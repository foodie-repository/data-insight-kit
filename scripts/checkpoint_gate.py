#!/usr/bin/env python3
"""
Create and enforce human-in-the-loop checkpoints between data-insight-kit stages.

The wrapper calls this script after explore/frame/analyze and before
communicate. If the checkpoint has no approved answer yet, the script writes
question artifacts and exits 3. If the latest answer asks for revision before
continuing, it exits 4.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# stage_guard.py lives next to this file. Reuse its answer validation so the
# checkpoint gate, the stage guard, and qa/validate.py all agree on what counts
# as a real v3 approval. Historically this gate only ran the weak
# is_human_confirmed() check, so a self-authored answer without provenance
# (recorded_by / answer_id / question_ref / approval_contract_version) passed
# here even though stage_guard and qa would reject it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_guard  # noqa: E402

KIT_ROOT = Path(__file__).resolve().parents[1]
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))
from dashboard_v5.contract import validate_layout  # noqa: E402


CHECKPOINTS: dict[str, dict[str, Any]] = {
    "data_profile": {
        "order": "01",
        "kind": "data_review",
        "header": "데이터 탐색 확인",
        "question_file": "01_data_profile_question",
        "recommended_option_id": "continue_with_current_data",
        "blocked_decision": "이 데이터 범위와 품질을 기준으로 분석 방향을 정해도 되는지 확인해야 한다.",
        "recommended_answer": "현재 데이터가 사용자의 목적에 맞고 기간·결측·샘플 한계를 인지했다면 현재 데이터로 진행한다. 목적이나 범위가 달라졌다면 범위·질문 수정을 선택한다.",
        "question": "현재 데이터 탐색 결과를 기준으로 다음 단계로 진행해도 될까요?",
        "options": [
            {
                "id": "continue_with_current_data",
                "label": "현재 데이터로 진행",
                "description": "표본, 기간, 주요 컬럼 한계를 인지한 상태에서 분석 방향을 정한다.",
                "recommended": True,
                "continue_pipeline": True,
                "maps_to": {"checkpoint_decision": "approved"},
            },
            {
                "id": "revise_scope",
                "label": "범위·질문 수정",
                "description": "데이터를 본 뒤 분석 목적, 기간, 세그먼트, 핵심 지표 후보를 다시 좁힌다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "revise_before_frame"},
            },
            {
                "id": "add_or_replace_data",
                "label": "데이터 보강",
                "description": "현재 데이터만으로는 부족하므로 추가 원천, 기간, 컬럼, 외부 보정 데이터를 보강한다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "needs_data_change"},
            },
        ],
    },
    "analysis_strategy": {
        "order": "02",
        "kind": "strategy_review",
        "header": "분석 전략 확인",
        "question_file": "02_analysis_strategy_question",
        "recommended_option_id": "approve_strategy",
        "blocked_decision": "핵심 지표, 분모, 비교 기준, 분석 질문이 사용자의 의도와 맞는지 확인해야 한다.",
        "recommended_answer": "핵심 질문, 핵심 지표, 분모, 비교 기준이 분석 목적과 맞으면 전략을 승인한다. 원하는 판단이 다르거나 지표가 낯설면 질문·지표 수정을 선택한다.",
        "question": "이 분석 방향과 핵심 지표 정의로 실제 분석을 진행해도 될까요?",
        "options": [
            {
                "id": "approve_strategy",
                "label": "전략 승인",
                "description": "제안된 핵심 질문, 핵심 지표, 비교 기준을 유지하고 분석 단계로 넘어간다.",
                "recommended": True,
                "continue_pipeline": True,
                "maps_to": {"checkpoint_decision": "approved"},
            },
            {
                "id": "revise_questions_kpis",
                "label": "질문·지표 수정",
                "description": "사용자가 원하는 의사결정과 맞도록 핵심 질문, 핵심 지표, 분모, 비교축을 다시 잡는다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "revise_frame"},
            },
            {
                "id": "choose_analysis_direction",
                "label": "분석 방향 다시 선택",
                "description": "규모·변화·구성·리스크·세그먼트 등 제안된 분석 방향안 중 다른 흐름으로 재구성한다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "rechoose_analysis_direction"},
            },
            {
                "id": "simplify_strategy",
                "label": "더 단순하게",
                "description": "심층 분석보다 읽기 쉬운 핵심 요약과 적은 수의 지표 중심으로 재구성한다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "simplify_frame"},
            },
        ],
    },
    "analysis_result_review": {
        # 조건부 checkpoint (spec §9). 고정 prefix 05_ — 번호는 식별자일 뿐 실행 순서가
        # 아니며, 실행 순서상 analyze 직후 dashboard_storyboard(03_) 앞에 온다.
        # 발동 여부는 wrapper/guard/QA가 결정적 술어로 판정하고, 이 gate는 요청받은
        # 경우에만 질문을 만든다.
        "order": "05",
        "kind": "result_review",
        "header": "1차 결과 확인",
        "question_file": "05_analysis_result_review_question",
        "recommended_option_id": "approve_analysis_result",
        "blocked_decision": "심화 분석 결과와 해석 수위가 사용자 목적과 업무 기준에 맞는지 확인해야 한다.",
        "recommended_answer": "핵심 발견이 목적과 맞고 해석이 과하지 않으면 승인한다. 결과가 낯설거나 결론이 과감하게 느껴지면 결론 수위 조정이나 기본 분석 전환을 선택한다.",
        "question": "1차 분석 결과를 기준으로 대시보드 구성 단계로 진행해도 될까요?",
        "options": [
            {
                "id": "approve_analysis_result",
                "label": "1차 결과 승인",
                "description": "핵심 발견이 목적과 맞으므로 이 결과를 기준으로 대시보드 구성안 확인 단계로 넘어간다.",
                "recommended": True,
                "continue_pipeline": True,
                "maps_to": {"checkpoint_decision": "approved"},
            },
            {
                "id": "lower_claim_strength",
                "label": "결론 수위 낮추기",
                "description": "발견 자체는 유지하되 확정 표현을 후보·참고 수준으로 낮춰 다시 정리한다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "reduce_analysis_claim_strength"},
            },
            {
                "id": "downgrade_to_basic",
                "label": "기본 분석으로 낮추기",
                "description": "심화 결과 대신 분포·구성·추세 중심의 기본 분석으로 다시 정리한다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "downgrade_route"},
            },
            {
                "id": "revise_analysis",
                "label": "해석 보완·재분석",
                "description": "표본, 비교 기준, 제외 규칙, 업무 기준을 조정해 분석을 다시 수행한다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "revise_analysis"},
            },
        ],
    },
    "dashboard_storyboard": {
        "order": "03",
        "kind": "storyboard_review",
        "header": "대시보드 구성 확인",
        "question_file": "03_dashboard_storyboard_question",
        "recommended_option_id": "approve_storyboard",
        "blocked_decision": "어떤 데이터/지표로 어떤 차트를 만들지, 어떤 화면 스타일로 보여줄지, 그리고 그 구성이 사용자 판단에 맞는지 확인해야 한다.",
        "recommended_answer": "차트 추천표의 데이터/지표, 비교 기준, 추천 차트, 대안/보류 이유가 의도와 맞으면 요약형 화면으로 승인한다. 더 깊게 탐색하려면 탐색형 화면, 반복 모니터링 목적이면 모니터링형 화면을 선택한다.",
        "question": "이 데이터/지표, 차트 추천, 대시보드 스타일로 최종 화면을 만들어도 될까요?",
        "options": [
            {
                "id": "approve_storyboard",
                "label": "요약형 화면으로 승인",
                "description": "핵심 지표 카드, 큰 메인 차트, 1-2개 보조 차트 중심으로 빠르게 읽히는 화면을 만든다.",
                "recommended": True,
                "continue_pipeline": True,
                "maps_to": {
                    "checkpoint_decision": "approved",
                    "dashboard_profile": "executive_brief",
                    "dashboard_density": "standard",
                    "dashboard_navigation": "tabs",
                },
            },
            {
                "id": "approve_analyst_workspace",
                "label": "탐색형 화면으로 승인",
                "description": "세그먼트, 예외, 관계, 표, 히트맵/산점도를 더 촘촘히 보고 비교할 수 있는 화면을 만든다.",
                "continue_pipeline": True,
                "maps_to": {
                    "checkpoint_decision": "approved",
                    "dashboard_profile": "analyst_workspace",
                    "dashboard_density": "compact",
                    "dashboard_navigation": "tabs",
                },
            },
            {
                "id": "approve_operations_monitor",
                "label": "모니터링형 화면으로 승인",
                "description": "현재 상태, 전 기간 대비 변화, 반복 지표와 예외 패널을 우선하는 화면을 만든다.",
                "continue_pipeline": True,
                "maps_to": {
                    "checkpoint_decision": "approved",
                    "dashboard_profile": "operations_monitor",
                    "dashboard_density": "standard",
                    "dashboard_navigation": "sidebar",
                },
            },
            {
                "id": "revise_chart_mix",
                "label": "차트 구성 수정",
                "description": "사용할 데이터/지표, 비교 기준, 차트 종류, 탭 순서, 강조 메시지를 다시 조정한다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "revise_chart_spec"},
            },
        ],
    },
    "report_outline": {
        "order": "04",
        "kind": "report_review",
        "header": "보고서 구성 확인",
        "question_file": "04_report_outline_question",
        "recommended_option_id": "approve_report_outline",
        "blocked_decision": "최종 보고서를 어떤 독자, 깊이, 논리 흐름, 문체로 작성할지 확인해야 한다.",
        "recommended_answer": "대시보드와 분석 결과의 흐름이 맞고 보고서 독자·깊이·문체가 의도와 맞으면 보고서 구성을 승인한다. 내부 용어가 많거나 결론 수위가 부담되면 문체·결론 수위 조정을 선택한다.",
        "question": "이 보고서 구성과 문체 방향으로 최종 보고서를 작성해도 될까요?",
        "options": [
            {
                "id": "approve_report_outline",
                "label": "보고서 구성 승인",
                "description": "현재 보고서 깊이, 독자, 핵심 발견 흐름, 문체 방향을 유지하고 최종 보고서를 작성한다.",
                "recommended": True,
                "continue_pipeline": True,
                "maps_to": {"checkpoint_decision": "approved"},
            },
            {
                "id": "revise_report_storyline",
                "label": "보고서 흐름 수정",
                "description": "핵심 발견 순서, 결론 수위, 요약과 심층 설명의 비중을 다시 잡는다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "revise_report_storyline"},
            },
            {
                "id": "adjust_audience_tone",
                "label": "독자·문체 조정",
                "description": "배포용, 내부 검토용, 실무 액션용 중 원하는 독자와 문체에 맞춰 다시 정리한다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "adjust_report_audience_tone"},
            },
            {
                "id": "reduce_overclaiming",
                "label": "결론 수위 낮추기",
                "description": "데이터가 직접 뒷받침하지 않는 추천, 원인, 성과 표현을 더 조심스럽게 바꾼다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "reduce_report_claim_strength"},
            },
        ],
    },
}

HUMAN_CONFIRMATION_SOURCES = {"ask_user_question", "user_chat", "manual_cli"}

DASHBOARD_DESIGN_PROFILES = {
    "executive_brief": {
        "label": "요약형 화면",
        "best_for": "핵심 지표와 주요 차트를 빠르게 공유하거나 리더에게 보고할 때",
        "layout": "핵심 지표 카드 + 큰 메인 차트 + 1-2개 보조 차트",
        "tradeoff": "세부 표와 탐색용 차트는 줄인다",
    },
    "analyst_workspace": {
        "label": "탐색형 화면",
        "best_for": "세그먼트, 예외, 관계, 분포를 깊게 탐색할 때",
        "layout": "촘촘한 그리드 + 히트맵/산점도/표/예외 패널",
        "tradeoff": "한눈에 읽히는 요약감은 약해질 수 있다",
    },
    "operations_monitor": {
        "label": "모니터링형 화면",
        "best_for": "주간/월간 반복 지표와 상태 변화를 추적할 때",
        "layout": "상태 카드 + 추세/비교 패널 + 레일형 화면 흐름",
        "tradeoff": "일회성 탐색 분석에는 과한 구조일 수 있다",
    },
}

CHART_TYPE_LABELS = {
    "line": "선 차트",
    "area": "영역 차트",
    "bar": "막대 차트",
    "stacked_bar": "누적 막대 차트",
    "histogram": "분포 차트",
    "scatter": "산점도",
    "heatmap": "히트맵",
    "boxplot": "상자그림",
    "waterfall": "증감 기여도 차트",
    "slope": "전후 비교 차트",
}

USER_REVIEW_BRIEFS: dict[str, dict[str, Any]] = {
    "data_profile": {
        "plain_title": "데이터를 먼저 보고 분석 방향을 정하는 단계",
        "why_this_checkpoint_matters": "데이터의 기간, 범위, 컬럼, 결측, 샘플을 확인해야 엉뚱한 질문이나 과한 결론으로 진행하지 않는다.",
        "what_user_should_review": [
            "이 데이터가 사용자가 보고 싶은 범위와 맞는지",
            "샘플과 주요 컬럼이 기대한 데이터인지",
            "현재 데이터만으로 가능한 분석과 불가능한 분석이 납득되는지",
        ],
        "what_will_happen_next": [
            "승인하면 핵심 지표와 핵심 질문을 잡는 분석 방향 확인 단계로 넘어간다.",
            "범위나 데이터가 다르면 실제 분석 전에 입력이나 분석 질문을 수정한다.",
        ],
        "what_this_does_not_decide": [
            "최종 차트 구성은 아직 확정하지 않는다.",
            "추천, 수익성, 원인 확정 같은 강한 결론은 추가 근거 없이는 확정하지 않는다.",
        ],
        "approval_question": "현재 데이터 범위와 한계를 이해한 상태에서 분석 전략 단계로 넘어가도 될까요?",
    },
    "analysis_strategy": {
        "plain_title": "무엇을 어떤 기준으로 분석할지 정하는 단계",
        "why_this_checkpoint_matters": "분석 질문과 핵심 지표가 사용자 의도와 맞지 않으면 이후 차트와 보고서가 그럴듯해도 쓸모가 떨어진다.",
        "what_user_should_review": [
            "핵심 질문이 실제로 알고 싶은 내용과 맞는지",
            "핵심 지표와 비교 기준이 이해 가능한지",
            "추천 분석 방향과 대안 중 어느 쪽이 더 원하는 결과물에 가까운지",
        ],
        "what_will_happen_next": [
            "승인하면 실제 계산과 인사이트 도출을 진행한다.",
            "수정하면 질문, 핵심 지표, 비교축을 다시 잡고 재확인한다.",
        ],
        "what_this_does_not_decide": [
            "대시보드의 최종 화면 구성은 아직 확정하지 않는다.",
            "데이터가 지원하지 않는 매출, 수요, 수익성 판단은 추가 원천 없이는 확정하지 않는다.",
        ],
        "approval_question": "이 질문과 핵심 지표 방향으로 실제 분석을 진행해도 될까요?",
    },
    "analysis_result_review": {
        "plain_title": "1차 분석 결과를 함께 확인하는 단계",
        "why_this_checkpoint_matters": "심화 분석이나 업무 도메인 판단이 들어간 결과는 화면과 보고서로 만들기 전에, 결과가 목적과 실제 업무 기준에 맞는지 먼저 확인해야 한다.",
        "what_user_should_review": [
            "핵심 발견이 알고 싶었던 질문에 실제로 답하는지",
            "결과 해석이 업무 상식이나 현장 경험과 어긋나지 않는지",
            "결론 수위가 데이터 근거에 비해 과하지 않은지",
        ],
        "what_will_happen_next": [
            "승인하면 대시보드 구성안 확인 단계로 넘어간다.",
            "수정을 선택하면 분석 깊이나 해석 수위를 조정한 뒤 다시 확인한다.",
        ],
        "what_this_does_not_decide": [
            "최종 화면 구성과 보고서 문체는 아직 확정하지 않는다.",
            "데이터가 직접 뒷받침하지 않는 원인, 추천, 성과 판단은 확정하지 않는다.",
        ],
        "approval_question": "1차 분석 결과를 이 방향으로 확정하고 화면 구성 단계로 넘어가도 될까요?",
    },
    "dashboard_storyboard": {
        "plain_title": "대시보드와 보고서의 흐름을 정하는 단계",
        "why_this_checkpoint_matters": "최종 화면을 만들기 전에 어떤 데이터와 지표를 어떤 차트로 보여줄지, 그리고 요약형·탐색형·모니터링형 중 어떤 화면 구성이 맞는지 확인해야 한다.",
        "what_user_should_review": [
            "각 차트가 사용할 데이터와 지표가 원하는 판단 흐름과 맞는지",
            "추천 차트와 대안 차트의 이유가 납득되는지",
            "요약형, 탐색형, 모니터링형 중 어떤 화면 구성이 목적에 맞는지",
        ],
        "what_will_happen_next": [
            "승인하면 최종 대시보드 화면을 만든다.",
            "수정하면 사용할 데이터/지표, 차트 종류, 탭 흐름, 메시지를 바꾼 뒤 다시 확인한다.",
        ],
        "what_this_does_not_decide": [
            "새 데이터를 자동으로 추가하지 않는다.",
            "데이터 한계를 넘어서는 추천이나 수익성 결론을 만들지 않는다.",
        ],
        "approval_question": "이 데이터/지표, 차트 추천, 화면 스타일로 최종 대시보드를 만들어도 될까요?",
    },
    "report_outline": {
        "plain_title": "최종 보고서의 독자와 논리 흐름을 확인하는 단계",
        "why_this_checkpoint_matters": "차트와 분석이 맞아도 보고서의 결론 수위, 문체, 설명 순서가 사용자 의도와 다르면 배포하거나 공유하기 어렵다.",
        "what_user_should_review": [
            "보고서가 누구에게 읽힐 문서인지",
            "요약과 심층 설명의 비중이 적절한지",
            "결론 수위와 피해야 할 표현이 의도와 맞는지",
        ],
        "what_will_happen_next": [
            "승인하면 최종 요약 보고서와 필요한 경우 심층 검토 보고서를 작성한다.",
            "수정하면 보고서 흐름, 문체, 결론 수위를 다시 잡고 재확인한다.",
        ],
        "what_this_does_not_decide": [
            "새 차트를 추가하거나 대시보드 구조를 자동 변경하지 않는다.",
            "데이터가 지원하지 않는 추천, 원인, 성과를 보고서에서 확정하지 않는다.",
        ],
        "approval_question": "이 독자와 논리 흐름, 문체 방향으로 최종 보고서를 작성해도 될까요?",
    },
}


# interview-loop-v2 §4.4: 라운드 2(추가 확인 후 확정) 공통 옵션. 정지점별
# 특화(방향 상세 표, 차트 재확인 등)는 data_profile 부착 커밋부터 확장한다.
ROUND2_OPTIONS: list[dict[str, Any]] = [
    {
        "id": "confirm_and_continue",
        "label": "확인했고 이대로 진행",
        "description": "추가로 확인한 내용을 반영해 이 단계를 확정하고 다음 단계로 진행한다.",
        "recommended": True,
        "continue_pipeline": True,
        "maps_to": {"checkpoint_decision": "approved"},
    },
    {
        "id": "needs_revision",
        "label": "수정이 필요함",
        "description": "확인 결과 방향이나 산출물을 고친 뒤 다시 확인한다.",
        "continue_pipeline": False,
        "maps_to": {"checkpoint_decision": "revise"},
    },
]

# 주 질문 답변이 이 loop_action을 가지면 라운드 2 트리거 (a)다 (spec §9).
MAIN_LOOP_ACTIONS = {"explore_direction", "free_question"}

# spec §8.1: domain mode에서 정지점별 companion 질문이 수집하는 domain_intake 필드.
CHECKPOINT_DOMAIN_FIELDS: dict[str, list[str]] = {
    "data_profile": ["row_meaning", "entity_grain", "column_semantics", "exclusion_rules"],
    "analysis_strategy": ["kpi_definitions", "segments", "reference_data", "forbidden_claims"],
    "analysis_result_review": ["evidence_boundaries", "open_questions"],
    "report_outline": ["terminology", "forbidden_claims"],
}

# 필드별 companion 질문 문구 (사용자 표현 — 내부 필드명 노출 금지, v1 §11).
DOMAIN_FIELD_QUESTIONS: dict[str, tuple[str, str]] = {
    "row_meaning": ("행의 의미", "이 데이터에서 행 1개는 어떤 업무 단위인가요? (예: 주문 1건, 고객 1명)"),
    "entity_grain": ("핵심 대상", "분석의 핵심 대상(고객·상품·지점 등)과 집계 단위는 무엇인가요?"),
    "column_semantics": ("컬럼 의미", "해석이 필요한 주요 컬럼이나 코드값이 있다면 업무 의미를 알려주세요."),
    "exclusion_rules": ("제외 기준", "분석에서 제외해야 할 데이터(테스트·취소·내부용 등)가 있나요?"),
    "objective": ("분석 목적", "이 분석으로 내리려는 실제 의사결정은 무엇인가요?"),
    "kpi_definitions": ("핵심 지표 기준", "업무에서 쓰는 핵심 지표의 계산 기준(분모·단위·비교 기준)을 알려주세요."),
    "segments": ("비교 축", "업무적으로 의미 있는 비교 축이나 그룹이 있나요?"),
    "reference_data": ("기준 자료", "함께 봐야 할 기준표·마스터·외부 기준이 있나요?"),
    "forbidden_claims": ("피해야 할 표현", "결과 해석에서 피해야 할 표현이나 위험한 결론이 있나요?"),
    "evidence_boundaries": ("판단 범위", "이 데이터로 직접 말할 수 있는 것과 없는 것의 경계를 알려주세요."),
    "open_questions": ("남은 질문", "결과를 보고 새로 생긴 의문이나 확인할 점이 있나요?"),
    "terminology": ("용어", "보고서 독자에게 맞는 용어나 표현 규칙이 있나요?"),
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"JSON root must be an object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    return path.as_posix()


def read_text_snippet(path: Path, max_lines: int = 28) -> str:
    if not path.exists():
        return f"{path} 파일이 아직 없습니다."
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return "\n".join(lines) if lines else f"{path} 파일에 읽을 수 있는 텍스트가 없습니다."


# input/에 wrapper·kit이 자동 생성하는 메타데이터 파일. 사용자 데이터가 아니므로
# 데이터 샘플 후보와 data_snapshot.source_files에서 제외한다. (알파벳 정렬상
# checkpoint_policy.json이 실제 데이터보다 앞에 와서 그게 "샘플"로 추출되던 버그의 원인.)
KIT_INTERNAL_INPUT_FILES = {
    "checkpoint_answers.json",
    "checkpoint_policy.json",
    "dependency_plan.json",
    "domain_intake.json",
    "external_adapter_plan.json",
    "external_denominators.json",
    "intake_questions.json",
    "run_context.json",
    "source_api_manifest.json",
}

# 데이터 샘플 후보 우선순위: 표 형식(parquet/csv/tsv)을 JSON보다 먼저 시도한다.
_SOURCE_SUFFIX_PRIORITY = {".parquet": 0, ".csv": 1, ".tsv": 2, ".jsonl": 3, ".json": 4}

# data_profile checkpoint는 원천을 다시 읽을 수 있으므로 connect 단계가 제거한
# 식별 컬럼을 되살리면 안 된다. 이름/주소/연락처/좌표와 이 데이터셋에서 쓰는
# 상세 위치·개체 키를 fail-closed denylist로 제거한다. 범주명처럼 분석에 필요한
# 일반적인 `*_name`은 유지하고, 개별 대상을 가리키는 열만 차단한다.
_SENSITIVE_PREVIEW_EXACT_COLUMNS = {
    "id",
    "recordid",
    "userid",
    "customerid",
    "accountid",
    "personid",
    "businessid",
    "storeid",
    "bizesid",
    "bizesnm",
    "brchnm",
    "lnocd",
    "plotsctcd",
    "plotsctnm",
    "lnomnno",
    "lnoslno",
    "lnoadr",
    "rdnmcd",
    "rdnm",
    "bldmnno",
    "bldslno",
    "bldmngno",
    "bldnm",
    "rdnmadr",
    "oldzipcd",
    "newzipcd",
    "dongno",
    "flrno",
    "hono",
    "lon",
    "lng",
    "lat",
    "longitude",
    "latitude",
    "상호",
    "상호명",
    "업체명",
    "사업체명",
    "지점명",
    "성명",
    "이름",
}
_SENSITIVE_PREVIEW_SUBSTRINGS = (
    "address",
    "email",
    "e-mail",
    "phone",
    "mobile",
    "telephone",
    "zipcode",
    "postalcode",
    "주소",
    "전화",
    "휴대폰",
    "이메일",
    "우편번호",
    "좌표",
)


def is_sensitive_preview_column(column: str) -> bool:
    raw = str(column).strip().lower()
    compact = re.sub(r"[\s_\-()./]+", "", raw)
    if compact in _SENSITIVE_PREVIEW_EXACT_COLUMNS:
        return True
    if any(fragment in raw for fragment in _SENSITIVE_PREVIEW_SUBSTRINGS):
        return True
    # snake/kebab/space 구분의 일반 개체 ID는 제외한다. category_code 같은
    # 분석 차원 코드는 이 규칙에 걸리지 않는다.
    parts = [part for part in re.split(r"[\s_\-./]+", raw) if part]
    return bool(parts and parts[-1] == "id")


def redact_preview_rows(rows: list[list[str]]) -> list[list[str]]:
    if not rows:
        return []
    keep = [idx for idx, column in enumerate(rows[0]) if not is_sensitive_preview_column(column)]
    if not keep:
        return []
    return [[row[idx] if idx < len(row) else "" for idx in keep] for row in rows]


def redact_preview_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: redact_preview_json(item)
            for key, item in value.items()
            if not is_sensitive_preview_column(str(key))
        }
    if isinstance(value, list):
        return [redact_preview_json(item) for item in value]
    return value


def source_files(run: Path) -> list[Path]:
    input_dir = run / "input"
    if not input_dir.exists():
        return []
    allowed = {".csv", ".tsv", ".json", ".jsonl", ".parquet"}
    files = [
        p
        for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in allowed and p.name not in KIT_INTERNAL_INPUT_FILES
    ]
    return sorted(files, key=lambda p: (_SOURCE_SUFFIX_PRIORITY.get(p.suffix.lower(), 9), p.name))[:20]


def read_csv_preview_rows(source: Path, delimiter: str, limit: int) -> list[list[str]]:
    # utf-8을 errors="replace"로만 읽으면 cp949 한글이 U+FFFD로 뭉개진 채
    # 미리보기에 실린다 — strict 디코딩으로 인코딩을 판별한 뒤 마지막에만 관용.
    for encoding, errors in (("utf-8-sig", "strict"), ("cp949", "strict"), ("utf-8-sig", "replace")):
        try:
            with source.open("r", encoding=encoding, errors=errors, newline="") as inp:
                reader = csv.reader(inp, delimiter=delimiter)
                rows: list[list[str]] = []
                for idx, row in enumerate(reader):
                    rows.append(row)
                    if idx >= limit:
                        break
                return rows
        except UnicodeDecodeError:
            continue
    return []


def write_csv_preview(source: Path, target: Path, delimiter: str = ",", limit: int = 20) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = redact_preview_rows(read_csv_preview_rows(source, delimiter, limit))
    if not rows:
        return False
    with target.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerows(rows)
    return True


def write_json_preview(source: Path, target: Path, limit: int = 20) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8", errors="replace")
    if source.suffix.lower() == ".jsonl":
        lines = [line for line in text.splitlines() if line.strip()][:limit]
        if not lines:
            return False
        try:
            sample = [redact_preview_json(json.loads(line)) for line in lines]
        except json.JSONDecodeError:
            return False
        target.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in sample) + "\n",
            encoding="utf-8",
        )
        return True
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    if isinstance(data, list):
        sample = data[:limit]
    elif isinstance(data, dict):
        sample = data
    else:
        sample = data
    sample = redact_preview_json(sample)
    target.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def write_parquet_preview(source: Path, target: Path, limit: int = 20) -> bool:
    try:
        import polars as pl  # type: ignore
    except Exception:
        return False
    try:
        scan = pl.scan_parquet(str(source))
        columns = [name for name in scan.collect_schema().names() if not is_sensitive_preview_column(name)]
        if not columns:
            return False
        df = scan.select(columns).limit(limit).collect()
        df.write_csv(str(target))
    except Exception:
        return False
    return True


def build_data_preview(run: Path, checkpoint_dir: Path, notes: list[str]) -> str | None:
    # connect가 만든 제한·비식별 preview가 있으면 원천 재샘플링보다 우선한다.
    # 이 파일도 같은 redaction writer를 통과시켜 방어를 한 겹 더 둔다.
    staged_previews = [
        run / "outputs" / "data_preview.csv",
        run / "outputs" / "data_preview.tsv",
        run / "outputs" / "data_preview.jsonl",
        run / "outputs" / "data_preview.json",
        run / "outputs" / "data_preview.parquet",
    ]
    candidates = [(source, True) for source in staged_previews if source.exists()]
    candidates.extend((source, False) for source in source_files(run))
    for source, staged in candidates:
        suffix = source.suffix.lower()
        origin = "connect 단계의 제한 샘플" if staged else str(source)
        if suffix == ".csv":
            target = checkpoint_dir / "data_preview.csv"
            if write_csv_preview(source, target):
                notes.append(f"{origin}에서 식별 가능 컬럼을 제외하고 최대 20행을 추출했다.")
                return rel(target)
        if suffix == ".tsv":
            target = checkpoint_dir / "data_preview.csv"
            if write_csv_preview(source, target, delimiter="\t"):
                notes.append(f"{origin}에서 식별 가능 컬럼을 제외하고 최대 20행 TSV 샘플을 CSV로 추출했다.")
                return rel(target)
        if suffix in {".json", ".jsonl"}:
            target = checkpoint_dir / f"data_preview{suffix}"
            if write_json_preview(source, target):
                notes.append(f"{origin}에서 식별 가능 필드를 제외한 JSON 샘플을 추출했다.")
                return rel(target)
        if suffix == ".parquet":
            target = checkpoint_dir / "data_preview.csv"
            if write_parquet_preview(source, target):
                notes.append(f"{origin}에서 식별 가능 컬럼을 제외하고 최대 20행 Parquet 샘플을 CSV로 추출했다.")
                return rel(target)
            notes.append(f"{origin}은 안전한 Parquet 샘플을 만들 수 없어 profile/EDA 요약으로 대체한다.")
    if not source_files(run):
        notes.append("input/ 아래에서 샘플링 가능한 CSV, TSV, JSON, JSONL, Parquet 파일을 찾지 못했다.")
    return None


def chart_spec_summary(path: Path) -> str:
    if not path.exists():
        return f"{path} 파일이 아직 없습니다."
    data = load_json(path)
    charts = data.get("charts") or []
    if not isinstance(charts, list):
        return "chart_spec.json의 charts 구조를 읽지 못했습니다."
    lines = [f"chart_spec charts: {len(charts)}"]
    story = data.get("dashboard_story") or {}
    if isinstance(story, dict) and any(story.get(k) for k in ("headline", "decision", "caveat")):
        if story.get("headline"):
            lines.append(f"story headline: {story.get('headline')}")
        if story.get("decision"):
            lines.append(f"decision: {story.get('decision')}")
        if story.get("caveat"):
            lines.append(f"caveat: {story.get('caveat')}")
    design = data.get("dashboard_design") or {}
    if isinstance(design, dict) and design.get("selected_profile"):
        profile = str(design.get("selected_profile"))
        profile_label = DASHBOARD_DESIGN_PROFILES.get(profile, {}).get("label", profile)
        lines.append(f"dashboard design: {profile_label}")
        if design.get("rationale"):
            lines.append(f"design rationale: {design.get('rationale')}")
    quality = data.get("quality_contract") or {}
    if isinstance(quality, dict) and quality.get("version") == "v5.1":
        brief = quality.get("decision_brief") or {}
        if brief.get("decision"):
            lines.append(f"판단 목적: {brief.get('decision')}")
        if brief.get("primary_question"):
            lines.append(f"핵심 질문: {brief.get('primary_question')}")
        family_labels = {
            "trend": "추세",
            "comparison": "비교",
            "composition": "구성",
            "distribution": "분포",
            "relationship": "관계",
            "matrix": "행렬",
            "decomposition": "기여 분해",
        }
        intent_labels = {
            "status": "현황",
            "movement": "변화",
            "ranking": "순위",
            "composition": "구성",
            "distribution": "분포",
            "relationship": "관계",
            "exception": "예외",
            "progression": "진행",
        }
        for chart in charts:
            if not isinstance(chart, dict):
                continue
            visual = chart.get("visual_contract") or {}
            if not visual:
                continue
            chart_obj = chart.get("chart") or {}
            variant = visual.get("variant") or chart_obj.get("type") or "unknown"
            lines.append(
                "표현 계획: "
                f"{family_labels.get(visual.get('family'), visual.get('family'))} / "
                f"{intent_labels.get(visual.get('comparison_intent'), visual.get('comparison_intent'))} / "
                f"{CHART_TYPE_LABELS.get(str(variant), str(variant))}"
            )
    recommendation_lines = chart_recommendation_table(charts)
    if recommendation_lines:
        lines.extend(["", "사용자용 차트 추천표:"])
        lines.extend(recommendation_lines)
    methods: dict[str, int] = {}
    chart_types: dict[str, int] = {}
    for chart in charts[:8]:
        if not isinstance(chart, dict):
            continue
        title = chart.get("title") or chart.get("question") or chart.get("id") or "(untitled)"
        chart_obj = chart.get("chart") or {}
        chart_type = chart.get("chart_type") or chart.get("type") or chart_obj.get("type") or "unknown"
        method_name = chart.get("method") or "unknown"
        methods[method_name] = methods.get(method_name, 0) + 1
        chart_types[chart_type] = chart_types.get(chart_type, 0) + 1
        method = chart.get("methodology") or chart.get("method") or ""
        lines.append(f"- {chart_type}: {title}" + (f" / {method}" if method else ""))
    if charts:
        lines.append(f"method mix: {methods}")
        lines.append(f"chart type mix: {chart_types}")
        if len(charts) >= 4 and (len(methods) < 3 or len(chart_types) < 2):
            lines.append("review note: 차트 구성의 질문/방법론이 단조로울 수 있으므로 storyboard 확인이 필요하다.")
    return "\n".join(lines)


def dashboard_layout_summary(path: Path) -> str:
    if not path.exists():
        return f"dashboard_layout path: {path}\n파일이 아직 없습니다."
    layout = load_json(path)
    revision = layout.get("revision")
    lines = [
        f"dashboard_layout path: {path}",
        f"revision {revision}",
        "| component | kind | role | 목적 | 판단 연결 | 표현 방식 | desktop span | mobile order |",
        "|---|---|---|---|---|---|---:|---:|",
    ]
    for component in layout.get("components") or []:
        if not isinstance(component, dict):
            continue
        placement = component.get("placement") if isinstance(component.get("placement"), dict) else {}
        desktop = placement.get("desktop") if isinstance(placement.get("desktop"), dict) else {}
        mobile = placement.get("mobile") if isinstance(placement.get("mobile"), dict) else {}
        render_options = (
            component.get("render_options")
            if isinstance(component.get("render_options"), dict)
            else {}
        )
        series_layout = render_options.get("series_layout")
        rendering = {
            "stacked_panels": "같은 시간축의 위아래 패널",
            "overlay": "한 화면에 겹침",
        }.get(series_layout, "기본")
        lines.append(
            f"| {component.get('id', '')} | {component.get('kind', '')} | "
            f"{component.get('role', '')} | {component.get('purpose', '')} | "
            f"{component.get('decision_link') or '-'} | {rendering} | {desktop.get('span', '')} | "
            f"{mobile.get('order', '')} |"
        )
    return "\n".join(lines)


def chart_recommendation_table(charts: list[Any], limit: int = 8) -> list[str]:
    if not charts:
        return []
    lines = [
        "| 사용할 데이터/지표 | 비교 기준 | 추천 차트 | 이 차트가 좋은 이유 | 대안/보류 이유 |",
        "|---|---|---|---|---|",
    ]
    for chart in charts[:limit]:
        if not isinstance(chart, dict):
            continue
        req = chart.get("data_requirements") if isinstance(chart.get("data_requirements"), dict) else {}
        chart_obj = chart.get("chart") if isinstance(chart.get("chart"), dict) else {}
        calculation = chart.get("calculation") if isinstance(chart.get("calculation"), dict) else {}
        grain = chart.get("grain") if isinstance(chart.get("grain"), dict) else {}
        rec = chart.get("chart_recommendation") if isinstance(chart.get("chart_recommendation"), dict) else {}
        measures = req.get("measures") if isinstance(req.get("measures"), list) else []
        dimensions = req.get("dimensions") if isinstance(req.get("dimensions"), list) else []
        time_columns = req.get("time_columns") if isinstance(req.get("time_columns"), list) else []
        chart_type = chart_obj.get("type") or chart.get("chart_type") or chart.get("type") or "unknown"
        data_or_metric = (
            rec.get("data_or_metric")
            or calculation.get("metric_definition")
            or chart.get("question")
            or ", ".join(str(item) for item in measures[:3])
            or chart.get("id")
            or "(지표 미상)"
        )
        comparison_basis = (
            rec.get("comparison_basis")
            or grain.get("row_meaning")
            or ", ".join(str(item) for item in [*dimensions[:2], *time_columns[:1]])
            or "전체 비교"
        )
        recommended_chart = rec.get("recommended_chart") or CHART_TYPE_LABELS.get(str(chart_type), str(chart_type))
        why_recommended = rec.get("why_recommended") or chart_obj.get("why_this_chart") or (chart.get("insight") or {}).get("finding") or "질문에 직접 답하기 위한 차트"
        alternative = rec.get("alternative_chart")
        tradeoff = rec.get("alternative_tradeoff")
        if alternative and tradeoff:
            alternative_text = f"{alternative}: {tradeoff}"
        elif alternative:
            alternative_text = str(alternative)
        elif tradeoff:
            alternative_text = str(tradeoff)
        else:
            alternative_text = (chart.get("insight") or {}).get("limit") or "대안 차트는 데이터 확인 후 조정"
        lines.append(
            "| "
            + " | ".join(
                sanitize_table_cell(str(value))
                for value in [data_or_metric, comparison_basis, recommended_chart, why_recommended, alternative_text]
            )
            + " |"
        )
    return lines if len(lines) > 2 else []


def sanitize_table_cell(value: str, max_chars: int = 120) -> str:
    value = " ".join(value.replace("|", "/").split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def report_contract_summary(run: Path) -> str:
    manifest = load_json(run / "manifest.json")
    intake = manifest.get("intake") if isinstance(manifest.get("intake"), dict) else {}
    report = intake.get("report") if isinstance(intake.get("report"), dict) else {}
    if not report:
        report = {"depth": "standard", "audience": "mixed", "evidence_scope": "data_only"}
    lines = [
        "report contract:",
        f"- depth: {report.get('depth', 'standard')}",
        f"- audience: {report.get('audience', 'mixed')}",
        f"- evidence_scope: {report.get('evidence_scope', 'data_only')}",
    ]
    objective = intake.get("objective")
    decision_context = intake.get("decision_context")
    if objective:
        lines.append(f"- objective: {objective}")
    if decision_context:
        lines.append(f"- decision_context: {decision_context}")
    return "\n".join(lines)


def dashboard_data_summary(path: Path) -> str:
    if not path.exists():
        return f"{path} 파일이 아직 없습니다."
    data = load_json(path)
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    sections = data.get("sections") or []
    sources = data.get("sources") or []
    lines = ["dashboard summary:"]
    if meta.get("title"):
        lines.append(f"- title: {meta.get('title')}")
    if meta.get("audience") or meta.get("mode"):
        lines.append(f"- audience/mode: {meta.get('audience', '')} / {meta.get('mode', '')}")
    if isinstance(sources, list):
        lines.append(f"- sources: {len(sources)}")
    if isinstance(sections, list):
        lines.append(f"- sections: {len(sections)}")
        for section in sections[:6]:
            if isinstance(section, dict):
                title = section.get("title") or section.get("id") or "(untitled)"
                cards = section.get("cards") or []
                charts = section.get("charts") or []
                lines.append(f"  - {title}: cards={len(cards) if isinstance(cards, list) else 0}, charts={len(charts) if isinstance(charts, list) else 0}")
    return "\n".join(lines)


def compact_for_chat(text: str, max_chars: int = 650) -> str:
    cleaned: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        cleaned.append(line)
    compact = " ".join(cleaned)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def build_chat_prompt(question: dict[str, Any]) -> str:
    brief = question.get("user_review_brief") or {}
    review_items = brief.get("what_user_should_review") or []
    profiles = question.get("dashboard_design_profiles")
    current_summary = " ".join(
        part
        for part in [
            str(brief.get("plain_title", "")).strip(),
            str(brief.get("why_this_checkpoint_matters", "")).strip(),
        ]
        if part
    )
    # 사용자 피드백(2026-07-12): 슬래시로 이어붙인 벽 텍스트는 읽기 어렵다 —
    # deep-interview 형식(현재 이해/확인할 내용/막힌 결정/추천 답안/질문)의
    # 라벨은 유지하되 불릿 포인트로 구성한다.
    lines = [
        f"- 현재 이해: {compact_for_chat(current_summary or question.get('current_understanding', ''))}"
    ]
    if review_items:
        lines.append("- 확인할 내용:")
        lines.extend(f"  - {item}" for item in review_items[:3])
    if isinstance(profiles, dict):
        profile_lines = [
            f"  - {value.get('label')}: {value.get('best_for')}"
            for value in profiles.values()
            if isinstance(value, dict)
        ]
        if profile_lines:
            lines.append("- 화면 스타일 선택지:")
            lines.extend(profile_lines)
    lines.append(f"- 막힌 결정: {question.get('blocked_decision', '')}")
    lines.append(f"- 추천 답안: {question.get('recommended_answer', '')}")
    lines.append(f"- 질문: {question.get('question', '')}")
    return "\n".join(lines)


def current_understanding(run: Path, checkpoint_id: str) -> tuple[str, dict[str, Any], list[dict[str, str]]]:
    checkpoint_dir = run / "outputs" / "checkpoints"
    notes: list[str] = []
    artifacts: list[dict[str, str]] = []

    if checkpoint_id == "data_profile":
        preview = build_data_preview(run, checkpoint_dir, notes)
        profile = run / "outputs" / "01_profile.md"
        eda = run / "outputs" / "02_eda.md"
        summary = "\n\n".join(
            [
                "[01_profile 요약]",
                read_text_snippet(profile, 18),
                "[02_eda 요약]",
                read_text_snippet(eda, 24),
            ]
        )
        if preview:
            artifacts.append({"path": preview, "type": "sample", "description": "사용자 검토용 제한 샘플"})
        artifacts.extend(
            [
                {"path": rel(profile), "type": "profile", "description": "connect 단계 데이터 프로파일"},
                {"path": rel(eda), "type": "eda", "description": "explore 단계 탐색 결과"},
            ]
        )
        snapshot = {
            "source_files": [rel(p) for p in source_files(run)],
            "sample_preview_path": preview,
            "profile_path": rel(profile) if profile.exists() else None,
            "eda_path": rel(eda) if eda.exists() else None,
            "notes": notes,
        }
        return summary, snapshot, artifacts

    if checkpoint_id == "analysis_strategy":
        frame = run / "outputs" / "03_frame.md"
        parts = ["[03_frame 요약]", read_text_snippet(frame, 36)]
        artifacts.append({"path": rel(frame), "type": "frame", "description": "문제 정의, KPI, 분석 전략"})
        route_summary = method_route_summary(run)
        if route_summary:
            parts.extend(["[분석 깊이 요약]", route_summary])
            artifacts.append(
                {
                    "path": rel(run / "outputs" / "method_route.json"),
                    "type": "method_route",
                    "description": "분석 깊이와 적용 방법 기록",
                }
            )
        dependency_summary = dependency_plan_summary(run)
        if dependency_summary:
            parts.extend(["[추가 분석 기능 준비]", dependency_summary])
            artifacts.append(
                {
                    "path": rel(run / "input" / "dependency_plan.json"),
                    "type": "dependency_plan",
                    "description": "추가 분석 기능 준비 상태와 승인 기록",
                }
            )
        return "\n\n".join(parts), None, artifacts

    if checkpoint_id == "analysis_result_review":
        analysis = run / "outputs" / "04_analysis.md"
        chart_spec = run / "outputs" / "chart_spec.json"
        parts = ["[04_analysis 요약]", read_text_snippet(analysis, 30)]
        route_summary = method_route_summary(run)
        if route_summary:
            parts.extend(["[분석 깊이 요약]", route_summary])
        parts.extend(["[chart_spec 요약]", chart_spec_summary(chart_spec)])
        artifacts.extend(
            [
                {"path": rel(analysis), "type": "analysis", "description": "1차 분석 결과와 근거·한계"},
                {"path": rel(chart_spec), "type": "chart_spec", "description": "질문별 발견과 차트 설계 초안"},
            ]
        )
        route_path = run / "outputs" / "method_route.json"
        if route_path.exists():
            artifacts.append(
                {"path": rel(route_path), "type": "method_route", "description": "분석 깊이와 적용 방법 기록"}
            )
        return "\n\n".join(parts), None, artifacts

    if checkpoint_id == "report_outline":
        analysis = run / "outputs" / "04_analysis.md"
        chart_spec = run / "outputs" / "chart_spec.json"
        dashboard_data = run / "outputs" / "dashboard_data.json"
        summary = "\n\n".join(
            [
                "[보고서 설정]",
                report_contract_summary(run),
                "[대시보드 요약]",
                dashboard_data_summary(dashboard_data),
                "[04_analysis 요약]",
                read_text_snippet(analysis, 26),
                "[chart_spec 요약]",
                chart_spec_summary(chart_spec),
            ]
        )
        artifacts.extend(
            [
                {"path": rel(analysis), "type": "analysis", "description": "보고서 근거가 되는 분석 결과"},
                {"path": rel(chart_spec), "type": "chart_spec", "description": "차트별 질문, 근거, 한계"},
                {"path": rel(dashboard_data), "type": "dashboard_data", "description": "보고서와 수치가 일치해야 하는 대시보드 데이터"},
            ]
        )
        return summary, None, artifacts

    analysis = run / "outputs" / "04_analysis.md"
    chart_spec = run / "outputs" / "chart_spec.json"
    parts = [
        "[04_analysis 요약]",
        read_text_snippet(analysis, 30),
        "[chart_spec 요약]",
        chart_spec_summary(chart_spec),
    ]
    artifacts.extend(
        [
            {"path": rel(analysis), "type": "analysis", "description": "분석 결과와 대시보드 메시지"},
            {"path": rel(chart_spec), "type": "chart_spec", "description": "차트 설계와 대시보드 매핑"},
        ]
    )
    if checkpoint_id == "dashboard_storyboard":
        layout = run / "outputs" / "dashboard_layout.json"
        if layout.exists():
            layout_data = load_json(layout)
            parts.extend(
                [
                    "[dashboard_layout 승인 원문]",
                    dashboard_layout_summary(layout),
                ]
            )
            artifacts.append(
                {
                    "path": rel(layout),
                    "type": "dashboard_layout",
                    "description": f"승인할 화면 구조 revision {layout_data.get('revision')}",
                }
            )
    return "\n\n".join(parts), None, artifacts


# 내부 route 값의 사용자용 표현 (spec §11). 질문·요약에는 내부 enum을 그대로 쓰지 않는다.
ROUTE_USER_LABELS = {
    "descriptive": "기본 현황 분석",
    "diagnostic": "차이·예외 진단 분석",
    "statistical": "통계적 확인 분석",
    "ml_exploratory": "패턴·군집 탐색 분석",
    "predictive": "예측 후보 분석",
    "causal_experiment": "전후·실험 비교 분석",
}

EXTRA_USER_LABELS = {
    "stats": "통계 검정·신뢰구간 기능",
    "ml": "군집·이상치 탐색 기능",
}

# 승인 시점 잠금 대상. checkpoint 질문 생성 시 존재하는 파일의 sha256을
# approval_targets로 내장한다. 검증(재승인 요구)은 stage guard와 QA가 한다.
APPROVAL_TARGET_FILES = {
    "analysis_strategy": {
        "method_route": ("outputs", "method_route.json"),
        "dependency_plan": ("input", "dependency_plan.json"),
    },
    "dashboard_storyboard": {
        "dashboard_layout": ("outputs", "dashboard_layout.json"),
    },
}


def method_route_summary(run: Path) -> str:
    route_data = load_json(run / "outputs" / "method_route.json")
    if not route_data:
        return ""
    route = str(route_data.get("route") or "")
    lines = [f"- 추천 분석 깊이: {ROUTE_USER_LABELS.get(route, route)}"]
    methods = route_data.get("selected_methods") or []
    if methods:
        lines.append(f"- 적용 방법 수: {len(methods)}")
    if route_data.get("downgraded_from"):
        origin = str(route_data.get("downgraded_from"))
        lines.append(
            f"- 원래 {ROUTE_USER_LABELS.get(origin, origin)}을(를) 검토했으나 조건이 부족해 낮췄다: "
            f"{route_data.get('downgrade_reason') or '사유 미기록'}"
        )
    return "\n".join(lines)


def dependency_plan_summary(run: Path) -> str:
    plan = load_json(run / "input" / "dependency_plan.json")
    if not plan:
        return ""
    missing = [str(g) for g in plan.get("missing") or []]
    installed = [str(g) for g in plan.get("installed") or []]
    lines: list[str] = []
    if installed:
        labels = ", ".join(EXTRA_USER_LABELS.get(g, g) for g in installed)
        lines.append(f"- 이미 준비된 기능: {labels}")
    if missing:
        labels = ", ".join(EXTRA_USER_LABELS.get(g, g) for g in missing)
        lines.append(f"- 설치 승인이 필요한 기능: {labels}")
        lines.append("- 설치는 사용자가 승인한 경우에만 kit 전용 환경에 진행한다.")
        lines.append("- 설치하지 않으면 기본·진단 분석 범위로 진행한다.")
    if not lines:
        lines.append("- 추가 기능 설치 없이 진행 가능한 분석이다.")
    return "\n".join(lines)


def approval_targets_for(
    run: Path, checkpoint_id: str = "analysis_strategy"
) -> dict[str, dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    for key, (folder, name) in APPROVAL_TARGET_FILES.get(checkpoint_id, {}).items():
        path = run / folder / name
        if not path.exists():
            continue
        artifact = load_json(path)
        targets[key] = {
            "path": rel(path),
            "sha256": stage_guard.sha256_file(path),
            "created_at": artifact.get("created_at") or artifact.get("generated_at"),
        }
        if key == "dashboard_layout":
            targets[key]["revision"] = artifact.get("revision")
    return targets


def analysis_strategy_dependency_options(run: Path) -> tuple[list[dict[str, Any]], str] | None:
    """설치 승인이 필요한 run에서만 dependency 결정이 포함된 4개 옵션을 만든다.

    설치 승인은 명시 옵션 선택으로만 인정된다 (spec §7.2). free-text 답변은
    설치 승인이 아니며 wrapper/guard가 skip_install로 처리한다. checkpoint_question
    schema의 options maxItems=4에 맞춰 기존 simplify 옵션은 미설치 진행 옵션이 대신한다.
    """
    plan = load_json(run / "input" / "dependency_plan.json")
    missing = [str(g) for g in plan.get("missing") or []]
    if not missing:
        return None
    labels = ", ".join(EXTRA_USER_LABELS.get(g, g) for g in missing)
    options = [
        {
            "id": "install_and_deepen",
            "label": "추가 기능 설치 후 심화 분석 진행",
            "description": f"{labels}을(를) kit 전용 환경에 설치하고 추천된 심화 분석을 진행한다.",
            "recommended": True,
            "continue_pipeline": True,
            "maps_to": {"checkpoint_decision": "approved", "dependency_decision": "install"},
        },
        {
            "id": "proceed_without_install",
            "label": "설치 없이 기본 분석으로 진행",
            "description": "추가 설치 없이 현재 가능한 기본·진단 분석 범위로 낮춰 진행한다.",
            "continue_pipeline": True,
            "maps_to": {"checkpoint_decision": "approved", "dependency_decision": "skip_install"},
        },
        {
            "id": "revise_questions_kpis",
            "label": "질문·지표 수정",
            "description": "사용자가 원하는 의사결정과 맞도록 핵심 질문, 핵심 지표, 분모, 비교축을 다시 잡는다.",
            "continue_pipeline": False,
            "maps_to": {"checkpoint_decision": "revise_frame", "dependency_decision": "adjust"},
        },
        {
            "id": "choose_analysis_direction",
            "label": "분석 방향 다시 선택",
            "description": "제안된 분석 깊이와 방향 대신 다른 흐름으로 재구성한다.",
            "continue_pipeline": False,
            "maps_to": {"checkpoint_decision": "rechoose_analysis_direction", "dependency_decision": "adjust"},
        },
    ]
    recommended_answer = (
        "추천 심화 분석이 목적과 맞으면 추가 기능 설치 후 진행을 선택한다. "
        "설치 없이 빠르게 보려면 기본 분석 진행을, 방향이 다르면 수정 선택지를 고른다. "
        "설치는 명시적으로 이 선택지를 고른 경우에만 진행된다."
    )
    return options, recommended_answer


def apply_dashboard_storyboard_recommendation(question: dict[str, Any], run: Path) -> None:
    """chart_spec이 고른 v5 프로필을 정지점의 실제 추천 선택지로 반영한다."""
    chart_spec = load_json(run / "outputs" / "chart_spec.json")
    design = chart_spec.get("dashboard_design") or {}
    selected_profile = str(design.get("selected_profile") or "executive_brief")
    profile_to_option = {
        "executive_brief": "approve_storyboard",
        "analyst_workspace": "approve_analyst_workspace",
        "operations_monitor": "approve_operations_monitor",
    }
    recommended_answers = {
        "executive_brief": (
            "이번 분석은 핵심 지표와 주요 메시지를 빠르게 공유하는 구성이므로 "
            "요약형 화면으로 승인하는 것을 추천한다. 세부 비교가 더 중요하면 탐색형을 선택한다."
        ),
        "analyst_workspace": (
            "이번 분석은 세그먼트, 예외, 관계를 촘촘히 비교하는 구성이므로 "
            "탐색형 화면으로 승인하는 것을 추천한다. 빠른 공유가 우선이면 요약형을 선택한다."
        ),
        "operations_monitor": (
            "이번 분석은 반복 지표와 상태 변화를 추적하는 구성이므로 "
            "모니터링형 화면으로 승인하는 것을 추천한다. 일회성 탐색이면 탐색형을 선택한다."
        ),
    }
    if selected_profile not in profile_to_option:
        selected_profile = "executive_brief"
    recommended_option_id = profile_to_option[selected_profile]
    for option in question.get("options", []):
        option.pop("recommended", None)
        if option.get("id") == recommended_option_id:
            option["recommended"] = True
    question["recommended_option_id"] = recommended_option_id
    question["recommended_answer"] = recommended_answers[selected_profile]


def answer_candidates(run: Path) -> list[Path]:
    return [run / "checkpoint_answers.json", run / "input" / "checkpoint_answers.json"]


def load_answers_fail_closed(run: Path) -> list[dict[str, Any]]:
    """interview-loop-v2 §4.3 canonical 단일화: 진행 판정 입력은
    runs/<run-id>/checkpoint_answers.json 하나다. input/ mirror는 판정에 쓰지
    않고 정합만 검사한다 — 과거에는 canonical 뒤에 mirror를 이어붙여
    answers[-1]을 취했기 때문에, 이중 기록 중 크래시로 어긋난 mirror의 옛
    승인이 최신 중단 의사를 덮을 수 있었다 (Codex 교차검증 H2)."""
    canonical = run / "checkpoint_answers.json"
    mirror = run / "input" / "checkpoint_answers.json"
    if mirror.exists():
        if not canonical.exists():
            raise SystemExit(
                "⛔ checkpoint_answers.json mirror가 canonical 없이 존재합니다 (fail-closed).\n"
                f"- canonical(없음): {canonical}\n"
                f"- mirror: {mirror}\n"
                "scripts/apply_checkpoint_answer.py로 답변을 다시 기록해 동기화하세요."
            )
        if canonical.read_bytes() != mirror.read_bytes():
            raise SystemExit(
                "⛔ canonical/mirror checkpoint_answers.json 불일치 (fail-closed).\n"
                f"- canonical: {canonical}\n"
                f"- mirror: {mirror}\n"
                "scripts/apply_checkpoint_answer.py로 답변을 다시 기록해 동기화하세요."
            )
    data = load_json(canonical)
    raw = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def latest_answer(run: Path, checkpoint_id: str) -> dict[str, Any] | None:
    """최신 '결정 레코드' (spec §4.3 선택 계약): companion 레코드만 제외한다.
    자유 질문 레코드는 I1에 의해 항상 continue_pipeline=false라 승인을 만들 수
    없고 라운드 전이만 유발한다. companion 제외로 승인 뒤 companion append가
    상태를 뒤집는 것을 막는다 (Codex 교차검증 M1)."""
    answers = [
        item
        for item in load_answers_fail_closed(run)
        if item.get("checkpoint_id") == checkpoint_id and not item.get("companion_id")
    ]
    return answers[-1] if answers else None


def free_question_count(run: Path, checkpoint_id: str, round_num: int) -> int:
    return sum(
        1
        for item in load_answers_fail_closed(run)
        if item.get("checkpoint_id") == checkpoint_id
        and item.get("loop_action") == "free_question"
        and int(item.get("interview_round") or 1) == round_num
    )


def question_file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mini_result_paths_for(run: Path, checkpoint_id: str, answer_id: str) -> list[str]:
    """자유 질문 미니 결과 artifact (spec §7): 자유 질문 답변 레코드의
    answer_id와 연결된 것만 라운드 2 질문에 노출한다."""
    paths: list[str] = []
    exploration = run / "outputs" / "exploration"
    if not answer_id or not exploration.is_dir():
        return paths
    for meta in sorted(exploration.glob(f"free_question_{checkpoint_id}_*.json")):
        if load_json(meta).get("answer_id") != answer_id:
            continue
        paths.append(rel(meta))
        markdown = meta.with_suffix(".md")
        if markdown.exists():
            paths.append(rel(markdown))
    return paths

def is_human_confirmed(answer: dict[str, Any]) -> bool:
    source = answer.get("source")
    user_response = str(answer.get("user_response") or "").strip()
    return (
        source in HUMAN_CONFIRMATION_SOURCES
        and bool(user_response)
        and bool(answer.get("human_confirmed")) is True
    )


EXPLORATION_CANDIDATES_FILE = "exploration_candidates.json"


def load_exploration_candidates(run: Path) -> tuple[dict[str, Any] | None, str | None]:
    """spec §6.1: explore 에이전트가 만든 탐색 방향 후보를 검증해
    (data, 강등 사유)로 돌려준다. 파일이 없거나 계약과 다르면 방향 옵션 없이
    기본 질문으로 강등한다 — 런타임 도입이 기존 흐름을 깨지 않는 안전판."""
    path = run / "outputs" / EXPLORATION_CANDIDATES_FILE
    if not path.exists():
        return None, "이번 탐색에서는 방향 후보 미리 보기가 준비되지 않아 기본 질문으로 진행합니다."
    data = load_json(path)
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "exploration_candidates.schema.json"
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None and schema_path.exists():
        try:
            jsonschema.validate(data, load_json(schema_path))
        except jsonschema.ValidationError:
            return None, "방향 후보 자료가 형식과 달라 기본 질문으로 진행합니다."
    else:
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not 2 <= len(candidates) <= 3:
            return None, "방향 후보 자료가 형식과 달라 기본 질문으로 진행합니다."
    return data, None


def direction_options_from(candidates_data: dict[str, Any]) -> list[dict[str, Any]]:
    """후보 → 라운드 1 방향 옵션. 불변식 I1: continue_pipeline은 무조건 false로
    생성한다 (spec §5.1)."""
    options: list[dict[str, Any]] = []
    for cand in (candidates_data.get("candidates") or [])[:3]:
        mini = cand.get("mini_result") if isinstance(cand.get("mini_result"), dict) else {}
        maps_to = dict(cand.get("maps_to") or {})
        maps_to["loop_action"] = "explore_direction"
        maps_to.setdefault("frame_focus", str(cand.get("id") or ""))
        maps_to["direction_id"] = str(cand.get("id") or "")
        options.append(
            {
                "id": f"explore_{cand.get('id')}",
                "label": str(cand.get("label") or cand.get("id")),
                "description": f"{mini.get('summary', '')} — 이 방향을 자세히 본 뒤 확정합니다.",
                "continue_pipeline": False,
                "maps_to": maps_to,
            }
        )
    return options


def find_answer_by_id(run: Path, answer_id: str) -> dict[str, Any] | None:
    if not answer_id:
        return None
    for item in load_answers_fail_closed(run):
        if str(item.get("answer_id")) == answer_id:
            return item
    return None


def candidate_by_direction(candidates_data: dict[str, Any] | None, direction_id: str) -> dict[str, Any] | None:
    if not candidates_data or not direction_id:
        return None
    for cand in candidates_data.get("candidates") or []:
        if str(cand.get("id")) == direction_id:
            return cand
    return None


def domain_interview_state(run: Path) -> tuple[list[str], set[str]]:
    """(readiness 공통 필수 중 아직 비어 있는 필드 목록, companion으로 답한 필드).

    '비어 있음' 판정은 주입/파생 domain_intake.json 값과 companion 답변 존재를
    합쳐 stage_guard.compute_domain_readiness와 같은 규칙으로 본다 (spec §8.3)."""
    injected = load_json(run / "input" / "domain_intake.json")
    answered: set[str] = set()
    for item in load_answers_fail_closed(run):
        if not item.get("companion_id"):
            continue
        field = str((item.get("maps_to") or {}).get("domain_field") or "")
        if field and str(item.get("user_response") or "").strip():
            answered.add(field)
    view: dict[str, Any] = {}
    for field in stage_guard.DOMAIN_REQUIRED_FIELDS:
        value = injected.get(field)
        filled = bool(str(value).strip()) if isinstance(value, str) else bool(value)
        view[field] = "확인됨" if (filled or field in answered) else None
    _, missing = stage_guard.compute_domain_readiness(view)
    return list(missing), answered


def domain_companions_for(run: Path, checkpoint_id: str) -> list[dict[str, Any]]:
    """spec §8.1/§8.3: 부족한 readiness 필수 필드 우선, 그다음 아직 답하지 않은
    정지점 매핑 필드 순으로 companion 질문 ≤2개를 결정적으로 고른다."""
    fields = CHECKPOINT_DOMAIN_FIELDS.get(checkpoint_id) or []
    if not fields or not stage_guard.domain_mode_active(run):
        return []
    missing, answered = domain_interview_state(run)
    ordered = [f for f in fields if f in missing]
    ordered += [f for f in fields if f not in missing and f not in answered]
    companions: list[dict[str, Any]] = []
    for field in ordered[:2]:
        header, text = DOMAIN_FIELD_QUESTIONS[field]
        companions.append(
            {
                "id": field,
                "question": text,
                "header": header,
                "allow_free_text": True,
                "maps_to": {"domain_field": field},
            }
        )
    return companions


def resolve_run_relative(run: Path, recorded: str) -> Path:
    """후보 파일의 경로 표기는 run-상대(`outputs/...`)가 기본이고 repo-상대도
    허용한다 — 존재하는 쪽을 택한다."""
    candidate = Path(recorded)
    if candidate.is_absolute():
        return candidate
    run_local = run / candidate
    return run_local if run_local.exists() else candidate


def update_manifest_block(run: Path, checkpoint_id: str, question_json: Path, question_md: Path) -> None:
    manifest_path = run / "manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {"run_id": run.name}
    stages = manifest.setdefault("stages", [])
    if not isinstance(stages, list):
        stages = []
        manifest["stages"] = stages
    stage_name = f"checkpoint:{checkpoint_id}"
    entry = {
        "name": stage_name,
        "status": "blocked_for_user_checkpoint",
        "outputs": [rel(question_json), rel(question_md)],
        "notes": ["human checkpoint answer is required before the next pipeline stage."],
    }
    replaced = False
    for idx, item in enumerate(stages):
        if isinstance(item, dict) and item.get("name") == stage_name:
            stages[idx] = entry
            replaced = True
            break
    if not replaced:
        stages.append(entry)
    write_json(manifest_path, manifest)


def update_manifest_pass(run: Path, checkpoint_id: str, answer: dict[str, Any]) -> None:
    manifest_path = run / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = load_json(manifest_path)
    stages = manifest.setdefault("stages", [])
    if not isinstance(stages, list):
        return
    stage_name = f"checkpoint:{checkpoint_id}"
    entry = {
        "name": stage_name,
        "status": "completed",
        "outputs": [rel(path) for path in answer_candidates(run) if path.exists()],
        "notes": [
            f"approved by {answer.get('source', 'unknown')} at {answer.get('answered_at', '')}",
            f"user_response: {str(answer.get('user_response', ''))[:160]}",
        ],
    }
    replaced = False
    for idx, item in enumerate(stages):
        if isinstance(item, dict) and item.get("name") == stage_name:
            stages[idx] = entry
            replaced = True
            break
    if not replaced:
        stages.append(entry)
    write_json(manifest_path, manifest)


def write_markdown(path: Path, question: dict[str, Any]) -> None:
    brief = question.get("user_review_brief") or {}
    lines = [
        f"# {question['header']}",
        "",
        "## 사용자용 검토 요약",
        "",
        f"### {brief.get('plain_title', question['header'])}",
        "",
        brief.get("why_this_checkpoint_matters", ""),
        "",
        "확인할 내용:",
        *[f"- {item}" for item in brief.get("what_user_should_review", [])],
        "",
        "승인하면 다음에 할 일:",
        *[f"- {item}" for item in brief.get("what_will_happen_next", [])],
        "",
        "이 단계에서 확정하지 않는 것:",
        *[f"- {item}" for item in brief.get("what_this_does_not_decide", [])],
        "",
        f"승인 질문: {brief.get('approval_question', question['question'])}",
        "",
        "## 채팅 질문",
        "",
        question.get("chat_prompt", build_chat_prompt(question)),
        "",
        "## 질문",
        "",
        question["question"],
        "",
        "## 선택지",
        "",
    ]
    recommended = question.get("recommended_option_id")
    for option in question.get("options", []):
        mark = " (Recommended)" if option.get("id") == recommended else ""
        gate = "진행" if option.get("continue_pipeline") else "수정 후 재확인"
        lines.extend(
            [
                f"- {option.get('label')}{mark}",
                f"  - {option.get('description')}",
                f"  - 게이트: {gate}",
            ]
        )
    evidence = collect_evidence(question)
    if evidence:
        lines.extend(["", "## 근거 (미리 본 결과 원문)", ""])
        for description, raw_path, snippet in evidence:
            lines.append(f"- {description} (`{raw_path}`)")
            if snippet:
                lines.append("")
                lines.extend(snippet.splitlines())
                lines.append("")
    companions = question.get("companion_questions") or []
    if companions:
        # 기록 명령은 checkpoint_id(내부 용어)를 포함하므로 사용자 구역이 아니라
        # '답변 반영'(기술 부록 뒤)에 둔다 — 언어 게이트 자기 차단 방지 (커밋 12d).
        lines.extend(
            [
                "",
                "## 추가 확인 질문 (선택)",
                "",
                "답하면 해석 기준에 반영되며, 단계 진행 여부와는 무관하다.",
                "",
            ]
        )
        for companion in companions:
            lines.append(f"- [{companion.get('header')}] {companion.get('question')}")
    lines.extend(
        [
            "",
            "## 기술 부록",
            "",
            f"- run_id: `{question['run_id']}`",
            f"- checkpoint_id: `{question['checkpoint_id']}`",
            f"- interview_style: `{question.get('interview_style', 'deep_interview_checkpoint')}`",
            "",
            "## 현재까지 확인된 내용",
            "",
            question["current_understanding"],
            "",
            "## 멈춘 결정",
            "",
            question["blocked_decision"],
            "",
            "## 추천 답안",
            "",
            question.get("recommended_answer", ""),
            "",
            "## 선택지 ID",
            "",
            *[
                f"- `{option.get('id')}`: {option.get('label')}"
                for option in question.get("options", [])
            ],
            "",
        ]
    )
    profiles = question.get("dashboard_design_profiles")
    if isinstance(profiles, dict):
        lines.extend(
            [
                "## 대시보드 스타일 선택지",
                "",
                "| 스타일 | 첫 화면 구성 | 적합한 경우 | 포기하는 점 |",
                "|---|---|---|---|",
            ]
        )
        for profile_id, profile in profiles.items():
            if isinstance(profile, dict):
                lines.append(
                    f"| {profile.get('label', profile_id)} | "
                    f"{profile.get('layout', '')} | {profile.get('best_for', '')} | "
                    f"{profile.get('tradeoff', '')} |"
                )
        lines.append("")
    lines.extend(
        [
            "## 참고 산출물",
            "",
        ]
    )
    for artifact in question.get("artifacts") or []:
        lines.append(f"- `{artifact['path']}`: {artifact['description']}")
    instructions = question.get("response_instructions") or {}
    lines.extend(
        [
            "",
            "## 답변 반영",
            "",
            "- 사용자 실제 답변 없이는 승인으로 인정하지 않는다. 에이전트 추천 답안을 그대로 넣어 자동 승인하지 않는다.",
            f"- 답변 파일: `{instructions.get('write_to', '')}`",
            f"- 반영 명령: `{instructions.get('apply_command', '')}`",
            f"- 재실행 명령: `{instructions.get('resume_command', '')}`",
        ]
    )
    if instructions.get("free_question_command"):
        lines.append(
            "- 직접 질문(단계당 1회): "
            f"`{instructions['free_question_command']}` — 기록 후 확인 결과를 보고 이어서 결정한다."
        )
    for companion in question.get("companion_questions") or []:
        lines.append(
            f"- 추가 확인 질문 [{companion.get('header')}] 기록: "
            f"`python3 scripts/apply_checkpoint_answer.py {question['run_id']} "
            f"{question['checkpoint_id']} --companion {companion.get('id')} "
            "--answer \"<답변>\" --source user_chat --user-response \"<답변>\" "
            "--transcript-ref \"<thread/message id>\"`"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def question_paths(run: Path, checkpoint_id: str, round_num: int = 1) -> tuple[Path, Path]:
    config = CHECKPOINTS[checkpoint_id]
    checkpoint_dir = run / "outputs" / "checkpoints"
    base = f"{config['order']}_{checkpoint_id}_question"
    if round_num >= 2:
        # 라운드 파일 분리는 provenance 요구(spec §4.1): 답변이 질문 파일을
        # sha256으로 고정하므로 라운드 2는 별도 불변 파일이어야 한다.
        base = f"{base}.round2"
    return checkpoint_dir / f"{base}.json", checkpoint_dir / f"{base}.md"


def load_existing_question(run_id: str, checkpoint_id: str) -> tuple[dict[str, Any], Path, Path]:
    run = Path("runs") / run_id
    for round_num in (2, 1):
        question_json, question_md = question_paths(run, checkpoint_id, round_num)
        if question_json.exists():
            return load_json(question_json), question_json, question_md
    question_json, _ = question_paths(run, checkpoint_id)
    raise SystemExit(f"checkpoint question JSON not found: {question_json}")


def collect_evidence(question: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    """질문의 근거 원문(미리 본 결과 표·직접 질문 확인 결과)을 (설명, 경로,
    내용 snippet)으로 수집한다 — 채팅 핸드오프와 질문 md가 같은 원문을 쓴다."""
    evidence_paths: list[tuple[str, str]] = []
    for item in question.get("artifacts") or []:
        if item.get("type") == "exploration_mini_result" and item.get("path"):
            evidence_paths.append((str(item.get("description") or "미리 본 결과"), str(item["path"])))
    loop_state_prior = (question.get("interview_loop") or {}).get("prior_round") or {}
    for raw in loop_state_prior.get("mini_result_paths") or []:
        if str(raw).endswith(".md") and all(str(raw) != p for _, p in evidence_paths):
            evidence_paths.append(("직접 질문 확인 결과", str(raw)))
    collected: list[tuple[str, str, str | None]] = []
    for description, raw_path in evidence_paths:
        evidence_file = Path(raw_path)
        snippet = read_text_snippet(evidence_file, max_lines=14) if evidence_file.exists() else None
        collected.append((description, raw_path, snippet))
    return collected


def render_question_for_chat(question: dict[str, Any], question_json: Path, question_md: Path) -> str:
    lines = [
        "",
        f"⏸ 사용자 확인이 필요합니다 (run-id: {question['run_id']})",
        "",
        "아래 질문에 답하면 다음 단계로 진행할지, 범위나 방향을 고칠지 결정할 수 있습니다.",
        "",
        question.get("chat_prompt", build_chat_prompt(question)),
        "",
        "선택지:",
    ]
    recommended = question.get("recommended_option_id")
    for option in question.get("options", []):
        mark = " (Recommended)" if option.get("id") == recommended else ""
        gate = "진행" if option.get("continue_pipeline") else "수정 후 재확인"
        lines.append(f"- {option.get('label')}{mark} [{gate}]")
        lines.append(f"  {option.get('description')}")
    lines.append("")
    lines.append("채팅창에는 선택지 이름이나 원하는 수정 방향을 그대로 답변하면 됩니다.")
    loop_state = question.get("interview_loop") if isinstance(question.get("interview_loop"), dict) else {}
    if not loop_state.get("free_question_used_this_round"):
        lines.append("데이터에 대해 궁금한 점을 직접 질문할 수도 있습니다(단계당 1회) — 확인 결과를 본 뒤 이어서 결정합니다.")
    companions = question.get("companion_questions") or []
    if companions:
        lines.append("")
        lines.append("추가로 확인하고 싶은 것(답하면 해석 기준에 반영, 진행 여부와는 무관):")
        for companion in companions:
            lines.append(f"- [{companion.get('header')}] {companion.get('question')}")
    if question.get("checkpoint_id") == "dashboard_storyboard":
        understanding = str(question.get("current_understanding") or "")
        marker = "[dashboard_layout 승인 원문]"
        if marker in understanding:
            layout_original = understanding.split(marker, 1)[1].strip()
            lines.extend(
                [
                    "",
                    "승인할 dashboard_layout 원문 (아래 구조를 보고 선택하세요):",
                    *layout_original.splitlines(),
                ]
            )
    # smoke 발견 수정: chat_prompt는 650자 압축을 거치며 근거 표가 탈락한다.
    # 사용자가 '내용을 모른 채' 선택하지 않도록, 미리 본 결과 원문을 핸드오프에
    # 그대로 내장한다 (표시 의무 — 링크·팝업 미리보기는 '보여준 것'이 아니다).
    evidence = collect_evidence(question)
    if evidence:
        lines.append("")
        lines.append("근거 (미리 본 결과 원문 — 아래 내용을 보고 선택하세요):")
        for description, raw_path, snippet in evidence:
            lines.append(f"- {description} ({raw_path})")
            if snippet:
                lines.extend(f"    {snippet_line}" for snippet_line in snippet.splitlines())
    lines.append("")
    instructions = question.get("response_instructions") or {}
    lines.extend(
        [
            "기술 정보:",
            f"- 질문 파일: {question_json}",
            f"- 요약 파일: {question_md}",
            f"- 답변 반영 명령: {instructions.get('apply_command', '')}",
            f"- 재실행 명령: {instructions.get('resume_command', '')}",
            "- 주의: 사용자 실제 답변을 --user-response에 넣고, 채팅/팝업 답변은 --transcript-ref도 남겨야 합니다.",
            "- 주의: 에이전트가 추천 답안이나 Plan Mode 승인 문구로 대신 승인하면 통과하지 않습니다.",
            "",
            "중단: 답변을 반영한 뒤 같은 명령으로 재실행하세요.",
        ]
    )
    return "\n".join(lines)


def record_handoff_print(question_json: Path) -> None:
    """핸드오프 원문 출력 사실을 스탬프로 남긴다 (전달 순서 규칙 — v4 smoke 발견).

    ask_user_question 답변 기록은 이 스탬프(같은 질문 sha256)가 선행해야
    통과한다 — 근거 원문 출력 없이 팝업만 띄우는 경로를 기계적으로 차단."""
    log_path = question_json.parent / "handoff_log.json"
    entries: list[dict[str, Any]] = []
    if log_path.exists():
        try:
            loaded = json.loads(log_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = loaded
        except (json.JSONDecodeError, OSError):
            entries = []
    entries.append(
        {
            "question_file": question_json.name,
            "question_sha256": hashlib.sha256(question_json.read_bytes()).hexdigest(),
            "printed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    log_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_question(question: dict[str, Any], question_json: Path, question_md: Path) -> None:
    record_handoff_print(question_json)
    print(render_question_for_chat(question, question_json, question_md))


def create_question(
    run_id: str,
    checkpoint_id: str,
    *,
    round_num: int = 1,
    prior_round: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    config = CHECKPOINTS[checkpoint_id]
    run = Path("runs") / run_id
    checkpoint_dir = run / "outputs" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    if round_num >= 3:
        raise SystemExit("추가 문답은 단계당 최대 2회입니다 — 라운드 3 질문은 만들 수 없습니다 (interview-loop-v2 D3).")
    if round_num >= 2 and not prior_round:
        raise SystemExit("라운드 2 질문에는 prior_round 정보가 필요합니다.")
    if checkpoint_id == "dashboard_storyboard":
        layout_path = run / "outputs" / "dashboard_layout.json"
        if layout_path.exists():
            layout_issues = validate_layout(load_json(layout_path))
            if layout_issues:
                details = "\n".join(f"- {issue}" for issue in layout_issues)
                raise SystemExit(
                    "dashboard_storyboard 질문 생성 전 dashboard_layout 검증에 "
                    f"실패했습니다. 레이아웃을 고친 뒤 다시 실행하세요.\n{details}"
                )
    understanding, snapshot, artifacts = current_understanding(run, checkpoint_id)
    question_json, question_md = question_paths(run, checkpoint_id, round_num)
    question = {
        "schema_version": "data-insight-kit.checkpoint_question.v2",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "blocked_for_user_checkpoint",
        "checkpoint_id": checkpoint_id,
        "checkpoint_kind": config["kind"],
        "header": config["header"],
        "interview_style": "deep_interview_checkpoint",
        "user_review_brief": copy.deepcopy(USER_REVIEW_BRIEFS[checkpoint_id]),
        "current_understanding": understanding,
        "data_snapshot": snapshot,
        "blocked_decision": config["blocked_decision"],
        "recommended_answer": config["recommended_answer"],
        "recommended_option_id": config["recommended_option_id"],
        "question": config["question"],
        "options": copy.deepcopy(config["options"]),
        "allow_free_text": True,
        "artifacts": artifacts,
        "response_instructions": {
            "mode": "checkpoint_answer",
            "write_to": f"runs/{run_id}/checkpoint_answers.json",
            "apply_command": (
                f"python3 scripts/apply_checkpoint_answer.py {run_id} {checkpoint_id} "
                "--option <option-id> --source user_chat "
                "--user-response \"<사용자 실제 답변>\" --transcript-ref \"<thread/message id>\""
            ),
            "resume_command": f"bash scripts/run_codex_pipeline.sh {run_id} --guided",
            "free_question_command": (
                f"python3 scripts/apply_checkpoint_answer.py {run_id} {checkpoint_id} "
                "--free-question \"<데이터에 대한 질문>\" --source user_chat "
                "--user-response \"<데이터에 대한 질문>\" --transcript-ref \"<thread/message id>\""
            ),
            "revision_rule": "continue_pipeline=false 답변은 다음 단계로 진행하지 않는다. 관련 산출물이나 입력을 수정한 뒤 다시 승인 답변을 남긴다.",
            "human_response_required": True,
            "allowed_sources": ["ask_user_question", "user_chat", "manual_cli"],
            "agent_assumption_rule": "agent_assumption source may record context but cannot continue the pipeline.",
        },
    }
    if checkpoint_id == "dashboard_storyboard":
        question["dashboard_design_profiles"] = copy.deepcopy(DASHBOARD_DESIGN_PROFILES)
        if round_num == 1:
            apply_dashboard_storyboard_recommendation(question, run)
    if checkpoint_id in APPROVAL_TARGET_FILES:
        targets = approval_targets_for(run, checkpoint_id)
        if targets:
            question["approval_targets"] = targets
    if checkpoint_id == "analysis_strategy":
        # 설치 승인이 필요한 run에서는 dependency 결정이 포함된 옵션으로 교체한다.
        dependency_variant = analysis_strategy_dependency_options(run)
        if dependency_variant is not None:
            options, recommended_answer = dependency_variant
            question["options"] = options
            question["recommended_option_id"] = "install_and_deepen"
            question["recommended_answer"] = recommended_answer
    if checkpoint_id == "dashboard_storyboard" and round_num == 1:
        # spec §5.4: 단순 run(조건부 1차 결과 확인 미발동)에서는 이 단계가 결과
        # 검토를 겸함을 명시하고 1차 결과 요약을 함께 보여준다 (v1 checklist §8
        # 미결 항목 흡수).
        if not stage_guard.review_predicate_required(run)[0]:
            analysis_path = run / "outputs" / "04_analysis.md"
            snippet = read_text_snippet(analysis_path, max_lines=12) if analysis_path.exists() else ""
            header = "이 확인 단계는 1차 분석 결과 검토를 겸합니다(별도 결과 확인 단계가 없는 분석)."
            if snippet:
                question["current_understanding"] = f"{header}\n\n1차 결과 요약:\n{snippet}\n\n{understanding}"
            else:
                question["current_understanding"] = f"{header}\n\n{understanding}"
    if checkpoint_id == "data_profile" and round_num == 1:
        # spec §5.1 탐색 문답: 후보가 유효하면 [바로 진행 + 방향 ≤3]으로 옵션을
        # 재구성한다(기존 수정/보강 의사는 자유 답변 경로로 흡수). 후보가 없거나
        # 계약과 다르면 기본 질문으로 강등하고 사유를 남긴다 (§6.1).
        candidates_data, exploration_note = load_exploration_candidates(run)
        directions = direction_options_from(candidates_data) if candidates_data else []
        if directions:
            base_option = next(
                (dict(opt) for opt in question["options"] if opt.get("continue_pipeline")),
                dict(question["options"][0]),
            )
            question["options"] = [base_option] + directions
            question["exploration"] = {
                "candidates_ref": rel(run / "outputs" / EXPLORATION_CANDIDATES_FILE),
                "free_question_slot": True,
            }
            question["question"] = (
                "현재 데이터로 바로 진행할까요, 아니면 궁금한 방향을 먼저 좁혀볼까요?"
            )
            for cand in candidates_data.get("candidates") or []:
                mini = cand.get("mini_result") if isinstance(cand.get("mini_result"), dict) else {}
                table_path = str(mini.get("table_path") or "")
                if table_path:
                    question["artifacts"].append(
                        {
                            "path": rel(resolve_run_relative(run, table_path)),
                            "type": "exploration_mini_result",
                            "description": f"'{cand.get('label')}' 방향 미리 본 결과 표",
                        }
                    )
        elif exploration_note:
            question["current_understanding"] = f"{understanding}\n\n{exploration_note}"
    domain_companions = domain_companions_for(run, checkpoint_id)
    if domain_companions:
        question["companion_questions"] = domain_companions
    interview_loop: dict[str, Any] = {
        "round": round_num,
        "max_rounds": 2,
        "free_question_used_this_round": free_question_count(run, checkpoint_id, round_num) > 0,
        "max_free_questions_per_round": 1,
        "finalization_rule": "충분함·진행 옵션을 선택하면 이 단계가 확정됩니다. 추가 문답은 단계당 최대 2회까지만 이어집니다.",
    }
    if round_num >= 2 and prior_round:
        interview_loop["prior_round"] = prior_round
        # 라운드 2는 '추가 확인 후 확정' 질문으로 교체한다 (spec §4.4).
        question["question"] = "추가로 확인한 내용을 반영해 이 단계를 확정하고 진행해도 될까요?"
        question["options"] = ROUND2_OPTIONS
        question["recommended_option_id"] = "confirm_and_continue"
        question["recommended_answer"] = (
            "확인한 내용이 목적과 맞으면 진행을 확정한다. 다르면 수정을 선택해 산출물을 고친 뒤 다시 확인한다."
        )
        question["blocked_decision"] = "직전 문답에서 확인한 내용을 반영해 이 단계를 확정할지 결정해야 한다."
        question["response_instructions"]["apply_command"] = (
            f"python3 scripts/apply_checkpoint_answer.py {run_id} {checkpoint_id} "
            f"--question-file {rel(question_json)} --option <option-id> --source user_chat "
            "--user-response \"<사용자 실제 답변>\" --transcript-ref \"<thread/message id>\""
        )
        if prior_round.get("trigger") == "domain_readiness_gap":
            # spec §8.3 / §9 트리거 (b): 부족한 업무 기준을 사용자 표현으로 보여주는
            # 재확인형 질문. companion은 domain_companions_for가 부족 필드 우선으로
            # 이미 채웠다.
            missing, _ = domain_interview_state(run)
            labels = [DOMAIN_FIELD_QUESTIONS[f][0] for f in missing if f in DOMAIN_FIELD_QUESTIONS]
            question["question"] = "업무 기준을 조금 더 확인한 뒤 이 단계를 확정할까요?"
            question["recommended_answer"] = (
                "추가 확인 질문에 답하면 해석 기준이 정확해진다. 지금 답하기 어려우면 "
                "확인된 기준까지만 반영해 진행할 수 있다(그 경우 강한 결론은 제한된다)."
            )
            question["blocked_decision"] = "부족한 업무 기준을 보완할지, 확인된 기준까지만 반영해 진행할지 결정해야 한다."
            if labels:
                question["current_understanding"] = (
                    f"{question['current_understanding']}\n\n아직 확인되지 않은 업무 기준: {', '.join(labels)}"
                )
        if checkpoint_id == "dashboard_storyboard" and prior_round.get("trigger") == "artifact_revision":
            revision = load_json(run / "outputs" / "dashboard_layout.json").get("revision")
            question["question"] = (
                f"QA에서 발견한 구조 문제를 반영한 화면 구성 revision {revision}을 "
                "다시 승인하고 진행해도 될까요?"
            )
            question["recommended_answer"] = (
                "표시된 변경 이유와 개정 레이아웃이 의도에 맞으면 진행을 확정한다. "
                "다르면 수정을 선택해 화면 구조를 다시 고친다."
            )
            question["blocked_decision"] = (
                "기존 승인 뒤 QA에서 필요해진 화면 구조 변경을 새 hash로 다시 확정해야 한다."
            )
        if checkpoint_id == "data_profile" and prior_round.get("trigger") == "explore_direction":
            # spec §5.1 라운드 2: 선택한 방향의 미니 결과를 내장하고 확정 옵션에
            # frame_focus를 실어 frame 입력 계약을 만든다.
            trigger_answer = find_answer_by_id(run, str(prior_round.get("answer_id") or ""))
            trigger_maps = (trigger_answer or {}).get("maps_to") or {}
            direction_id = str(trigger_maps.get("direction_id") or trigger_maps.get("frame_focus") or "")
            candidates_data, _ = load_exploration_candidates(run)
            candidate = candidate_by_direction(candidates_data, direction_id)
            if candidate:
                mini = candidate.get("mini_result") if isinstance(candidate.get("mini_result"), dict) else {}
                focus = str((candidate.get("maps_to") or {}).get("frame_focus") or direction_id)
                label = str(candidate.get("label") or direction_id)
                question["question"] = f"'{label}' 방향으로 분석을 확정하고 진행해도 될까요?"
                question["options"] = [
                    {
                        "id": "confirm_direction",
                        "label": "이 방향으로 확정",
                        "description": f"{mini.get('summary', '')} — 이 방향을 분석 질문과 비교 기준에 반영해 진행한다.",
                        "recommended": True,
                        "continue_pipeline": True,
                        "maps_to": {"checkpoint_decision": "approved", "frame_focus": focus},
                    },
                    {
                        "id": "choose_other_direction",
                        "label": "방향 다시 선택",
                        "description": "이 방향이 아닌 다른 방향이나 질문으로 다시 좁힌다.",
                        "continue_pipeline": False,
                        "maps_to": {"checkpoint_decision": "revise"},
                    },
                ]
                question["recommended_option_id"] = "confirm_direction"
                question["recommended_answer"] = (
                    f"미리 본 결과가 궁금증과 맞으면 '{label}' 방향으로 확정한다. 다르면 방향을 다시 고른다."
                )
                table_path = str(mini.get("table_path") or "")
                if table_path:
                    table_file = resolve_run_relative(run, table_path)
                    if table_file.exists():
                        snippet = read_text_snippet(table_file, max_lines=14)
                        question["current_understanding"] = (
                            f"{question['current_understanding']}\n\n'{label}' 방향 미리 본 결과:\n{snippet}"
                        )
                        question["artifacts"].append(
                            {
                                "path": rel(table_file),
                                "type": "exploration_mini_result",
                                "description": f"'{label}' 방향 미리 본 결과 표",
                            }
                        )
    question["interview_loop"] = interview_loop
    question["chat_prompt"] = build_chat_prompt(question)
    write_json(question_json, question)
    write_markdown(question_md, question)
    update_manifest_block(run, checkpoint_id, question_json, question_md)
    return question, question_json, question_md


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce a data-insight-kit human checkpoint.")
    parser.add_argument("run_id")
    parser.add_argument("checkpoint_id", choices=sorted(CHECKPOINTS))
    parser.add_argument("--dry-run", action="store_true", help="Print intended checkpoint behavior without writing files.")
    parser.add_argument("--auto", action="store_true", help="Skip this checkpoint explicitly.")
    parser.add_argument("--quiet", action="store_true", help="Do not print the chat handoff when creating a question.")
    parser.add_argument("--print-existing", action="store_true", help="Print an existing checkpoint question as a chat handoff and exit.")
    args = parser.parse_args()

    run = Path("runs") / args.run_id
    if args.print_existing:
        question, question_json, question_md = load_existing_question(args.run_id, args.checkpoint_id)
        print_question(question, question_json, question_md)
        return 0
    if args.auto:
        print(f"⏭ checkpoint skipped by --auto: {args.checkpoint_id}")
        return 0
    if args.dry_run:
        print(f"    checkpoint gate: {args.checkpoint_id} would require an approved answer or create question artifacts")
        return 0

    answer = latest_answer(run, args.checkpoint_id)
    if answer:
        if bool(answer.get("continue_pipeline")):
            # Require the SAME v3 provenance that stage_guard/qa require, not just
            # is_human_confirmed(). Otherwise a self-authored answer (no
            # recorded_by / answer_id / question_ref / approval_contract_version)
            # would pass the gate here and only fail later at the next stage_guard.
            provenance_issues = stage_guard.validate_answer(run, args.checkpoint_id, answer)
            if not is_human_confirmed(answer) or provenance_issues:
                question, question_json, question_md = create_question(args.run_id, args.checkpoint_id)
                print("")
                print(f"✋ checkpoint answer rejected: {args.checkpoint_id}")
                print("이전 답변은 사용자 실제 답변으로 확인되지 않았거나 승인 provenance가 부족합니다.")
                print("필수 조건: scripts/apply_checkpoint_answer.py로 기록한 checkpoint-answer.v3 답변")
                print("(source=user_chat|ask_user_question|manual_cli, human_confirmed=true, user_response,")
                print(" recorded_by, answer_id, question_ref 일치, user_chat/ask_user_question은 transcript_ref).")
                for issue in provenance_issues:
                    print(f"- {issue}")
                if not args.quiet:
                    print_question(question, question_json, question_md)
                return 3
            if args.checkpoint_id == "dashboard_storyboard":
                lock_issues = stage_guard.dashboard_layout_lock_issues(run, answer)
                if lock_issues:
                    qpath, chain_issues = stage_guard.resolve_answer_question(
                        run, args.checkpoint_id, answer
                    )
                    if chain_issues or not qpath.exists():
                        print("✋ 기존 storyboard 승인 질문 체인을 확인할 수 없습니다.")
                        for issue in chain_issues:
                            print(f"- {issue}")
                        return 4
                    old_question = load_json(qpath)
                    old_target = (old_question.get("approval_targets") or {}).get(
                        "dashboard_layout"
                    ) or {}
                    current_layout = load_json(run / "outputs" / "dashboard_layout.json")
                    old_revision = int(old_target.get("revision") or 0)
                    current_revision = int(current_layout.get("revision") or 0)
                    if current_revision <= old_revision:
                        print("✋ 승인 뒤 layout hash가 바뀌었지만 revision이 증가하지 않았습니다.")
                        print(
                            f"- 승인 revision={old_revision}, 현재 revision={current_revision}; "
                            "revision을 올린 뒤 재승인 질문을 만드세요."
                        )
                        return 4
                    if int(answer.get("interview_round") or 1) >= 2:
                        print("⛔ 추가 문답 상한(단계당 2회) 도달: dashboard_storyboard")
                        print("round 2 승인 뒤에는 같은 checkpoint에서 새 구조 변경을 승인할 수 없습니다.")
                        return 4
                    q2_json, q2_md = question_paths(run, args.checkpoint_id, 2)
                    if q2_json.exists():
                        question = load_json(q2_json)
                        q2_target = (question.get("approval_targets") or {}).get(
                            "dashboard_layout"
                        ) or {}
                        if (
                            q2_target.get("sha256")
                            != stage_guard.sha256_file(run / "outputs" / "dashboard_layout.json")
                            or q2_target.get("revision") != current_revision
                        ):
                            print("⛔ 이미 만든 round 2 질문과 현재 layout이 다시 달라졌습니다.")
                            print("질문 파일은 덮어쓰지 않습니다. 화면 구조를 확정한 뒤 새 run을 사용하세요.")
                            return 4
                    else:
                        prior_round = {
                            "question_path": rel(qpath),
                            "question_sha256": stage_guard.sha256_file(qpath),
                            "answer_id": str(answer.get("answer_id") or ""),
                            "trigger": "artifact_revision",
                        }
                        question, q2_json, q2_md = create_question(
                            args.run_id,
                            args.checkpoint_id,
                            round_num=2,
                            prior_round=prior_round,
                        )
                    print("")
                    print("🔁 QA 구조 수정 재승인(2회차): dashboard_storyboard")
                    for issue in lock_issues:
                        print(f"- {issue}")
                    if not args.quiet:
                        print_question(question, q2_json, q2_md)
                    return 3
            update_manifest_pass(run, args.checkpoint_id, answer)
            print(f"✅ checkpoint approved: {args.checkpoint_id} ({answer.get('selected_option_id') or 'free-text'})")
            return 0
        loop_action = answer.get("loop_action") or (answer.get("maps_to") or {}).get("loop_action")
        if loop_action in MAIN_LOOP_ACTIONS:
            # interview-loop-v2 §4.4/§9 트리거 (a): 주 질문 답변의 loop_action.
            ref_sha = str((answer.get("question_ref") or {}).get("sha256") or "")
            answer_id = str(answer.get("answer_id") or "")
            q1_json, _ = question_paths(run, args.checkpoint_id, 1)
            q2_json, _ = question_paths(run, args.checkpoint_id, 2)
            r1_sha = question_file_sha256(q1_json)
            if r1_sha and answer_id and ref_sha == r1_sha:
                prior_round: dict[str, Any] = {
                    "question_path": rel(q1_json),
                    "question_sha256": r1_sha,
                    "answer_id": answer_id,
                    "trigger": str(loop_action),
                }
                minis = mini_result_paths_for(run, args.checkpoint_id, answer_id)
                if minis:
                    prior_round["mini_result_paths"] = minis
                question, question_json, question_md = create_question(
                    args.run_id, args.checkpoint_id, round_num=2, prior_round=prior_round
                )
                print("")
                print(f"🔁 추가 문답 (2회차): {args.checkpoint_id}")
                print("직전 답변(방향 선택 또는 직접 질문)을 반영한 확인 질문을 만들었습니다.")
                if not args.quiet:
                    print_question(question, question_json, question_md)
                return 3
            r2_sha = question_file_sha256(q2_json)
            if r2_sha and ref_sha == r2_sha:
                print("")
                print(f"⛔ 추가 문답 상한(단계당 2회) 도달: {args.checkpoint_id}")
                print("이 단계의 문답은 소진되었습니다. 승인 옵션으로 확정하거나, 산출물을 수정한 뒤 승인 답변을 다시 남겨주세요.")
                return 4
            print("")
            print(f"✋ 이전 문답 답변이 현재 질문 파일과 연결되지 않습니다: {args.checkpoint_id}")
            print("질문이 재생성되어 이전 답변은 고아 레코드가 되었습니다. 현재 질문에 다시 답해주세요.")
            return 4
        print("")
        print(f"✋ checkpoint revision requested: {args.checkpoint_id}")
        print(f"answer: {answer.get('answer', '')}")
        print("이 답변은 다음 단계 진행을 허용하지 않습니다. 관련 산출물이나 입력을 수정한 뒤 승인 답변을 다시 남겨주세요.")
        return 4

    # 결정 레코드가 없는 상태 — spec §9 트리거 (b): domain mode에서 현재 R1에 대한
    # companion 답변이 있고 readiness 공통 필수 필드가 남아 있으면, R1을 재생성하는
    # 대신 재확인형 라운드 2를 만든다.
    if stage_guard.domain_mode_active(run):
        q1_json, _ = question_paths(run, args.checkpoint_id, 1)
        r1_sha = question_file_sha256(q1_json)
        if r1_sha:
            companion_answers = [
                item
                for item in load_answers_fail_closed(run)
                if item.get("checkpoint_id") == args.checkpoint_id
                and item.get("companion_id")
                and str((item.get("question_ref") or {}).get("sha256") or "") == r1_sha
            ]
            missing, _ = domain_interview_state(run)
            relevant = [f for f in CHECKPOINT_DOMAIN_FIELDS.get(args.checkpoint_id, []) if f in missing]
            if companion_answers and relevant:
                last_companion = companion_answers[-1]
                prior_round = {
                    "question_path": rel(q1_json),
                    "question_sha256": r1_sha,
                    "answer_id": str(last_companion.get("answer_id") or ""),
                    "trigger": "domain_readiness_gap",
                }
                question, question_json, question_md = create_question(
                    args.run_id, args.checkpoint_id, round_num=2, prior_round=prior_round
                )
                print("")
                print(f"🔁 추가 문답 (2회차, 업무 기준 보완): {args.checkpoint_id}")
                if not args.quiet:
                    print_question(question, question_json, question_md)
                return 3

    question, question_json, question_md = create_question(args.run_id, args.checkpoint_id)
    if not args.quiet:
        print_question(question, question_json, question_md)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
