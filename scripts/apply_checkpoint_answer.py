#!/usr/bin/env python3
"""
Append a human checkpoint answer to runs/<run-id>/checkpoint_answers.json.

The wrapper only continues past a checkpoint when the latest answer for that
checkpoint has continue_pipeline=true.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HUMAN_CONFIRMATION_SOURCES = {"ask_user_question", "user_chat", "manual_cli"}


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


def resolve_question_file(run: Path, checkpoint_id: str, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    candidates = sorted((run / "outputs" / "checkpoints").glob(f"*_{checkpoint_id}_question.json"))
    if not candidates:
        raise SystemExit(f"checkpoint question file not found for {checkpoint_id}: {run / 'outputs' / 'checkpoints'}")
    return candidates[-1]


def select_answer(
    question: dict[str, Any],
    option_id: str | None,
    answer: str | None,
    free_text_continue: bool,
) -> tuple[str, dict[str, Any] | None, bool]:
    options = question.get("options") or []
    if option_id:
        for option in options:
            if option.get("id") == option_id:
                return str(option.get("label") or option_id), option, bool(option.get("continue_pipeline"))
        valid = ", ".join(str(option.get("id")) for option in options)
        raise SystemExit(f"unknown option id '{option_id}'. valid options: {valid}")
    if answer:
        return answer, None, bool(free_text_continue)
    recommended = question.get("recommended_option_id")
    if recommended:
        for option in options:
            if option.get("id") == recommended:
                return str(option.get("label") or recommended), option, bool(option.get("continue_pipeline"))
    raise SystemExit("provide --option or --answer; no recommended option was found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a data-insight-kit checkpoint answer.")
    parser.add_argument("run_id")
    parser.add_argument("checkpoint_id")
    parser.add_argument("--question-file", help="defaults to outputs/checkpoints/*_<checkpoint>_question.json")
    parser.add_argument("--option", help="selected option id")
    parser.add_argument("--answer", help="free-text answer")
    parser.add_argument(
        "--continue-pipeline",
        action="store_true",
        help="Only for free-text answers: allow the wrapper to continue past this checkpoint.",
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=["ask_user_question", "user_chat", "manual_cli", "agent_assumption"],
        help=(
            "Where the checkpoint answer came from. Use user_chat for an actual chat reply, "
            "ask_user_question for a Plan-mode popup, manual_cli for an operator-entered reply. "
            "agent_assumption records a note but can never approve continuation."
        ),
    )
    parser.add_argument(
        "--user-response",
        help="The user's actual wording or a concise operator transcript of the answer.",
    )
    parser.add_argument(
        "--transcript-ref",
        help="Optional thread/session/message reference for the user answer.",
    )
    args = parser.parse_args()

    if args.option and args.answer:
        raise SystemExit("use only one of --option or --answer")
    user_response = (args.user_response or args.answer or "").strip()
    if not user_response:
        raise SystemExit(
            "checkpoint answers require --user-response with the user's actual reply. "
            "Do not fill this from the agent's own recommendation."
        )

    run = Path("runs") / args.run_id
    question_path = resolve_question_file(run, args.checkpoint_id, args.question_file)
    question = load_json(question_path)
    if question.get("run_id") and question["run_id"] != args.run_id:
        raise SystemExit(f"question run_id {question['run_id']} does not match {args.run_id}")
    if question.get("checkpoint_id") and question["checkpoint_id"] != args.checkpoint_id:
        raise SystemExit(f"question checkpoint_id {question['checkpoint_id']} does not match {args.checkpoint_id}")

    answer_value, option, continue_pipeline = select_answer(
        question,
        args.option,
        args.answer,
        args.continue_pipeline,
    )
    human_confirmed = args.source in HUMAN_CONFIRMATION_SOURCES and bool(user_response)
    if continue_pipeline and not human_confirmed:
        raise SystemExit(
            "this answer would continue the pipeline, but source is not human-confirmed. "
            "Ask the user and rerun with --source user_chat or --source ask_user_question plus --user-response."
        )
    now = datetime.now(timezone.utc).isoformat()
    output_path = run / "checkpoint_answers.json"
    data = load_json(output_path)
    data["schema_version"] = "data-insight-kit.checkpoint_answers.v2"
    data["run_id"] = args.run_id
    data["updated_at"] = now
    answers = data.setdefault("answers", [])
    if not isinstance(answers, list):
        raise SystemExit(f"answers must be an array: {output_path}")
    answers.append(
        {
            "checkpoint_id": args.checkpoint_id,
            "checkpoint_kind": question.get("checkpoint_kind"),
            "question": question.get("question", ""),
            "blocked_decision": question.get("blocked_decision", ""),
            "recommended_answer": question.get("recommended_answer", ""),
            "chat_prompt": question.get("chat_prompt", ""),
            "answer": answer_value,
            "selected_option_id": args.option,
            "source": args.source,
            "user_response": user_response,
            "transcript_ref": args.transcript_ref,
            "human_confirmed": human_confirmed,
            "approval_contract_version": "checkpoint-answer.v2",
            "continue_pipeline": continue_pipeline,
            "maps_to": (option or {}).get("maps_to") or {},
            "answered_at": now,
            "question_file": str(question_path),
        }
    )
    write_json(output_path, data)

    mirror_path = run / "input" / "checkpoint_answers.json"
    write_json(mirror_path, data)

    print(f"updated: {output_path}")
    print(f"mirrored: {mirror_path}")
    print(f"answered: {args.checkpoint_id} = {answer_value}")
    print(f"continue_pipeline: {str(continue_pipeline).lower()}")
    if not continue_pipeline:
        print("이 답변은 다음 단계 진행을 막습니다. 관련 산출물을 수정한 뒤 승인 답변을 다시 남기세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
