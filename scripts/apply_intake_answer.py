#!/usr/bin/env python3
"""
Apply a guided intake answer to runs/<run-id>/intake_draft.yaml.

The draft is written as YAML-compatible JSON so this helper has no PyYAML
dependency. Intake agents can still read it as structured data.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ADAPTER_GUARDS = [
    "do_not_overclaim_without_supporting_context",
    "layer_separation_required",
    "no_recommendation_from_single_context_layer",
]


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"question file not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}")


def load_draft(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        backup = path.with_suffix(path.suffix + ".manual.bak")
        backup.write_text(text, encoding="utf-8")
        return {"manual_draft_backup": str(backup)}
    if not isinstance(data, dict):
        raise SystemExit(f"draft root must be an object: {path}")
    return data


def resolve_run_path(run: Path, value: str | None, default: Path) -> Path:
    """Resolve a question-provided run path while preserving old defaults."""
    if not value:
        return default
    path = Path(value)
    if path.is_absolute():
        return path
    # Most question files use "runs/<run-id>/..." paths relative to kit root.
    if len(path.parts) >= 2 and path.parts[0] == "runs":
        return path
    # Also accept paths relative to the run directory for hand-authored questions.
    return run / path


def select_answer(question: dict[str, Any], option_id: str | None, answer: str | None) -> tuple[str, dict[str, Any] | None]:
    options = question.get("options") or []
    if option_id:
        for option in options:
            if option.get("id") == option_id:
                return str(option.get("label") or option_id), option
        valid = ", ".join(str(option.get("id")) for option in options)
        raise SystemExit(f"unknown option id '{option_id}'. valid options: {valid}")
    if answer:
        return answer, None
    recommended = question.get("recommended_option_id")
    if recommended:
        for option in options:
            if option.get("id") == recommended:
                return str(option.get("label") or recommended), option
    raise SystemExit("provide --option or --answer; no recommended option was found")


def merge_external_adapter_answer(
    draft: dict[str, Any],
    question: dict[str, Any],
    option: dict[str, Any] | None,
    answer_value: str,
) -> dict[str, Any] | None:
    """Return and store an external_adapters policy when the question is adapter-related."""
    maps_to = (option or {}).get("maps_to") or {}
    policy = maps_to.get("external_adapters")

    question_kind = question.get("question_kind")
    question_id = question.get("question_id")
    is_adapter_question = question_kind == "external_adapter_policy" or question_id == "external_adapter_policy"

    if policy is None and not is_adapter_question:
        return None

    if isinstance(policy, dict):
        normalized = dict(policy)
    else:
        normalized = {
            "mode": "ask_user_selected",
            "selected_categories": [],
            "unavailable_categories": [],
            "interpretation_guards": DEFAULT_ADAPTER_GUARDS,
            "notes": [answer_value],
        }

    normalized.setdefault("mode", "ask_user_selected")
    normalized.setdefault("selected_categories", [])
    normalized.setdefault("unavailable_categories", [])
    normalized.setdefault("interpretation_guards", DEFAULT_ADAPTER_GUARDS)
    if "registry_ref" not in normalized:
        adapter_meta = question.get("adapter_selection") or {}
        if adapter_meta.get("registry_ref"):
            normalized["registry_ref"] = adapter_meta["registry_ref"]

    draft["external_adapters"] = normalized
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Append an AskUserQuestion answer to intake_draft.yaml.")
    parser.add_argument("run_id", help="data-insight-kit run id")
    parser.add_argument("--question-file", help="defaults to runs/<run-id>/outputs/intake_questions.json")
    parser.add_argument("--option", help="selected option id from intake_questions.json")
    parser.add_argument("--answer", help="free-text answer")
    parser.add_argument("--source", default="ask_user_question", choices=["ask_user_question", "chat", "cli"])
    args = parser.parse_args()

    if args.option and args.answer:
        raise SystemExit("use only one of --option or --answer")

    run = Path("runs") / args.run_id
    question_path = Path(args.question_file) if args.question_file else run / "outputs" / "intake_questions.json"

    question = load_json(question_path)
    if question.get("run_id") and question["run_id"] != args.run_id:
        raise SystemExit(f"question run_id {question['run_id']} does not match {args.run_id}")

    instructions = question.get("response_instructions") or {}
    draft_path = resolve_run_path(run, instructions.get("write_to"), run / "intake_draft.yaml")

    answer_value, option = select_answer(question, args.option, args.answer)
    question_id = str(question.get("question_id") or "unknown")
    now = datetime.now(timezone.utc).isoformat()

    draft = load_draft(draft_path)
    interview = draft.setdefault("interview", {})
    answered = interview.setdefault("answered_decisions", {})
    answers = interview.setdefault("answers", [])

    answered[question_id] = answer_value
    if option:
        for key, value in (option.get("maps_to") or {}).items():
            answered[str(key)] = value
            if key == "report_contract" and isinstance(value, dict):
                draft["report"] = value
            elif key == "analysis_mode":
                draft["analysis_mode"] = value
    adapter_policy = merge_external_adapter_answer(draft, question, option, answer_value)
    if adapter_policy is not None:
        answered["external_adapters"] = adapter_policy

    state = question.get("interview_state") or {}
    previous_remaining = list(state.get("remaining_decisions") or [])
    remaining = [
        item
        for item in previous_remaining
        if item != question_id and item not in answered
    ]

    answers.append(
        {
            "question_id": question_id,
            "question": question.get("question", ""),
            "answer": answer_value,
            "selected_option_id": args.option,
            "source": args.source,
            "answered_at": now,
        }
    )

    interview["needed"] = bool(remaining)
    interview["style"] = "ask_user_question + deep_interview"
    interview["question_count"] = len(answers)
    interview["remaining_decisions"] = remaining
    interview["unresolved"] = remaining

    draft["run_id"] = args.run_id
    draft["updated_at"] = now
    draft["draft_status"] = "needs_followup" if remaining else "ready_for_final_intake"
    draft["response_instructions"] = instructions

    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"updated: {draft_path}")
    print(f"answered: {question_id} = {answer_value}")
    if remaining:
        print("remaining: " + ", ".join(remaining))
    else:
        print("remaining: none; intake can finalize on next run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
