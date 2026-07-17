#!/usr/bin/env python3
"""Validate reader-facing planning/checkpoint text.

This is a narrow guard for fields shown to non-technical users before they
approve analysis direction. It intentionally allows internal terms in technical
appendices, but blocks them in `user_analysis_brief`, `user_review_brief`, and
markdown text before the "기술 부록" section.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


FORBIDDEN_TERMS = {
    "data_profile": "데이터 확인 단계",
    "analysis_strategy": "분석 방향 확인 단계",
    "dashboard_storyboard": "대시보드 구성안 확인 단계",
    "report_outline": "보고서 구성 확인 단계",
    "source_ref": "출처 또는 근거",
    "chart_spec": "차트 구성안",
    "chart_recommendation": "차트 추천",
    "metric_layer": "지표 성격",
    "selected_categories": "선택한 보정 데이터",
    "qa-post": "최종 보고서 검증",
    "source_api_manifest": "API 수집 계획",
    "checkpoint_question": "중간 확인 질문",
    "qa/validate.py": "품질 검증",
    "storyboard": "구성안",
    "dashboard_data.json": "대시보드 데이터",
    "dashboard.html": "대시보드 화면",
    "KPI": "핵심 지표",
    "method_route": "분석 깊이와 방법 선택",
    "dependency_plan": "추가 분석 기능 준비",
    "domain_readiness": "도메인 기준 확인 상태",
    "domain_intake": "도메인 전문가 확인 정보",
    "analysis_result_review": "1차 결과 확인 단계",
    "descriptive": "기본 현황 분석",
    "diagnostic": "차이·예외 진단 분석",
    "statistical": "통계적 확인 분석",
    "ml_exploratory": "패턴·군집 탐색 분석",
    "predictive": "예측 후보 분석",
    "causal_experiment": "전후·실험 비교 분석",
    "interview_loop": "탐색 문답",
    "exploration_candidates": "볼 만한 방향 후보",
    "companion_question": "추가 확인 질문",
    "free_question": "직접 질문",
    "mini_result": "미리 본 결과",
    "loop_action": "문답 진행 정보",
    "frame_focus": "선택한 분석 방향",
}

FORBIDDEN_PHRASES = {
    "실행을 시작하면 위 선택지를 먼저 묻고": "사용자가 바로 고를 수 있는 승인 질문",
    "이전 계획은 취소": "최신 기준으로 제안합니다",
    "이전 계획을 취소": "최신 기준으로 제안합니다",
    "선택된 방향:": "승인 전에는 '추천 방향' 또는 '우선 제안하는 방향'",
    "현황·리스크 진단": "분모가 없으면 '분포·집중도 진단' 또는 '구조 진단'",
    "위험 점검": "분모가 없으면 '주의 신호 확인' 또는 '구조 진단'",
    "안전도 평가": "인구 보정 등 분모가 있을 때만 별도 한계와 함께 사용",
    "시작월": "실제 비교 시작 시점(예: 2022-01)",
    "끝월": "실제 비교 종료 시점(예: 2026-06)",
    "최근 끝점": "실제 최근 시점(예: 2026-06)",
    "기간 가격": "실제 기간과 집계 의미(예: 2022-01~2026-06 월별 중앙가격)",
    "가격 단위 미확인": "근거를 확인한 독자용 통화 단위 또는 해당 수치 제외",
    "가격 단위 후보": "근거를 확인한 독자용 통화 단위 또는 해당 수치 제외",
    "원천 단위": "독자가 이해할 수 있는 실제 단위",
}

TECHNICAL_SECTION_MARKERS = (
    "\n## 기술 부록",
    "\n# 기술 부록",
    "\n기술 부록",
    "\n## 내부 실행 계획",
    "\n# 내부 실행 계획",
    "\n내부 실행 계획",
)

USER_FACING_KEYS = {"user_analysis_brief", "user_review_brief"}

USER_PLAN_ANCHORS = (
    "사용자용 분석 기획안",
    "이번 분석은 이렇게 진행합니다",
    "한 줄 목적",
)

TECHNICAL_PLAN_HEADINGS = (
    "## Summary",
    "## Key Changes",
    "## Pipeline",
    "## Test Plan",
    "## Assumptions",
)


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def user_facing_json_strings(data: Any) -> Iterable[tuple[str, str]]:
    if isinstance(data, dict):
        for key, value in data.items():
            if key in USER_FACING_KEYS:
                for text in iter_strings(value):
                    yield key, text
            else:
                yield from user_facing_json_strings(value)
    elif isinstance(data, list):
        for item in data:
            yield from user_facing_json_strings(item)


def markdown_user_section(text: str) -> str:
    end = len(text)
    for marker in TECHNICAL_SECTION_MARKERS:
        idx = text.find(marker)
        if idx >= 0:
            end = min(end, idx)
    return text[:end]


def validate_text(label: str, text: str, issues: list[str]) -> None:
    lowered = text.lower()
    for term, replacement in FORBIDDEN_TERMS.items():
        if term.lower() in lowered:
            issues.append(f"{label}: internal term '{term}' -> use '{replacement}'")
    for phrase, replacement in FORBIDDEN_PHRASES.items():
        if phrase in text:
            issues.append(f"{label}: reader-facing phrase '{phrase}' -> use '{replacement}'")


def validate_plan_shape(label: str, text: str, issues: list[str]) -> None:
    """Block developer-plan templates before the user-facing analysis brief."""
    user_section = markdown_user_section(text)
    first_technical_idx = min(
        (idx for heading in TECHNICAL_PLAN_HEADINGS if (idx := user_section.find(heading)) >= 0),
        default=-1,
    )
    if first_technical_idx < 0:
        return

    first_anchor_idx = min(
        (idx for anchor in USER_PLAN_ANCHORS if (idx := user_section.find(anchor)) >= 0),
        default=-1,
    )
    if first_anchor_idx < 0 or first_technical_idx < first_anchor_idx:
        issues.append(
            f"{label}: technical plan heading appears before user-facing analysis brief "
            "-> start with '사용자용 분석 기획안' and move Summary/Key Changes/Test Plan to '기술 부록'"
        )


def validate_path(path: Path) -> list[str]:
    issues: list[str] = []
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        found = False
        for key, text in user_facing_json_strings(data):
            found = True
            validate_text(f"{path}:{key}", text, issues)
        if not found:
            issues.append(f"{path}: no user_analysis_brief or user_review_brief found")
    else:
        validate_plan_shape(f"{path}:reader_section", raw, issues)
        validate_text(f"{path}:reader_section", markdown_user_section(raw), issues)
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate reader-facing planning text.")
    parser.add_argument("paths", nargs="+", help="JSON or Markdown files to validate")
    args = parser.parse_args()

    all_issues: list[str] = []
    for raw in args.paths:
        path = Path(raw)
        if not path.exists():
            all_issues.append(f"{path}: file not found")
            continue
        try:
            all_issues.extend(validate_path(path))
        except Exception as exc:
            all_issues.append(f"{path}: validation error: {exc}")

    if all_issues:
        print("USER-FACING TEXT BLOCK")
        for issue in all_issues:
            print(f"- {issue}")
        return 1
    print("user-facing text OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
