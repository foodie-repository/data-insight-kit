#!/usr/bin/env python3
"""
Prepare the core external adapter plan from finalized or draft intake state.

This script is intentionally orchestration-focused. It does not collect new
external data and it does not copy run-local smoke-test logic into the core
pipeline. It converts the guided intake answer into a small machine-readable
plan that connect/frame/analyze/visualize/communicate can consistently read.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from datetime import datetime, timezone
from typing import Any

from external_adapter_utils import ADAPTER_REGISTRY


SCHEMA_VERSION = "data-insight-kit.external_adapter_plan.v1"
ADAPTER_REQUEST_TERMS = (
    "외부 데이터",
    "외부 보정",
    "보정 데이터",
    "추가 데이터",
    "external adapter",
    "external context",
    "domain pack",
)
DEFAULT_INTERPRETATION_GUARDS = [
    "do_not_overclaim_without_supporting_context",
    "layer_separation_required",
]


def read_json(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def load_yaml_if_available(text: str) -> dict[str, Any] | None:
    try:
        import yaml  # type: ignore
    except Exception:
        return None
    try:
        data = yaml.safe_load(text)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def parse_simple_external_adapters(text: str) -> dict[str, Any] | None:
    """Parse the simple YAML shape used by data-insight-kit intake files."""
    lines = text.splitlines()
    start = None
    base_indent = 0
    for idx, line in enumerate(lines):
        if re.match(r"^\s*external_adapters:\s*$", line):
            start = idx
            base_indent = len(line) - len(line.lstrip(" "))
            break
    if start is None:
        return None

    out: dict[str, Any] = {}
    current_list: str | None = None
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= base_indent:
            break
        item_match = re.match(r"^-\s*(.+?)\s*$", stripped)
        if item_match and current_list:
            out.setdefault(current_list, []).append(item_match.group(1).strip().strip('"').strip("'"))
            continue
        kv_match = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*?)\s*$", stripped)
        if not kv_match:
            continue
        key, raw_value = kv_match.group(1), kv_match.group(2)
        if raw_value == "":
            current_list = key
            out.setdefault(key, [])
            continue
        current_list = None
        if raw_value in {"[]", "[ ]"}:
            out[key] = []
        elif raw_value.lower() in {"true", "false"}:
            out[key] = raw_value.lower() == "true"
        else:
            out[key] = raw_value.strip().strip('"').strip("'")
    return out or None


def load_structured(path: pathlib.Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    data = load_yaml_if_available(text)
    if data is not None:
        return data
    adapters = parse_simple_external_adapters(text)
    return {"external_adapters": adapters} if adapters else None


def candidate_intake_paths(run: pathlib.Path) -> list[pathlib.Path]:
    return [
        run / "input" / "intake.yaml",
        run / "intake.yaml",
        run / "input" / "intake_draft.yaml",
        run / "intake_draft.yaml",
        run / "manifest.json",
    ]


def extract_external_adapters(data: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(data.get("external_adapters"), dict):
        return data["external_adapters"]
    intake = data.get("intake")
    if isinstance(intake, dict) and isinstance(intake.get("external_adapters"), dict):
        return intake["external_adapters"]
    interview = data.get("interview")
    if isinstance(interview, dict):
        answered = interview.get("answered_decisions")
        if isinstance(answered, dict) and isinstance(answered.get("external_adapters"), dict):
            return answered["external_adapters"]
    return None


def find_adapter_policy(run: pathlib.Path) -> tuple[dict[str, Any] | None, pathlib.Path | None]:
    for path in candidate_intake_paths(run):
        data = load_structured(path)
        if not data:
            continue
        policy = extract_external_adapters(data)
        if policy:
            return dict(policy), path
    return None, None


def normalize_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    if not policy:
        return {
            "mode": "none",
            "selected_categories": [],
            "unavailable_categories": [],
            "interpretation_guards": DEFAULT_INTERPRETATION_GUARDS,
            "registry_ref": "docs/external-adapter-registry.md",
        }
    selected = [str(item) for item in (policy.get("selected_categories") or [])]
    unavailable = [str(item) for item in (policy.get("unavailable_categories") or [])]
    guards = [str(item) for item in (policy.get("interpretation_guards") or DEFAULT_INTERPRETATION_GUARDS)]
    return {
        "mode": str(policy.get("mode") or ("ask_user_selected" if selected else "none")),
        "selected_categories": selected,
        "unavailable_categories": unavailable,
        "interpretation_guards": guards,
        "registry_ref": str(policy.get("registry_ref") or "docs/external-adapter-registry.md"),
    }


def external_manifest_paths(run: pathlib.Path) -> list[pathlib.Path]:
    return [
        run / "external_denominators.json",
        run / "input" / "external_denominator_manifest.json",
    ]


def load_available_manifest_categories(run: pathlib.Path) -> tuple[set[str], list[str]]:
    categories: set[str] = set()
    paths: list[str] = []
    for path in external_manifest_paths(run):
        manifest = read_json(path)
        if not manifest:
            continue
        paths.append(str(path))
        for adapter in manifest.get("adapters") or []:
            if isinstance(adapter, dict) and adapter.get("category"):
                categories.add(str(adapter["category"]))
    return categories, paths


def category_contract(category: str) -> dict[str, Any]:
    spec = ADAPTER_REGISTRY.get(category, ADAPTER_REGISTRY["custom"])
    return {
        "category": category,
        "metric_layers": list(spec["metric_layers"]),
        "meaning": spec["meaning"],
        "allowed_uses": list(spec["allowed_uses"]),
        "prohibited_interpretations": list(spec["prohibited_interpretations"]),
    }


def build_plan(run_id: str, run: pathlib.Path, policy: dict[str, Any] | None, policy_path: pathlib.Path | None) -> dict[str, Any]:
    normalized = normalize_policy(policy)
    selected = normalized["selected_categories"]
    manifest_categories, manifest_paths = load_available_manifest_categories(run)
    missing_from_manifest = [
        category for category in selected if category not in manifest_categories
    ]
    unavailable = sorted(set(normalized["unavailable_categories"]) | set(missing_from_manifest))
    available = [category for category in selected if category not in unavailable]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "selected" if selected else "none",
        "source_intake_path": str(policy_path) if policy_path else None,
        "mode": normalized["mode"],
        "selected_categories": selected,
        "available_categories": available,
        "unavailable_categories": unavailable,
        "interpretation_guards": normalized["interpretation_guards"],
        "registry_ref": normalized["registry_ref"],
        "manifest_paths": manifest_paths,
        "category_contracts": [category_contract(category) for category in selected],
        "notes": [
            "This plan is derived from guided intake and does not collect external data.",
            "If a selected category has no manifest/source, keep it unavailable instead of fabricating data.",
        ],
    }


def write_plan(run: pathlib.Path, plan: dict[str, Any]) -> tuple[pathlib.Path, pathlib.Path]:
    input_path = run / "input" / "external_adapter_plan.json"
    root_path = run / "external_adapter_plan.json"
    for path in (input_path, root_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return input_path, root_path


def request_needs_adapter_policy(user_request: str) -> bool:
    lowered = user_request.lower()
    return any(term.lower() in lowered for term in ADAPTER_REQUEST_TERMS)


def write_adapter_question(run_id: str, run: pathlib.Path, user_request: str) -> None:
    outputs = run / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    user_analysis_brief = {
        "plain_title": "보조 데이터를 함께 쓸지 선택합니다",
        "analysis_goal": "기본 데이터만 볼지, 결과 판단을 보강할 외부 데이터나 도메인 기준을 함께 볼지 정합니다.",
        "answerable_questions": [
            "현재 데이터만으로 빠르게 구조를 볼까요?",
            "판단을 보강할 보조 데이터가 있나요?",
            "회사나 업무 도메인에서 반드시 반영해야 할 기준이 있나요?",
        ],
        "data_can_support": [
            "기본 데이터만 쓰면 입력 데이터에서 직접 확인되는 구조와 패턴을 볼 수 있습니다.",
            "외부 데이터나 domain pack이 준비되면 수요, 비용, 성과, 리스크 같은 보조 근거를 별도로 결합할 수 있습니다.",
        ],
        "not_answerable": [
            "외부 근거가 없으면 수요, 비용, 성과, 원인, 추천 같은 강한 판단을 확정하지 않습니다.",
            "선택한 보정 데이터가 실제로 수집 가능하다는 뜻은 아니며, 데이터 연결 단계에서 사용 가능 여부를 확인합니다.",
        ],
        "analysis_options": [
            {
                "label": "기본 데이터만 사용",
                "description": "입력 데이터에서 직접 확인되는 구조와 패턴만 봅니다.",
            },
            {
                "label": "핵심 보조 데이터만 사용",
                "description": "결론에 꼭 필요한 보조 데이터 1~2개만 우선 확인합니다.",
                "recommended": True,
            },
            {
                "label": "도메인 기준까지 반영",
                "description": "domain pack의 지표, 금지 해석, 보고서 기준을 함께 적용합니다.",
            },
        ],
        "checkpoint_plan": [
            "선택한 외부 데이터가 실제로 있는지 데이터 연결 단계에서 확인합니다.",
            "없는 데이터는 임의로 만들지 않고 한계와 후속 보강으로 남깁니다.",
            "데이터 샘플과 품질 요약을 본 뒤 실제 분석 방향을 다시 확인합니다.",
            "최종 보고서의 독자, 흐름, 문체, 결론 수위를 확인한 뒤 작성합니다.",
        ],
        "preflight_requirements": [
            "선택한 보정 데이터가 로컬 스냅샷이나 접근 가능한 공식 원천으로 준비되어 있어야 합니다.",
            "준비되지 않은 보정 데이터는 결과에 있는 것처럼 쓰지 않고 '후속 보강'으로 남깁니다.",
        ],
        "approval_options": [
            {
                "label": "기본 데이터만 사용",
                "description": "입력 데이터에서 직접 확인되는 구조와 패턴만 봅니다.",
            },
            {
                "label": "핵심 보조 데이터만 사용",
                "description": "결론에 꼭 필요한 보조 데이터 1~2개만 우선 확인합니다.",
                "recommended": True,
            },
            {
                "label": "도메인 기준까지 반영",
                "description": "domain pack의 지표, 금지 해석, 보고서 기준을 함께 적용합니다.",
            },
        ],
        "approval_question": "이번 분석에서 보조 데이터나 도메인 기준을 어느 정도까지 반영할까요?",
    }
    question = {
        "schema_version": "data-insight-kit.intake_question.v1",
        "run_id": run_id,
        "status": "blocked_for_user_question",
        "question_id": "external_adapter_policy",
        "question_kind": "external_adapter_policy",
        "header": "보조 데이터",
        "user_analysis_brief": user_analysis_brief,
        "current_understanding": (
            f"사용자는 '{user_request}' 요청으로 분석 대시보드와 보고서를 만들고 싶다."
            if user_request
            else "사용자는 분석 대시보드와 보고서를 만들고 싶다."
        ),
        "blocked_decision": "기본 데이터만 볼지, 보조 데이터나 도메인 기준을 함께 볼지 선택해야 한다.",
        "recommended_option_id": "core_context",
        "question": "이번 분석에서 보조 데이터나 도메인 기준을 어느 정도까지 반영할까요?",
        "options": [
            {
                "id": "data_only",
                "label": "기본 데이터만 사용",
                "description": "입력 데이터에서 직접 확인되는 구조와 패턴만 봅니다.",
                "maps_to": {
                    "external_adapters": {
                        "mode": "none",
                        "selected_categories": [],
                        "unavailable_categories": [],
                        "interpretation_guards": ["do_not_overclaim_without_supporting_context"],
                        "registry_ref": "docs/external-adapter-registry.md",
                    }
                },
            },
            {
                "id": "core_context",
                "label": "핵심 보조 데이터만 사용",
                "description": "결론에 꼭 필요한 보조 데이터 1~2개만 우선 확인합니다.",
                "maps_to": {
                    "external_adapters": {
                        "mode": "ask_user_selected",
                        "selected_categories": [],
                        "unavailable_categories": [],
                        "interpretation_guards": [
                            "do_not_overclaim_without_supporting_context",
                        ],
                        "registry_ref": "docs/external-adapter-registry.md",
                    }
                },
            },
            {
                "id": "domain_context",
                "label": "도메인 기준까지 반영",
                "description": "domain pack의 지표, 금지 해석, 보고서 기준을 함께 적용합니다.",
                "maps_to": {
                    "external_adapters": {
                        "mode": "ask_user_selected",
                        "selected_categories": [],
                        "unavailable_categories": [],
                        "interpretation_guards": DEFAULT_INTERPRETATION_GUARDS,
                        "registry_ref": "domains/<domain>/domain.yaml",
                    }
                },
            },
        ],
        "allow_free_text": True,
        "adapter_selection": {
            "selection_mode": "full",
            "available_categories": [],
            "recommended_categories": [],
            "registry_ref": "docs/external-adapter-registry.md",
        },
        "interview_state": {
            "question_index": 2,
            "max_questions": 3,
            "answered_decisions": {},
            "remaining_decisions": ["report_contract"],
            "can_finalize_after_answer": False,
            "finalization_rule": "답변은 intake_draft.yaml에 누적하고, 충분해지면 intake.yaml을 확정한다.",
        },
        "response_instructions": {
            "mode": "draft",
            "write_to": f"runs/{run_id}/intake_draft.yaml",
            "finalize_to": f"runs/{run_id}/intake.yaml",
            "apply_command": f"python3 scripts/apply_intake_answer.py {run_id} --option <option-id>",
            "resume_command": f"bash scripts/run_codex_pipeline.sh {run_id} --guided-intake",
        },
    }
    (outputs / "intake_questions.json").write_text(json.dumps(question, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (outputs / "intake_questions.md").write_text(
        "\n".join(
            [
                "# external adapter 선택 필요",
                "",
                "## 사용자용 분석 기획안",
                "",
                f"### {user_analysis_brief['plain_title']}",
                "",
                user_analysis_brief["analysis_goal"],
                "",
                "답할 질문:",
                *[f"- {item}" for item in user_analysis_brief["answerable_questions"]],
                "",
                "이번 데이터로 볼 수 있는 것:",
                *[f"- {item}" for item in user_analysis_brief["data_can_support"]],
                "",
                "이번 데이터만으로 판단하지 않을 것:",
                *[f"- {item}" for item in user_analysis_brief["not_answerable"]],
                "",
                "추천 분석 방향:",
                *[
                    f"- {opt['label']}: {opt['description']}" + (" (추천)" if opt.get("recommended") else "")
                    for opt in user_analysis_brief["analysis_options"]
                ],
                "",
                "중간 확인 시점:",
                *[f"- {item}" for item in user_analysis_brief["checkpoint_plan"]],
                "",
                "실행 전 준비사항:",
                *[f"- {item}" for item in user_analysis_brief["preflight_requirements"]],
                "",
                "승인 선택지:",
                *[
                    f"- {opt['label']}: {opt['description']}" + (" (추천)" if opt.get("recommended") else "")
                    for opt in user_analysis_brief["approval_options"]
                ],
                "",
                f"승인 질문: {user_analysis_brief['approval_question']}",
                "",
                "## 채팅 질문",
                "",
                f"현재 이해: {question['current_understanding']}",
                f"막힌 결정: {question['blocked_decision']}",
                f"추천 답안: {question['recommended_option_id']}",
                f"질문: {question['question']}",
                "",
                "선택지:",
                *[f"- {opt['id']}: {opt['label']} — {opt['description']}" for opt in question["options"]],
                "- 직접 입력 가능",
                "",
                f"답변 누적 명령: python3 scripts/apply_intake_answer.py {run_id} --option <option-id>",
                f"재실행 명령: bash scripts/run_codex_pipeline.sh {run_id} --guided-intake",
                "",
            ]
        ),
        encoding="utf-8",
    )

    manifest_path = run / "manifest.json"
    manifest = read_json(manifest_path) or {"run_id": run_id}
    intake = manifest.setdefault("intake", {})
    intake.setdefault("mode", "directed")
    interview = intake.setdefault("interview", {})
    interview["needed"] = True
    interview["style"] = "ask_user_question + deep_interview"
    unresolved = set(interview.get("unresolved") or [])
    unresolved.add("external_adapter_policy")
    interview["unresolved"] = sorted(unresolved)
    stages = manifest.setdefault("stages", [])
    stages.append(
        {
            "name": "intake",
            "status": "blocked_for_user_question",
            "outputs": [
                f"runs/{run_id}/outputs/intake_questions.json",
                f"runs/{run_id}/outputs/intake_questions.md",
            ],
            "notes": ["external adapter policy is required before connect/frame/analyze stages."],
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_prompt_block(plan: dict[str, Any]) -> None:
    if plan.get("status") == "none":
        print("[external adapter plan]\n- mode: none\n- selected_categories: []")
        return
    print("[external adapter plan]")
    print(f"- file: runs/{plan['run_id']}/input/external_adapter_plan.json")
    print(f"- mode: {plan['mode']}")
    print(f"- selected_categories: {', '.join(plan['selected_categories']) or '(none)'}")
    print(f"- available_categories: {', '.join(plan['available_categories']) or '(none yet)'}")
    print(f"- unavailable_categories: {', '.join(plan['unavailable_categories']) or '(none)'}")
    print(f"- interpretation_guards: {', '.join(plan['interpretation_guards'])}")
    print("- category contracts:")
    for contract in plan.get("category_contracts") or []:
        layers = ", ".join(contract["metric_layers"])
        print(f"  - {contract['category']}: layers={layers}; meaning={contract['meaning']}")
    print("- Use this as orchestration context only. Do not fabricate missing adapter snapshots.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare external adapter plan from guided intake state.")
    parser.add_argument("run_id")
    parser.add_argument("--user-request", default="")
    parser.add_argument("--require-if-relevant", action="store_true")
    parser.add_argument("--print-prompt-block", action="store_true")
    args = parser.parse_args()

    run = pathlib.Path("runs") / args.run_id
    run.mkdir(parents=True, exist_ok=True)
    policy, policy_path = find_adapter_policy(run)

    if args.require_if_relevant and request_needs_adapter_policy(args.user_request) and not policy:
        write_adapter_question(args.run_id, run, args.user_request)
        print("external_adapter_policy question required")
        return 3

    plan = build_plan(args.run_id, run, policy, policy_path)
    input_path, root_path = write_plan(run, plan)

    if args.print_prompt_block:
        print_prompt_block(plan)
    else:
        print(f"wrote: {input_path}")
        print(f"wrote: {root_path}")
        print(f"selected_categories: {', '.join(plan['selected_categories']) or '(none)'}")
        if plan["unavailable_categories"]:
            print(f"unavailable_categories: {', '.join(plan['unavailable_categories'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
