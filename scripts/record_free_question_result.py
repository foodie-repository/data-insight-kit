#!/usr/bin/env python3
"""자유 질문 미니 결과 artifact 기록 helper (interview-loop-v2 spec §7).

오케스트레이터가 미니 쿼리(이번 run input 한정, 조회·집계만)를 수행한 뒤 이
스크립트로 결과를 기록한다. 계약:

- 선행 조건: `apply_checkpoint_answer.py --free-question`으로 기록된 답변
  레코드(answer_id)가 먼저 존재해야 한다 — "질문 없이 만들어진 미니 결과"를
  QA가 잡는 근거.
- 산출물 쌍: `outputs/exploration/free_question_<checkpoint>_<n>.md`(질문 원문·
  계산 방법·결과 표 ≤20행·한계) + 같은 이름의 `.json`(answer_id 연결 provenance).
- 미니 결과는 참고 자료다: 공식 산출물에 직접 인용하지 않는다 (spec §7).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RECORDER_ID = "scripts/record_free_question_result.py"
MAX_TABLE_DATA_ROWS = 20


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}")
    return data if isinstance(data, dict) else {}


def find_free_question_answer(run: Path, checkpoint_id: str, answer_id: str) -> dict[str, Any]:
    answers = load_json(run / "checkpoint_answers.json").get("answers")
    for item in answers if isinstance(answers, list) else []:
        if not isinstance(item, dict) or str(item.get("answer_id")) != answer_id:
            continue
        if item.get("checkpoint_id") != checkpoint_id:
            raise SystemExit(
                f"answer {answer_id}는 checkpoint '{item.get('checkpoint_id')}' 소속입니다 "
                f"(요청: {checkpoint_id})."
            )
        if item.get("loop_action") != "free_question":
            raise SystemExit(
                f"answer {answer_id}는 자유 질문 레코드가 아닙니다 — 미니 결과는 자유 질문에만 연결합니다."
            )
        return item
    raise SystemExit(
        f"answer_id {answer_id}를 checkpoint_answers.json에서 찾지 못했습니다. "
        "자유 질문 답변을 apply_checkpoint_answer.py --free-question으로 먼저 기록하세요."
    )


def table_row_count(table_md: str) -> int:
    rows = [line for line in table_md.strip().splitlines() if line.strip().startswith("|")]
    # 헤더 1줄 + 구분선 1줄 제외
    return max(0, len(rows) - 2)


def next_result_paths(run: Path, checkpoint_id: str) -> tuple[Path, Path]:
    exploration = run / "outputs" / "exploration"
    exploration.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        meta = exploration / f"free_question_{checkpoint_id}_{n}.json"
        if not meta.exists():
            return meta, meta.with_suffix(".md")
        n += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a free-question mini-result artifact pair.")
    parser.add_argument("run_id")
    parser.add_argument("checkpoint_id")
    parser.add_argument("--answer-id", required=True, help="자유 질문 답변 레코드의 answer_id")
    parser.add_argument("--method", required=True, help="계산 방법 설명 (사용 컬럼·필터·집계)")
    parser.add_argument("--limits", required=True, help="한계 (결측·표본·해석 주의)")
    parser.add_argument("--table-md", required=True, help="결과 표 markdown 파일 경로 (데이터 행 ≤20)")
    args = parser.parse_args()

    run = Path("runs") / args.run_id
    answer = find_free_question_answer(run, args.checkpoint_id, args.answer_id)

    exploration = run / "outputs" / "exploration"
    for meta in sorted(exploration.glob(f"free_question_{args.checkpoint_id}_*.json")) if exploration.is_dir() else []:
        if load_json(meta).get("answer_id") == args.answer_id:
            raise SystemExit(f"이 answer_id의 미니 결과가 이미 있습니다: {meta}")

    table_path = Path(args.table_md)
    if not table_path.is_file():
        raise SystemExit(f"결과 표 파일이 없습니다: {table_path}")
    table_md = table_path.read_text(encoding="utf-8")
    rows = table_row_count(table_md)
    if rows == 0:
        raise SystemExit("결과 표에 데이터 행이 없습니다 (markdown 표 형식 | ... | 필요).")
    if rows > MAX_TABLE_DATA_ROWS:
        raise SystemExit(f"결과 표 데이터 행이 {rows}개입니다 — 최대 {MAX_TABLE_DATA_ROWS}행 (spec §7).")

    question_text = str(answer.get("user_response") or answer.get("answer") or "").strip()
    now = datetime.now(timezone.utc).isoformat()
    meta_path, md_path = next_result_paths(run, args.checkpoint_id)

    md_path.write_text(
        "# 직접 질문 확인 결과\n\n"
        f"질문: {question_text}\n\n"
        f"계산 방법: {args.method}\n\n"
        f"결과:\n{table_md.strip()}\n\n"
        f"한계: {args.limits}\n\n"
        "이 결과는 참고 자료입니다. 공식 분석에 반영하려면 분석 단계에서 다시 계산합니다.\n",
        encoding="utf-8",
    )
    meta_path.write_text(
        json.dumps(
            {
                "schema_version": "data-insight-kit.free_question_result.v1",
                "run_id": args.run_id,
                "checkpoint_id": args.checkpoint_id,
                "answer_id": args.answer_id,
                "question": question_text,
                "method": args.method,
                "limits": args.limits,
                "table_rows": rows,
                "md_path": str(md_path),
                "recorded_by": RECORDER_ID,
                "created_at": now,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"recorded: {md_path}")
    print(f"provenance: {meta_path}")
    print("다음: checkpoint gate를 다시 실행하면 이 결과가 추가 문답에 연결됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
