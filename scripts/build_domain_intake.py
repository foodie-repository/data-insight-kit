#!/usr/bin/env python3
"""checkpoint 답변에서 domain_intake.json을 결정적으로 파생한다 (spec §8.2).

답변 원천은 단일하다: companion 답변도 `checkpoint_answers.json`에만 쌓이고,
이 스크립트가 `maps_to.domain_field`를 가진 레코드에서
`runs/<run-id>/input/domain_intake.json`을 파생한다.

- 주입 파일 우선: 기존 domain_intake.json이 있고 `generated_by`가 없으면(수동
  주입) 필드를 덮지 않는다 — 인터뷰 답변은 open_questions 보강으로만 병합한다.
- `domain_readiness.status`는 stage_guard.compute_domain_readiness와 같은
  규칙(deterministic-v1)으로 계산한다. QA가 재계산해 불일치를 BLOCK한다.
- 자유 서술 답변의 구조화 배열 매핑(§8.2 v2.0 한계): column_semantics·
  terminology·kpi_definitions는 서술 전체를 meaning/formula에 담고 식별자는
  고정 라벨을 쓴다. evidence_boundaries 서술은 open_questions로 보강한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_guard  # noqa: E402

GENERATOR_ID = "scripts/build_domain_intake.py"

STRING_FIELDS = ("domain_scope", "objective", "row_meaning", "entity_grain", "time_grain")
STRING_LIST_FIELDS = ("exclusion_rules", "segments", "reference_data", "open_questions")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}")
    return data if isinstance(data, dict) else {}


def collect_field_answers(run: Path) -> tuple[dict[str, list[str]], list[str]]:
    """domain_field별 답변 텍스트(시간순)와 근거 answer_id 목록."""
    canonical = run / "checkpoint_answers.json"
    mirror = run / "input" / "checkpoint_answers.json"
    if mirror.exists() and canonical.exists() and canonical.read_bytes() != mirror.read_bytes():
        raise SystemExit("canonical/mirror checkpoint_answers.json 불일치 (fail-closed) — 동기화 후 다시 실행하세요.")
    by_field: dict[str, list[str]] = {}
    answer_ids: list[str] = []
    answers = load_json(canonical).get("answers")
    for item in answers if isinstance(answers, list) else []:
        if not isinstance(item, dict) or not item.get("companion_id"):
            continue
        field = str((item.get("maps_to") or {}).get("domain_field") or "")
        text = str(item.get("user_response") or item.get("answer") or "").strip()
        if not field or not text:
            continue
        by_field.setdefault(field, []).append(text)
        if item.get("answer_id"):
            answer_ids.append(str(item["answer_id"]))
    return by_field, answer_ids


def structured_items(field: str, texts: list[str]) -> list[dict[str, str]]:
    if field == "column_semantics":
        return [{"column": "인터뷰 답변", "meaning": text} for text in texts]
    if field == "terminology":
        return [{"term": "인터뷰 답변", "meaning": text} for text in texts]
    if field == "kpi_definitions":
        return [{"name": "인터뷰 정의 지표", "formula": text} for text in texts]
    if field == "forbidden_claims":
        return [{"phrase": text} for text in texts]
    return []


def readiness_block(intake: dict[str, Any]) -> dict[str, Any]:
    status, missing = stage_guard.compute_domain_readiness(intake)
    return {
        "status": status,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "rule": "deterministic-v1",
        "missing_required": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive domain_intake.json from checkpoint interview answers.")
    parser.add_argument("run_id")
    args = parser.parse_args()

    run = Path("runs") / args.run_id
    target = run / "input" / "domain_intake.json"
    by_field, answer_ids = collect_field_answers(run)
    if not by_field:
        raise SystemExit(
            "domain_field 답변이 없습니다 — 추가 확인 질문(companion)에 대한 답변을 "
            "apply_checkpoint_answer.py --companion 으로 먼저 기록하세요."
        )
    now = datetime.now(timezone.utc).isoformat()
    existing = load_json(target)

    if existing and not existing.get("generated_by"):
        # 수동 주입 파일 우선 (spec §8.2): 필드는 덮지 않고 open_questions 보강만.
        merged = dict(existing)
        open_questions = list(merged.get("open_questions") or [])
        for field, texts in sorted(by_field.items()):
            for text in texts:
                note = f"인터뷰 보강({field_label(field)}): {text}"
                if note not in open_questions:
                    open_questions.append(note)
        merged["open_questions"] = open_questions
        merged["domain_readiness"] = readiness_block(merged)
        target.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"merged (주입 파일 우선, open_questions 보강): {target}")
        return 0

    intake: dict[str, Any] = {
        "schema_version": "data-insight-kit.domain_intake.v1",
        "run_id": args.run_id,
        "created_at": str(existing.get("created_at") or now),
        "domain_scope": None,
        "objective": None,
        "row_meaning": None,
        "entity_grain": None,
        "time_grain": None,
        "terminology": [],
        "column_semantics": [],
        "exclusion_rules": [],
        "kpi_definitions": [],
        "segments": [],
        "reference_data": [],
        "forbidden_claims": [],
        "evidence_boundaries": {"can_say": [], "cannot_say": []},
        "open_questions": [],
        "generated_by": GENERATOR_ID,
        "source_answer_ids": answer_ids,
        "generated_at": now,
    }
    for field in STRING_FIELDS:
        if field in by_field:
            intake[field] = by_field[field][-1]
    for field in STRING_LIST_FIELDS:
        if field in by_field:
            intake[field] = list(by_field[field])
    for field in ("column_semantics", "terminology", "kpi_definitions", "forbidden_claims"):
        if field in by_field:
            intake[field] = structured_items(field, by_field[field])
    if "evidence_boundaries" in by_field:
        for text in by_field["evidence_boundaries"]:
            intake["open_questions"].append(f"판단 범위 확인: {text}")
    intake["domain_readiness"] = readiness_block(intake)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(intake, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"derived: {target}")
    print(f"readiness: {intake['domain_readiness']['status']} (missing: {', '.join(intake['domain_readiness']['missing_required']) or '없음'})")
    return 0


def field_label(field: str) -> str:
    return {
        "row_meaning": "행의 의미",
        "entity_grain": "핵심 대상",
        "column_semantics": "컬럼 의미",
        "exclusion_rules": "제외 기준",
        "objective": "분석 목적",
        "kpi_definitions": "핵심 지표 기준",
        "segments": "비교 축",
        "reference_data": "기준 자료",
        "forbidden_claims": "피해야 할 표현",
        "evidence_boundaries": "판단 범위",
        "open_questions": "남은 질문",
        "terminology": "용어",
        "domain_scope": "도메인 범위",
        "time_grain": "시간 단위",
    }.get(field, field)


if __name__ == "__main__":
    raise SystemExit(main())
