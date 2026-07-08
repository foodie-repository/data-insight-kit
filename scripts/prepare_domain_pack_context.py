#!/usr/bin/env python3
"""Prepare a compact domain-pack prompt context for data-insight-kit stages.

Domain packs are optional. This helper never changes core pipeline behavior by
itself; it only resolves a user-selected domain pack and writes a small context
file that later stages can read. The core contract still wins when a domain pack
and `docs/pipeline-contract.md` disagree.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
from datetime import datetime, timezone
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
CONTEXT_VERSION = "data-insight-kit.domain_pack_context.v1"
ARTIFACT_ORDER = [
    ("terminology", "terminology.md"),
    ("kpi_rules", "kpi-rules.md"),
    ("interview_questions", "interview-questions.md"),
    ("dashboard_patterns", "dashboard-patterns.md"),
    ("report_rubric", "report-rubric.md"),
    ("qa_rules", "qa-rules.md"),
]


def read_json(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


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


def load_structured(path: pathlib.Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    parsed = load_yaml_if_available(text)
    if parsed is not None:
        return parsed
    return parse_simple_keys(text)


def parse_simple_keys(text: str) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    for raw in text.splitlines():
        match = re.match(r"^\s*([A-Za-z0-9_.-]+):\s*(.+?)\s*$", raw)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip().strip('"').strip("'")
        if key in {"domain_pack", "domain_pack_path", "domain_ref", "registry_ref"}:
            out[key] = value
    return out or None


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def candidate_ref_paths(run: pathlib.Path) -> list[pathlib.Path]:
    return [
        run / "input" / "domain_pack_ref.json",
        run / "input" / "domain_pack_ref.txt",
        run / "input" / "domain_pack.yaml",
        run / "input" / "intake.yaml",
        run / "intake.yaml",
        run / "input" / "intake_draft.yaml",
        run / "intake_draft.yaml",
        run / "input" / "external_adapter_plan.json",
        run / "external_adapter_plan.json",
        run / "manifest.json",
    ]


def extract_domain_ref(data: dict[str, Any]) -> str | None:
    candidates = [
        data.get("domain_pack"),
        data.get("domain_pack_path"),
        data.get("domain_ref"),
        nested_get(data, "domain_pack", "path"),
        nested_get(data, "intake", "domain_pack"),
        nested_get(data, "intake", "domain_pack_path"),
        nested_get(data, "intake", "domain_ref"),
        nested_get(data, "intake", "external_adapters", "registry_ref"),
        nested_get(data, "external_adapters", "registry_ref"),
        data.get("registry_ref"),
    ]
    for value in candidates:
        if not value:
            continue
        ref = str(value).strip()
        if ref and ref.startswith("domains/") and "<domain>" not in ref:
            return ref
    return None


def find_domain_ref(run: pathlib.Path) -> str | None:
    env_ref = os.environ.get("DIK_DOMAIN_PACK", "").strip() or os.environ.get("VK_DOMAIN_PACK", "").strip()
    if env_ref:
        return env_ref
    for path in candidate_ref_paths(run):
        if not path.exists():
            continue
        if path.suffix == ".txt":
            ref = path.read_text(encoding="utf-8", errors="replace").strip()
            if ref:
                return ref
            continue
        data = load_structured(path)
        if not data:
            continue
        ref = extract_domain_ref(data)
        if ref:
            return ref
    return None


def resolve_domain_yaml(ref: str) -> pathlib.Path:
    path = pathlib.Path(ref)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise SystemExit(f"domain pack must be inside data-insight-kit: {path}") from exc
    if path.is_dir():
        path = path / "domain.yaml"
    if path.name != "domain.yaml":
        raise SystemExit(f"domain pack reference must point to domain.yaml or its directory: {path}")
    if not path.exists():
        raise SystemExit(f"domain pack not found: {path}")
    return path


def domain_metadata(domain_yaml: pathlib.Path) -> dict[str, Any]:
    data = load_structured(domain_yaml) or {}
    artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), dict) else {}
    return {
        "schema_version": data.get("schema_version", "data-insight-kit.domain.v1"),
        "domain_id": data.get("domain_id", domain_yaml.parent.name),
        "display_name": data.get("display_name", domain_yaml.parent.name),
        "description": data.get("description", ""),
        "activation": data.get("activation", {}),
        "default_intake": data.get("default_intake", {}),
        "external_context": data.get("external_context", {}),
        "artifacts": artifacts,
    }


def artifact_paths(domain_yaml: pathlib.Path, metadata: dict[str, Any]) -> list[tuple[str, pathlib.Path]]:
    artifacts = metadata.get("artifacts") if isinstance(metadata.get("artifacts"), dict) else {}
    out: list[tuple[str, pathlib.Path]] = [("domain", domain_yaml)]
    for key, default_name in ARTIFACT_ORDER:
        rel_name = str(artifacts.get(key) or default_name)
        path = (domain_yaml.parent / rel_name).resolve()
        if path.exists():
            out.append((key, path))
    return out


def read_artifact(path: pathlib.Path, max_chars: int = 5500) -> str:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "\n…"


def build_context(run_id: str, domain_yaml: pathlib.Path, ref: str) -> dict[str, Any]:
    metadata = domain_metadata(domain_yaml)
    artifacts = []
    for key, path in artifact_paths(domain_yaml, metadata):
        artifacts.append(
            {
                "key": key,
                "path": path.relative_to(ROOT).as_posix(),
                "content": read_artifact(path),
            }
        )
    return {
        "schema_version": CONTEXT_VERSION,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_ref": ref,
        "domain_yaml": domain_yaml.relative_to(ROOT).as_posix(),
        "domain_id": metadata["domain_id"],
        "display_name": metadata["display_name"],
        "description": metadata["description"],
        "activation": metadata["activation"],
        "default_intake": metadata["default_intake"],
        "external_context": metadata["external_context"],
        "artifacts": artifacts,
        "notes": [
            "Domain pack is advisory. docs/pipeline-contract.md and schemas remain authoritative.",
            "Use domain rules to ask better questions and guard interpretation; do not auto-conclude without user confirmation.",
        ],
    }


def write_context(run: pathlib.Path, context: dict[str, Any]) -> tuple[pathlib.Path, pathlib.Path]:
    input_path = run / "input" / "domain_pack_context.md"
    root_path = run / "domain_pack_context.md"
    text = render_markdown(context)
    for path in (input_path, root_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return input_path, root_path


def render_markdown(context: dict[str, Any]) -> str:
    lines = [
        "# Domain Pack Context",
        "",
        f"- schema_version: `{context['schema_version']}`",
        f"- domain_id: `{context['domain_id']}`",
        f"- display_name: {context['display_name']}",
        f"- domain_yaml: `{context['domain_yaml']}`",
        "",
        "## Usage Rules",
        "",
        "- This domain pack is advisory and cannot override `docs/pipeline-contract.md`.",
        "- Use it to ask better domain questions, define KPI candidates, adapt language, and apply domain QA guards.",
        "- If a domain rule requires evidence not present in the data, ask the user or record a limitation instead of inventing a conclusion.",
        "",
    ]
    if context.get("description"):
        lines.extend(["## Description", "", str(context["description"]), ""])
    for artifact in context.get("artifacts") or []:
        lines.extend(
            [
                f"## {artifact['key']}: {artifact['path']}",
                "",
                artifact["content"],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def print_prompt_block(context_path: pathlib.Path) -> None:
    print("[domain pack context]")
    print(context_path.read_text(encoding="utf-8", errors="replace"))
    print("[domain pack context end]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare optional data-insight-kit domain pack context.")
    parser.add_argument("run_id")
    parser.add_argument("--print-prompt-block", action="store_true")
    args = parser.parse_args()

    run = RUNS / args.run_id
    run.mkdir(parents=True, exist_ok=True)
    context_path = run / "input" / "domain_pack_context.md"
    if args.print_prompt_block:
        if context_path.exists():
            print_prompt_block(context_path)
        return 0

    ref = find_domain_ref(run)
    if not ref:
        # Remove stale context if a previous run used a pack but the current
        # intake/env no longer selects one.
        for path in (run / "input" / "domain_pack_context.md", run / "domain_pack_context.md"):
            if path.exists():
                path.unlink()
        return 0
    domain_yaml = resolve_domain_yaml(ref)
    context = build_context(args.run_id, domain_yaml, ref)
    input_path, root_path = write_context(run, context)
    print(f"wrote: {input_path.relative_to(ROOT)}")
    print(f"wrote: {root_path.relative_to(ROOT)}")
    print(f"domain_id: {context['domain_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
