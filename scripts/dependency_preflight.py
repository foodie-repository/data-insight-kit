#!/usr/bin/env python3
"""Dependency preflight for expert-guided analysis routing (spec §7).

frame 단계 이후 실행되어 `runs/<run-id>/input/dependency_plan.json`을 작성한다.

원칙 (spec §7.3):
- 이 스크립트는 **절대 설치하지 않는다**. 설치 명령 문자열만 출력한다.
  실제 설치는 사용자가 analysis_strategy checkpoint에서 명시 옵션으로 승인한 뒤
  wrapper가 실행한다.
- 설치 여부 판정은 kit 전용 `.venv`(`<kit-root>/.venv`) 기준이다. 현재 인터프리터나
  워크스페이스 venv에 같은 패키지가 있어도 "설치됨"으로 보지 않는다.
- 허용 패키지의 단일 원천은 `methods/method_registry.json`의 `dependency_allowlist`다.
- stdlib만 사용한다 (jsonschema 자체 검증은 가능할 때만 best-effort).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# stage_guard.py lives next to this file (siblings in scripts/). Mirror
# checkpoint_gate.py's import pattern so approval detection/validation stays
# identical across guard, gate, and this preflight.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_guard  # noqa: E402

KIT_ROOT_DEFAULT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA_VERSION = "data-insight-kit.dependency_plan.v1"
VALID_EXTRAS = ("stats", "ml")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}")
    return data if isinstance(data, dict) else {}


def load_registry(kit_root: Path) -> dict:
    path = kit_root / "methods" / "method_registry.json"
    registry = load_json(path)
    if not registry.get("methods") or not registry.get("dependency_allowlist"):
        raise SystemExit(f"method registry missing or incomplete: {path}")
    return registry


def required_extras_for_run(run: Path, registry: dict) -> tuple[list[str], list[str]]:
    """(required_extras, issues) — selected_methods 기준, 단일 원천은 registry."""
    route_data = load_json(run / "outputs" / "method_route.json")
    methods_by_id = {m["id"]: m for m in registry["methods"]}
    issues: list[str] = []
    extras: set[str] = set()
    for method_id in route_data.get("selected_methods") or []:
        method = methods_by_id.get(str(method_id))
        if method is None:
            issues.append(f"method not in registry: {method_id}")
            continue
        for group in method.get("dependency_groups") or []:
            if group not in VALID_EXTRAS:
                issues.append(f"method {method_id} references unknown group: {group}")
                continue
            extras.add(group)
    return sorted(extras), issues


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def site_packages_dirs(venv: Path) -> list[Path]:
    return sorted(venv.glob("lib/python*/site-packages"))


def installed_dist_names(venv: Path) -> set[str]:
    names: set[str] = set()
    for sp in site_packages_dirs(venv):
        for info in sp.glob("*.dist-info"):
            # e.g. scikit_learn-1.4.2.dist-info -> scikit_learn
            base = info.name[: -len(".dist-info")]
            names.add(normalize(base.rsplit("-", 1)[0]))
    return names


def probe_extras(kit_root: Path, registry: dict, required: list[str]) -> tuple[list[str], list[str], list[dict]]:
    """kit .venv 기준으로 (installed_extras, missing_extras, package detail)."""
    venv = kit_root / ".venv"
    dists = installed_dist_names(venv) if venv.exists() else set()
    allowlist = registry["dependency_allowlist"]
    installed: list[str] = []
    missing: list[str] = []
    packages: list[dict] = []
    for extra in required:
        pkg_names = allowlist.get(extra) or []
        extra_ok = bool(pkg_names)
        for pkg in pkg_names:
            ok = normalize(pkg) in dists
            packages.append({"extra": extra, "name": pkg, "installed": ok, "version": None})
            extra_ok = extra_ok and ok
        (installed if extra_ok else missing).append(extra)
    return installed, missing, packages


def build_plan(run_id: str, run: Path, kit_root: Path, registry: dict) -> tuple[dict, list[str]]:
    required, issues = required_extras_for_run(run, registry)
    installed, missing, packages = probe_extras(kit_root, registry, required)
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": now_iso(),
        "environment": {
            "kit_root": str(kit_root),
            "venv_path": str(kit_root / ".venv"),
            "basis": "kit_local_venv",
            "python": sys.version.split()[0],
        },
        "required_extras": required,
        "installed": installed,
        "missing": missing,
        "packages": packages,
        "allowlist_ref": "methods/method_registry.json",
        "approval": None,
        "install_result": None,
    }
    # 같은 required_extras로 재실행하면 기존 승인/설치 기록을 보존한다.
    # required가 달라졌으면 이전 승인은 무효 (승인 시점 잠금과 일관, spec §7.2).
    existing = load_json(run / "input" / "dependency_plan.json")
    if existing.get("required_extras") == required:
        plan["approval"] = existing.get("approval")
        plan["install_result"] = existing.get("install_result")
    return plan, issues


def install_command(kit_root: Path, missing: list[str]) -> str | None:
    if not missing:
        return None
    extras = " ".join(f"--extra {g}" for g in missing)
    return f"uv sync --project {kit_root} {extras}"


def validate_plan_best_effort(plan: dict, kit_root: Path) -> str:
    try:
        import jsonschema  # type: ignore
    except Exception:
        return "schema check skipped (jsonschema unavailable)"
    schema_path = kit_root / "schemas" / "dependency_plan.schema.json"
    try:
        jsonschema.validate(plan, json.loads(schema_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise SystemExit(f"dependency_plan schema validation failed: {exc}")
    return "schema check OK"


def truncate_error(text: str | None, limit: int = 600) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def downgrade_method_route(run: Path, registry: dict, reason: str) -> str | None:
    """설치 실패/미승인 시 method_route.json을 core-only로 강등한다 (spec §7.3).

    - core method(빈 dependency_groups)만 남긴다.
    - 새 route는 남은 method에 diagnostic이 있으면 diagnostic, 아니면 descriptive.
    - downgraded_from은 이미 기록돼 있으면 원본을 유지한다(중간값으로 덮지 않는다).
    반환값은 강등된 route (없으면 None)."""
    mr_path = run / "outputs" / "method_route.json"
    if not mr_path.exists():
        print("- WARN: method_route.json이 없어 강등을 기록하지 못했습니다.")
        return None
    route_data = load_json(mr_path)
    methods_by_id = {m["id"]: m for m in registry["methods"]}
    selected = [str(m) for m in route_data.get("selected_methods") or []]
    core = [m for m in selected if not (methods_by_id.get(m) or {}).get("dependency_groups")]
    if not core:
        print("- WARN: core method가 없어 강등 대체 route를 찾지 못했습니다. method_route를 유지합니다.")
        return None
    prev_route = route_data.get("route")
    new_route = "diagnostic" if any(
        (methods_by_id.get(m) or {}).get("route") == "diagnostic" for m in core
    ) else "descriptive"
    route_data["route"] = new_route
    route_data["selected_methods"] = core
    route_data["dependency_groups"] = []
    if not route_data.get("downgraded_from"):
        route_data["downgraded_from"] = prev_route
    route_data["downgrade_reason"] = reason
    route_data["allowed_scope"] = "핵심 방법(순위·분포·구성·추세·품질 진단)만 사용 가능"
    mr_path.write_text(json.dumps(route_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return new_route


def apply_approval(run: Path, kit_root: Path, registry: dict, plan: dict) -> int:
    """analysis_strategy 승인 답변의 dependency_decision에 따라 설치/강등을 적용한다.

    wrapper가 analysis_strategy checkpoint 통과 직후에만 호출한다. 승인 답변이 없거나
    검증에 실패하면 non-zero, 실제 설치 실패는 강등으로 정상 처리하므로 0을 반환한다."""
    answer = stage_guard.latest_answers(run).get("analysis_strategy")
    if not answer:
        print("✗ apply-approval: analysis_strategy 승인 답변을 찾지 못했습니다.")
        return 1
    problems = stage_guard.validate_answer(run, "analysis_strategy", answer)
    if problems:
        print("✗ apply-approval: analysis_strategy 답변 검증 실패:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    decision = (answer.get("maps_to") or {}).get("dependency_decision")
    missing = [str(g) for g in plan.get("missing") or []]
    out = run / "input" / "dependency_plan.json"

    if not missing:
        # 설치 대상 extra가 없던 run(단순 분석 등). 적용할 설치/강등이 없다.
        print("apply-approval: 설치가 필요한 추가 기능이 없어 적용할 항목이 없습니다.")
        return 0

    answer_id = answer.get("answer_id")
    now = now_iso()

    if decision == "install":
        attempted: list[str] = []
        command_parts: list[str] = []
        error_text: str | None = None
        for extra in missing:
            cmd = ["uv", "sync", "--project", str(kit_root), "--extra", extra]
            command_parts.append(" ".join(cmd))
            attempted.append(extra)
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                error_text = truncate_error(proc.stderr or proc.stdout)
                break
        command_str = " && ".join(command_parts)
        plan["approval"] = {
            "answer_id": answer_id,
            "checkpoint_id": "analysis_strategy",
            "dependency_decision": "install",
            "approved_at": now,
        }
        if error_text is None:
            plan["installed"] = sorted(set([str(g) for g in plan.get("installed") or []] + missing))
            plan["missing"] = []
            plan["install_result"] = {
                "status": "success",
                "extras": missing,
                "command": command_str,
                "completed_at": now_iso(),
                "error": None,
                "fallback_route": None,
            }
            print(f"apply-approval: 설치 성공 — {', '.join(missing)}")
        else:
            fallback = downgrade_method_route(run, registry, f"설치 실패: {error_text}")
            plan["install_result"] = {
                "status": "failed",
                "extras": attempted,
                "command": command_str,
                "completed_at": now_iso(),
                "error": error_text,
                "fallback_route": fallback,
            }
            print(f"apply-approval: 설치 실패 — route를 {fallback or '유지'}(으)로 강등했습니다.")
    elif decision == "skip_install":
        plan["approval"] = {
            "answer_id": answer_id,
            "checkpoint_id": "analysis_strategy",
            "dependency_decision": "skip_install",
            "approved_at": now,
        }
        # install_result는 null 유지 (시도한 설치가 없음).
        fallback = downgrade_method_route(run, registry, "사용자가 설치 없이 진행을 선택함")
        # 강등 후 이 route는 extra가 필요 없다. 승인 시점 잠금 검증(stage guard)이
        # missing 비어 있지 않음을 상향으로 오인하지 않도록 missing을 비운다.
        plan["missing"] = []
        print(f"apply-approval: 설치 없이 진행 — route를 {fallback or '유지'}(으)로 강등했습니다.")
    else:
        # adjust / 미기록 / 미인식: continue_pipeline=false 매핑이라 여기 도달하지 않아야
        # 하지만 방어적으로 no-op.
        print(f"apply-approval: dependency_decision='{decision}' — 적용할 설치/강등이 없습니다.")
        return 0

    validate_plan_best_effort(plan, kit_root)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Write dependency_plan.json for a run (never installs).")
    parser.add_argument("run_id")
    parser.add_argument("--kit-root", type=Path, default=KIT_ROOT_DEFAULT)
    parser.add_argument("--runs-root", type=Path, default=None,
                        help="기본값은 <kit-root>/runs (stage_guard와 동일하게 cwd 기준 상대 runs도 허용)")
    parser.add_argument("--print-install-command", action="store_true",
                        help="설치가 필요한 extra의 uv 명령만 출력 (실행하지 않음)")
    parser.add_argument("--apply-approval", action="store_true",
                        help="analysis_strategy 승인 답변의 dependency_decision에 따라 설치/강등을 적용한다.")
    args = parser.parse_args()

    kit_root = args.kit_root.resolve()
    runs_root = args.runs_root if args.runs_root is not None else kit_root / "runs"
    run = runs_root / args.run_id
    if not run.exists():
        raise SystemExit(f"run not found: {run}")

    registry = load_registry(kit_root)
    plan, issues = build_plan(args.run_id, run, kit_root, registry)

    (run / "input").mkdir(parents=True, exist_ok=True)
    out = run / "input" / "dependency_plan.json"
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    check_note = validate_plan_best_effort(plan, kit_root)
    print(f"dependency preflight: {out} ({check_note})")
    print(f"- required extras: {plan['required_extras'] or '없음'}")
    print(f"- already installed (kit .venv 기준): {plan['installed'] or '없음'}")
    print(f"- missing (설치 승인 필요): {plan['missing'] or '없음'}")
    for issue in issues:
        print(f"- WARN: {issue}")

    if args.apply_approval:
        rc = apply_approval(run, kit_root, registry, plan)
        if rc != 0:
            return rc
        return 1 if issues else 0

    cmd = install_command(kit_root, plan["missing"])
    if cmd and args.print_install_command:
        print("설치는 이 스크립트가 실행하지 않습니다. 사용자 승인 후 wrapper가 실행할 명령:")
        print(f"  {cmd}")
    if issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
