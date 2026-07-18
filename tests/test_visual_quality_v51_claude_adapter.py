"""Claude Code thin-adapter packaging for the shared data-insight-kit core."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


KIT_ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((KIT_ROOT / path).read_text(encoding="utf-8"))


def test_claude_manifest_and_marketplace_point_to_the_plugin_root_once():
    manifest = _json(".claude-plugin/plugin.json")
    marketplace = _json(".claude-plugin/marketplace.json")
    entry = marketplace["plugins"][0]

    assert manifest["name"] == "data-insight-kit"
    assert manifest["version"] == "0.2.1"
    assert manifest["license"] == "MIT"
    assert entry["name"] == manifest["name"]
    assert entry["source"] == "./"
    assert entry["strict"] is True
    assert "version" not in entry, "plugin version must have one authority"


def test_claude_default_component_discovery_exposes_shared_skill_and_hook():
    skill = KIT_ROOT / "skills" / "run-pipeline" / "SKILL.md"
    hooks = _json("hooks/hooks.json")

    assert skill.is_file()
    assert skill.read_text(encoding="utf-8").startswith("---\nname: run-pipeline\n")
    assert list(hooks["hooks"]) == ["PreToolUse"]
    groups = hooks["hooks"]["PreToolUse"]
    assert len(groups) == 1
    assert groups[0]["matcher"] == "Write|Edit|Bash|AskUserQuestion"
    commands = [item["command"] for item in groups[0]["hooks"]]
    assert commands == [
        'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dik_checkpoint_hook.py"'
    ]


def test_claude_adapter_has_no_foreign_plugin_runtime_or_private_cache_dependency():
    surfaces = [
        KIT_ROOT / ".claude-plugin" / "plugin.json",
        KIT_ROOT / ".claude-plugin" / "marketplace.json",
        KIT_ROOT / "hooks" / "hooks.json",
        KIT_ROOT / "skills" / "run-pipeline" / "SKILL.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in surfaces)
    for forbidden in (
        ".codex/plugins/cache",
        "/Users/foodie/.codex/skills/visualize",
        "window.openai",
        "::codex-inline-vis",
        "dataAnalyticsWidgets",
        "plugin://data-analytics",
        "plugin://visualize",
    ):
        assert forbidden not in combined


@pytest.mark.skipif(shutil.which("claude") is None, reason="Claude Code CLI missing")
def test_claude_cli_strict_validation_and_session_discovery():
    validate = subprocess.run(
        ["claude", "plugin", "validate", "--strict", "."],
        cwd=KIT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr

    details = subprocess.run(
        [
            "claude",
            "--plugin-dir",
            ".",
            "plugin",
            "details",
            "data-insight-kit@inline",
        ],
        cwd=KIT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert details.returncode == 0, details.stdout + details.stderr
    assert "run-pipeline" in details.stdout
    assert "PreToolUse" in details.stdout


def test_shared_core_pipeline_dry_run_is_available_to_the_adapter():
    result = subprocess.run(
        ["bash", "scripts/run_codex_pipeline.sh", "_claude-adapter-test", "--dry-run"],
        cwd=KIT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "checkpoint:data_profile" in result.stdout
    assert "checkpoint:dashboard_storyboard" in result.stdout
    assert "render_dashboard_v5.py" in result.stdout
    assert "qa-post" in result.stdout


def test_claude_install_docs_use_the_marketplace_qualified_plugin_name():
    for path in ("README.md", "GUIDE.md"):
        document = (KIT_ROOT / path).read_text(encoding="utf-8")
        assert "/plugin marketplace add /path/to/data-insight-kit" in document
        assert "/plugin install data-insight-kit@data-insight-kit" in document
