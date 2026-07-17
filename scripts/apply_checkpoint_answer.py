#!/usr/bin/env python3
"""
Append a human checkpoint answer to runs/<run-id>/checkpoint_answers.json.

The wrapper only continues past a checkpoint when the latest answer for that
checkpoint has continue_pipeline=true.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

HUMAN_CONFIRMATION_SOURCES = {"ask_user_question", "user_chat", "manual_cli"}
RECORDER_ID = "scripts/apply_checkpoint_answer.py"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def latest_handoff_print(question_path: Path, question_sha: str) -> str | None:
    """checkpoint_gate가 남긴 핸드오프 출력 스탬프 중 이 질문(sha 일치)의
    가장 최근 printed_at을 돌려준다. 없으면 None (턴 분리 규칙 검증용)."""
    log_path = question_path.parent / "handoff_log.json"
    if not log_path.exists():
        return None
    try:
        entries = json.loads(log_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(entries, list):
        return None
    printed = [
        str(entry.get("printed_at"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("question_sha256") == question_sha and entry.get("printed_at")
    ]
    return max(printed) if printed else None


QUESTION_FILE_RE = re.compile(r"^\d+_(?P<checkpoint>[a-z_]+)_question(?:\.round2)?\.json$")


def validate_question_path(run: Path, checkpoint_id: str, path: Path) -> None:
    """interview-loop-v2 §4.6: 질문 파일 허용 집합 검사(기록 시점). 허용 집합은
    해당 run의 outputs/checkpoints/ 안에 있는 R1 canonical 또는 같은 prefix의
    .round2 파일뿐이다 — 임의 파일을 provenance 대상으로 삼을 수 없다."""
    if not path.is_file():
        raise SystemExit(f"checkpoint question file not found: {path}")
    resolved = path.resolve()
    allowed_dir = (run / "outputs" / "checkpoints").resolve()
    if allowed_dir not in resolved.parents:
        raise SystemExit(
            f"question file must live under {run / 'outputs' / 'checkpoints'}: {path}"
        )
    match = QUESTION_FILE_RE.match(resolved.name)
    if match is None or match.group("checkpoint") != checkpoint_id:
        raise SystemExit(
            "question file name must be <NN>_<checkpoint>_question[.round2].json "
            f"for '{checkpoint_id}': {resolved.name}"
        )


def resolve_question_file(run: Path, checkpoint_id: str, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    checkpoints_dir = run / "outputs" / "checkpoints"
    round2 = sorted(checkpoints_dir.glob(f"*_{checkpoint_id}_question.round2.json"))
    if round2:
        return round2[-1]
    candidates = sorted(checkpoints_dir.glob(f"*_{checkpoint_id}_question.json"))
    if not candidates:
        raise SystemExit(f"checkpoint question file not found for {checkpoint_id}: {checkpoints_dir}")
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
        "--companion",
        help="companion 질문 id — 정보 수집용 답변. 진행을 결정하지 않는다 (불변식 I1).",
    )
    parser.add_argument(
        "--free-question",
        help="사용자 자유 질문 원문 — loop_action=free_question 레코드. 진행을 결정하지 않는다 (불변식 I1).",
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
    if args.free_question and (args.option or args.answer or args.companion or args.continue_pipeline):
        raise SystemExit(
            "--free-question은 단독으로만 씁니다 — --option/--answer/--companion/"
            "--continue-pipeline과 상호 배타입니다 (불변식 I1)."
        )
    if args.companion and args.continue_pipeline:
        raise SystemExit(
            "--companion 답변은 진행을 결정하지 않습니다 — --continue-pipeline과 함께 쓸 수 없습니다 (불변식 I1)."
        )
    user_response = (args.user_response or args.answer or args.free_question or "").strip()
    if not user_response:
        raise SystemExit(
            "checkpoint answers require --user-response with the user's actual reply. "
            "Do not fill this from the agent's own recommendation."
        )
    if args.source in {"user_chat", "ask_user_question"} and not (args.transcript_ref or "").strip():
        raise SystemExit(
            "--source user_chat and --source ask_user_question require --transcript-ref. "
            "Do not convert a Plan-mode approval into checkpoint-specific answers. "
            "Show the checkpoint prompt to the user and record the actual message reference."
        )

    run = Path("runs") / args.run_id
    question_path = resolve_question_file(run, args.checkpoint_id, args.question_file)
    validate_question_path(run, args.checkpoint_id, question_path)
    question = load_json(question_path)
    if question.get("run_id") and question["run_id"] != args.run_id:
        raise SystemExit(f"question run_id {question['run_id']} does not match {args.run_id}")
    if question.get("checkpoint_id") and question["checkpoint_id"] != args.checkpoint_id:
        raise SystemExit(f"question checkpoint_id {question['checkpoint_id']} does not match {args.checkpoint_id}")
    if not question.get("created_at"):
        raise SystemExit(
            "checkpoint question is missing created_at. Regenerate it with scripts/checkpoint_gate.py "
            "before recording a user answer."
        )

    interview_round = int((question.get("interview_loop") or {}).get("round") or 1)
    companion_id: str | None = None
    companion_maps: dict[str, Any] = {}
    loop_action: str | None = None
    if args.free_question:
        # 라운드당 자유 질문 1개 (interview-loop-v2 D3) — 기록 시점에도 거부한다.
        existing = load_json(run / "checkpoint_answers.json").get("answers")
        used = sum(
            1
            for item in (existing if isinstance(existing, list) else [])
            if isinstance(item, dict)
            and item.get("checkpoint_id") == args.checkpoint_id
            and item.get("loop_action") == "free_question"
            and int(item.get("interview_round") or 1) == interview_round
        )
        if used >= 1:
            raise SystemExit("자유 질문은 라운드당 1개까지만 기록할 수 있습니다 (interview-loop-v2 D3).")
        loop_action = "free_question"
        answer_value, option, continue_pipeline = args.free_question, None, False
    elif args.companion:
        companions = question.get("companion_questions") or []
        companion = next(
            (c for c in companions if isinstance(c, dict) and c.get("id") == args.companion), None
        )
        if companion is None:
            valid = ", ".join(str(c.get("id")) for c in companions if isinstance(c, dict)) or "없음"
            raise SystemExit(f"unknown companion id '{args.companion}'. valid companions: {valid}")
        companion_id = args.companion
        if isinstance(companion.get("maps_to"), dict):
            companion_maps = companion["maps_to"]
        companion_options = companion.get("options") or []
        if args.option:
            option = next(
                (o for o in companion_options if isinstance(o, dict) and o.get("id") == args.option),
                None,
            )
            if option is None:
                valid = ", ".join(
                    str(o.get("id")) for o in companion_options if isinstance(o, dict)
                ) or "없음"
                raise SystemExit(f"unknown companion option id '{args.option}'. valid options: {valid}")
            answer_value = str(option.get("label") or args.option)
        elif args.answer:
            option = None
            answer_value = args.answer
        else:
            raise SystemExit("companion 답변에는 --option 또는 --answer가 필요합니다.")
        # companion 답변은 어떤 경우에도 진행을 결정하지 않는다 (불변식 I1).
        continue_pipeline = False
    else:
        answer_value, option, continue_pipeline = select_answer(
            question,
            args.option,
            args.answer,
            args.continue_pipeline,
        )
        option_maps = (option or {}).get("maps_to") or {}
        if option_maps.get("loop_action"):
            loop_action = str(option_maps["loop_action"])
            # 불변식 I1: 탐색 레코드는 진행 불가 — 스키마 층과 별개로 기록 시점에도 강제.
            continue_pipeline = False
    human_confirmed = args.source in HUMAN_CONFIRMATION_SOURCES and bool(user_response)
    if continue_pipeline and not human_confirmed:
        raise SystemExit(
            "this answer would continue the pipeline, but source is not human-confirmed. "
            "Ask the user and rerun with --source user_chat or --source ask_user_question plus --user-response."
        )
    now = datetime.now(timezone.utc).isoformat()
    question_created_at = str(question["created_at"])
    question_file = stable_path(question_path)
    question_ref = {
        "path": question_file,
        "sha256": sha256_file(question_path),
        "created_at": question_created_at,
        "checkpoint_id": args.checkpoint_id,
    }
    # 전달 순서(턴 분리) 강제: 팝업(ask_user_question) 답변은 이 질문의 핸드오프
    # 원문이 최소 한 번 출력된 뒤에만 기록할 수 있다 (v4 smoke 발견).
    handoff_printed_at = latest_handoff_print(question_path, question_ref["sha256"])
    if args.source == "ask_user_question" and handoff_printed_at is None:
        raise SystemExit(
            "ask_user_question 답변은 핸드오프 원문 출력이 선행되어야 합니다 — 먼저 "
            f"`python3 scripts/checkpoint_gate.py {args.run_id} {args.checkpoint_id} --print-existing` "
            "으로 근거 원문을 사용자에게 보여준 뒤(턴 분리) 다시 기록하세요."
        )
    output_path = run / "checkpoint_answers.json"
    data = load_json(output_path)
    data["schema_version"] = "data-insight-kit.checkpoint_answers.v3"
    data["run_id"] = args.run_id
    data["updated_at"] = now
    answers = data.setdefault("answers", [])
    if not isinstance(answers, list):
        raise SystemExit(f"answers must be an array: {output_path}")
    record_maps = dict((option or {}).get("maps_to") or {})
    if companion_id is not None:
        record_maps = {**companion_maps, **record_maps}
    record: dict[str, Any] = {
        "answer_id": f"chkans_{uuid4().hex}",
        "checkpoint_id": args.checkpoint_id,
        "checkpoint_kind": question.get("checkpoint_kind"),
        "recorded_by": RECORDER_ID,
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
        "approval_contract_version": "checkpoint-answer.v3",
        "continue_pipeline": continue_pipeline,
        "maps_to": record_maps,
        "interview_round": interview_round,
        "answered_at": now,
        "question_file": question_file,
        "question_ref": question_ref,
    }
    if loop_action:
        record["loop_action"] = loop_action
    if companion_id:
        record["companion_id"] = companion_id
    if handoff_printed_at:
        record["handoff_printed_at"] = handoff_printed_at
        try:
            gap = (
                datetime.fromisoformat(now) - datetime.fromisoformat(handoff_printed_at)
            ).total_seconds()
            record["handoff_to_answer_seconds"] = round(gap, 1)
        except ValueError:
            pass
    answers.append(record)
    write_json(output_path, data)

    mirror_path = run / "input" / "checkpoint_answers.json"
    write_json(mirror_path, data)

    print(f"updated: {output_path}")
    print(f"mirrored: {mirror_path}")
    print(f"answered: {args.checkpoint_id} = {answer_value}")
    print(f"continue_pipeline: {str(continue_pipeline).lower()}")
    if loop_action == "free_question":
        print("직접 질문이 기록되었습니다. 답변 자료가 준비되면 다음 문답에서 함께 확인합니다.")
    elif companion_id:
        print("추가 확인 질문 답변이 기록되었습니다. 이 답변은 단계 진행을 결정하지 않습니다.")
    elif loop_action:
        print("탐색 방향 선택이 기록되었습니다. 다음 문답에서 선택한 방향을 자세히 확인합니다.")
    elif not continue_pipeline:
        print("이 답변은 다음 단계 진행을 막습니다. 관련 산출물을 수정한 뒤 승인 답변을 다시 남기세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
