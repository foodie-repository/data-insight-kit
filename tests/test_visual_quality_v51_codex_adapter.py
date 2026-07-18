"""Codex thin-adapter packaging for the shared data-insight-kit core."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess


KIT_ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((KIT_ROOT / path).read_text(encoding="utf-8"))


def test_codex_manifest_is_a_validator_compatible_v022_plugin_with_marketplace_metadata():
    manifest = _json(".codex-plugin/plugin.json")

    assert manifest["name"] == "data-insight-kit"
    assert manifest["version"] == "0.2.2"
    assert manifest["license"] == "MIT"
    assert manifest["skills"] == "./skills/"
    assert "hooks" not in manifest
    assert (KIT_ROOT / ".codex" / "hooks.json").is_file()
    assert "mcpServers" not in manifest
    assert "apps" not in manifest
    interface = manifest["interface"]
    assert interface["displayName"] == "Data Insight Kit"
    assert interface["developerName"] == "foodie"
    assert interface["category"] == "Productivity"
    assert interface["capabilities"] == ["Interactive", "Read", "Write"]
    assert interface["defaultPrompt"]


def test_codex_hook_routes_only_to_the_shared_checkpoint_guard():
    hooks = _json(".codex/hooks.json")

    assert list(hooks["hooks"]) == ["PreToolUse"]
    groups = hooks["hooks"]["PreToolUse"]
    assert len(groups) == 1
    assert groups[0]["matcher"] == "apply_patch|Bash"
    commands = [item["command"] for item in groups[0]["hooks"]]
    assert len(commands) == 1
    assert "scripts/dik_checkpoint_hook.py" in commands[0]
    assert "PLUGIN_ROOT" in commands[0]


def test_run_pipeline_skill_is_runtime_neutral_and_resolves_the_product_root():
    document = (KIT_ROOT / "skills" / "run-pipeline" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "Claude Code와 Codex가 함께 사용하는" in document
    assert "KIT_ROOT" in document
    assert "Codex에서는 이 파일을 직접 실행하지 않고" not in document


def test_codex_adapter_keeps_standalone_html_and_has_no_host_widget_dependency():
    surfaces = [
        KIT_ROOT / ".codex-plugin" / "plugin.json",
        KIT_ROOT / ".codex" / "hooks.json",
        KIT_ROOT / "skills" / "run-pipeline" / "SKILL.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in surfaces)

    assert "dashboard.html" in combined
    assert "checkpoint" in combined
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


def test_codex_install_docs_use_marketplace_qualified_commands():
    document = (KIT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "codex plugin marketplace add /path/to/data-insight-kit" in document
    assert "codex plugin add data-insight-kit@data-insight-kit" in document


def test_codex_adapter_reaches_the_shared_core_dry_run():
    result = subprocess.run(
        ["bash", "scripts/run_codex_pipeline.sh", "_codex-adapter-test", "--dry-run"],
        cwd=KIT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "checkpoint:data_profile" in result.stdout
    assert "checkpoint:report_outline" in result.stdout
    assert "render_dashboard_v5.py" in result.stdout
    assert "--post-communicate" in result.stdout
