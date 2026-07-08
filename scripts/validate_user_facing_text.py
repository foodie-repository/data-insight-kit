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
}

FORBIDDEN_PHRASES = {
    "실행을 시작하면 위 선택지를 먼저 묻고": "사용자가 바로 고를 수 있는 승인 질문",
    "이전 계획은 취소": "최신 기준으로 제안합니다",
    "이전 계획을 취소": "최신 기준으로 제안합니다",
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
