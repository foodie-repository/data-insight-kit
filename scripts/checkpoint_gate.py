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
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    "dashboard_storyboard": {
        "order": "03",
        "kind": "storyboard_review",
        "header": "대시보드 구성 확인",
        "question_file": "03_dashboard_storyboard_question",
        "recommended_option_id": "approve_storyboard",
        "blocked_decision": "어떤 데이터/지표로 어떤 차트를 만들지, 그리고 그 차트가 사용자 판단에 맞는지 확인해야 한다.",
        "recommended_answer": "차트 추천표의 데이터/지표, 비교 기준, 추천 차트, 대안/보류 이유가 의도와 맞으면 구성 승인으로 진행한다. 원하는 판단과 맞지 않으면 차트 구성 수정을 선택한다.",
        "question": "이 데이터/지표와 차트 추천 구성으로 최종 대시보드를 만들어도 될까요?",
        "options": [
            {
                "id": "approve_storyboard",
                "label": "구성 승인",
                "description": "현재 데이터/지표, 비교 기준, 추천 차트, 분석 메시지를 유지하고 대시보드 화면 생성으로 넘어간다.",
                "recommended": True,
                "continue_pipeline": True,
                "maps_to": {"checkpoint_decision": "approved"},
            },
            {
                "id": "revise_chart_mix",
                "label": "차트 구성 수정",
                "description": "사용할 데이터/지표, 비교 기준, 차트 종류, 탭 순서, 강조 메시지를 다시 조정한다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "revise_chart_spec"},
            },
            {
                "id": "deepen_chart_story",
                "label": "내용·차트 모두 심화",
                "description": "단순 순위·요약이 많으면 질문별 차트, 비교축, 예외/관계 분석을 보강해 구성안을 다시 만든다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "rebuild_storyboard_for_insight"},
            },
            {
                "id": "make_publish_ready",
                "label": "배포용으로 다듬기",
                "description": "내부 분석 용어를 줄이고 독자가 바로 읽을 수 있는 제목·문장·차트 흐름으로 고친다.",
                "continue_pipeline": False,
                "maps_to": {"checkpoint_decision": "rewrite_for_audience"},
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
    "dashboard_storyboard": {
        "plain_title": "대시보드와 보고서의 흐름을 정하는 단계",
        "why_this_checkpoint_matters": "최종 화면을 만들기 전에 어떤 데이터와 지표를 어떤 차트로 보여줄지 확인해야 단순 순위표 반복을 피할 수 있다.",
        "what_user_should_review": [
            "각 차트가 사용할 데이터와 지표가 원하는 판단 흐름과 맞는지",
            "추천 차트와 대안 차트의 이유가 납득되는지",
            "추천 구성안과 대안 구성안 중 어떤 흐름이 더 좋은지",
        ],
        "what_will_happen_next": [
            "승인하면 최종 대시보드 화면을 만든다.",
            "수정하면 사용할 데이터/지표, 차트 종류, 탭 흐름, 메시지를 바꾼 뒤 다시 확인한다.",
        ],
        "what_this_does_not_decide": [
            "새 데이터를 자동으로 추가하지 않는다.",
            "데이터 한계를 넘어서는 추천이나 수익성 결론을 만들지 않는다.",
        ],
        "approval_question": "이 데이터/지표와 차트 추천 구성으로 최종 대시보드를 만들어도 될까요?",
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


def source_files(run: Path) -> list[Path]:
    input_dir = run / "input"
    if not input_dir.exists():
        return []
    allowed = {".csv", ".tsv", ".json", ".jsonl", ".parquet"}
    files = [p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in allowed]
    return sorted(files)[:20]


def write_csv_preview(source: Path, target: Path, delimiter: str = ",", limit: int = 20) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as inp:
        reader = csv.reader(inp, delimiter=delimiter)
        rows = []
        for idx, row in enumerate(reader):
            rows.append(row)
            if idx >= limit:
                break
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
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
    target.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def write_parquet_preview(source: Path, target: Path, limit: int = 20) -> bool:
    try:
        import polars as pl  # type: ignore
    except Exception:
        return False
    try:
        df = pl.scan_parquet(str(source)).limit(limit).collect()
        df.write_csv(str(target))
    except Exception:
        return False
    return True


def build_data_preview(run: Path, checkpoint_dir: Path, notes: list[str]) -> str | None:
    for source in source_files(run):
        suffix = source.suffix.lower()
        if suffix == ".csv":
            target = checkpoint_dir / "data_preview.csv"
            if write_csv_preview(source, target):
                notes.append(f"{source}에서 최대 20행 샘플을 추출했다.")
                return rel(target)
        if suffix == ".tsv":
            target = checkpoint_dir / "data_preview.csv"
            if write_csv_preview(source, target, delimiter="\t"):
                notes.append(f"{source}에서 최대 20행 TSV 샘플을 CSV로 추출했다.")
                return rel(target)
        if suffix in {".json", ".jsonl"}:
            target = checkpoint_dir / f"data_preview{suffix}"
            if write_json_preview(source, target):
                notes.append(f"{source}에서 제한된 JSON 샘플을 추출했다.")
                return rel(target)
        if suffix == ".parquet":
            target = checkpoint_dir / "data_preview.csv"
            if write_parquet_preview(source, target):
                notes.append(f"{source}에서 최대 20행 Parquet 샘플을 CSV로 추출했다.")
                return rel(target)
            notes.append(f"{source}는 Parquet 샘플 추출 환경이 없어 profile/EDA 요약으로 대체한다.")
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
    review_text = " / ".join(str(item) for item in review_items[:3])
    current_summary = " ".join(
        part
        for part in [
            str(brief.get("plain_title", "")).strip(),
            str(brief.get("why_this_checkpoint_matters", "")).strip(),
        ]
        if part
    )
    return "\n".join(
        [
            f"현재 이해: {compact_for_chat(current_summary or question.get('current_understanding', ''))}",
            f"확인할 내용: {review_text}" if review_text else "",
            f"막힌 결정: {question.get('blocked_decision', '')}",
            f"추천 답안: {question.get('recommended_answer', '')}",
            f"질문: {question.get('question', '')}",
        ]
    ).replace("\n\n", "\n")


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
        summary = "\n\n".join(["[03_frame 요약]", read_text_snippet(frame, 36)])
        artifacts.append({"path": rel(frame), "type": "frame", "description": "문제 정의, KPI, 분석 전략"})
        return summary, None, artifacts

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
    summary = "\n\n".join(
        [
            "[04_analysis 요약]",
            read_text_snippet(analysis, 30),
            "[chart_spec 요약]",
            chart_spec_summary(chart_spec),
        ]
    )
    artifacts.extend(
        [
            {"path": rel(analysis), "type": "analysis", "description": "분석 결과와 대시보드 메시지"},
            {"path": rel(chart_spec), "type": "chart_spec", "description": "차트 설계와 대시보드 매핑"},
        ]
    )
    return summary, None, artifacts


def answer_candidates(run: Path) -> list[Path]:
    return [run / "checkpoint_answers.json", run / "input" / "checkpoint_answers.json"]


def latest_answer(run: Path, checkpoint_id: str) -> dict[str, Any] | None:
    answers: list[dict[str, Any]] = []
    for path in answer_candidates(run):
        data = load_json(path)
        raw = data.get("answers") if isinstance(data, dict) else None
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and item.get("checkpoint_id") == checkpoint_id:
                    answers.append(item)
    return answers[-1] if answers else None

def is_human_confirmed(answer: dict[str, Any]) -> bool:
    source = answer.get("source")
    user_response = str(answer.get("user_response") or "").strip()
    return (
        source in HUMAN_CONFIRMATION_SOURCES
        and bool(user_response)
        and bool(answer.get("human_confirmed")) is True
    )


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
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def print_question(question: dict[str, Any], question_json: Path, question_md: Path) -> None:
    print("")
    print(f"⏸ 사용자 체크포인트 필요 (run-id: {question['run_id']})")
    print(f"질문 파일: {question_json}")
    print(f"요약 파일: {question_md}")
    print("")
    print("채팅 질문:")
    print(question.get("chat_prompt", build_chat_prompt(question)))
    print("")
    print("선택지:")
    recommended = question.get("recommended_option_id")
    for option in question.get("options", []):
        mark = " (Recommended)" if option.get("id") == recommended else ""
        gate = "진행" if option.get("continue_pipeline") else "수정 후 재확인"
        print(f"- {option.get('label')}{mark} [{gate}]")
        print(f"  {option.get('description')}")
    print("")
    instructions = question.get("response_instructions") or {}
    print(f"답변 반영 명령: {instructions.get('apply_command', '')}")
    print(f"재실행 명령: {instructions.get('resume_command', '')}")
    print("주의: 사용자 실제 답변을 --user-response에 넣어야 하며, 에이전트가 추천 답안으로 대신 승인하면 통과하지 않습니다.")
    print("중단: 답변을 반영한 뒤 같은 명령으로 재실행하세요.")


def create_question(run_id: str, checkpoint_id: str) -> tuple[dict[str, Any], Path, Path]:
    config = CHECKPOINTS[checkpoint_id]
    run = Path("runs") / run_id
    checkpoint_dir = run / "outputs" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    understanding, snapshot, artifacts = current_understanding(run, checkpoint_id)
    base = f"{config['order']}_{checkpoint_id}_question"
    question_json = checkpoint_dir / f"{base}.json"
    question_md = checkpoint_dir / f"{base}.md"
    question = {
        "schema_version": "data-insight-kit.checkpoint_question.v1",
        "run_id": run_id,
        "status": "blocked_for_user_checkpoint",
        "checkpoint_id": checkpoint_id,
        "checkpoint_kind": config["kind"],
        "header": config["header"],
        "interview_style": "deep_interview_checkpoint",
        "user_review_brief": USER_REVIEW_BRIEFS[checkpoint_id],
        "current_understanding": understanding,
        "data_snapshot": snapshot,
        "blocked_decision": config["blocked_decision"],
        "recommended_answer": config["recommended_answer"],
        "recommended_option_id": config["recommended_option_id"],
        "question": config["question"],
        "options": config["options"],
        "allow_free_text": True,
        "artifacts": artifacts,
        "response_instructions": {
            "mode": "checkpoint_answer",
            "write_to": f"runs/{run_id}/checkpoint_answers.json",
            "apply_command": (
                f"python3 scripts/apply_checkpoint_answer.py {run_id} {checkpoint_id} "
                "--option <option-id> --source user_chat --user-response \"<사용자 실제 답변>\""
            ),
            "resume_command": f"bash scripts/run_codex_pipeline.sh {run_id} --guided",
            "revision_rule": "continue_pipeline=false 답변은 다음 단계로 진행하지 않는다. 관련 산출물이나 입력을 수정한 뒤 다시 승인 답변을 남긴다.",
            "human_response_required": True,
            "allowed_sources": ["ask_user_question", "user_chat", "manual_cli"],
            "agent_assumption_rule": "agent_assumption source may record context but cannot continue the pipeline.",
        },
    }
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
    args = parser.parse_args()

    run = Path("runs") / args.run_id
    if args.auto:
        print(f"⏭ checkpoint skipped by --auto: {args.checkpoint_id}")
        return 0
    if args.dry_run:
        print(f"    checkpoint gate: {args.checkpoint_id} would require an approved answer or create question artifacts")
        return 0

    answer = latest_answer(run, args.checkpoint_id)
    if answer:
        if bool(answer.get("continue_pipeline")):
            if not is_human_confirmed(answer):
                question, question_json, question_md = create_question(args.run_id, args.checkpoint_id)
                print("")
                print(f"✋ checkpoint answer rejected: {args.checkpoint_id}")
                print("이전 답변은 사용자 실제 답변으로 확인되지 않았습니다.")
                print("필수 조건: source=user_chat|ask_user_question|manual_cli, human_confirmed=true, user_response 존재.")
                print_question(question, question_json, question_md)
                return 3
            update_manifest_pass(run, args.checkpoint_id, answer)
            print(f"✅ checkpoint approved: {args.checkpoint_id} ({answer.get('selected_option_id') or 'free-text'})")
            return 0
        print("")
        print(f"✋ checkpoint revision requested: {args.checkpoint_id}")
        print(f"answer: {answer.get('answer', '')}")
        print("이 답변은 다음 단계 진행을 허용하지 않습니다. 관련 산출물이나 입력을 수정한 뒤 승인 답변을 다시 남겨주세요.")
        return 4

    question, question_json, question_md = create_question(args.run_id, args.checkpoint_id)
    print_question(question, question_json, question_md)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
