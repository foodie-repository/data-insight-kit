"""Release-level contracts for the public data-insight-kit v0.2.2 tree."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib


KIT_ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((KIT_ROOT / path).read_text(encoding="utf-8"))


def test_v022_has_one_version_across_project_and_both_adapters():
    project = tomllib.loads((KIT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((KIT_ROOT / "uv.lock").read_text(encoding="utf-8"))
    claude = _json(".claude-plugin/plugin.json")
    codex = _json(".codex-plugin/plugin.json")
    marketplace = _json(".claude-plugin/marketplace.json")
    locked_project = next(
        package for package in lock["package"] if package["name"] == "data-insight-kit"
    )

    assert {
        project["project"]["version"],
        locked_project["version"],
        claude["version"],
        codex["version"],
    } == {"0.2.2"}
    assert "version" not in marketplace["plugins"][0]


def test_codex_manifest_uses_default_hook_discovery_supported_by_validator():
    manifest = _json(".codex-plugin/plugin.json")

    assert "hooks" not in manifest
    assert (KIT_ROOT / ".codex" / "hooks.json").is_file()


def test_public_docs_include_remote_marketplace_install_commands():
    readme = (KIT_ROOT / "README.md").read_text(encoding="utf-8")
    guide = (KIT_ROOT / "GUIDE.md").read_text(encoding="utf-8")

    assert "codex plugin marketplace add foodie-repository/data-insight-kit --ref v0.2.2" in readme
    for document in (readme, guide):
        assert "claude plugin marketplace add foodie-repository/data-insight-kit" in document
        assert "claude plugin install data-insight-kit@data-insight-kit" in document


def test_release_spec_preserves_distribution_and_human_approval_boundaries():
    spec = (KIT_ROOT / "docs" / "specs" / "v0.2.2-release.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "git archive",
        "force push는 하지 않는다",
        "runs/*",
        "원격 설치 smoke",
        "블라인드 UAT",
        "실제 domain mode checkpoint 답변",
        "실제 statistical route dependency 승인",
    ):
        assert required in spec


def test_standalone_distribution_ignores_local_runtime_artifacts():
    ignore = (KIT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    for pattern in (
        ".venv/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".playwright-cli/",
        ".DS_Store",
    ):
        assert pattern in ignore


def test_install_check_dry_run_does_not_require_an_input_source():
    run_id = "_v022-install-check-no-source"
    with tempfile.TemporaryDirectory() as tmp:
        clean_root = Path(tmp) / "data-insight-kit"
        shutil.copytree(
            KIT_ROOT,
            clean_root,
            ignore=shutil.ignore_patterns(
                ".git",
                ".env",
                "runs",
                ".venv",
                ".pytest_cache",
                ".ruff_cache",
                ".playwright-cli",
                "__pycache__",
                "*.pyc",
            ),
        )
        result = subprocess.run(
            ["bash", "scripts/run_codex_pipeline.sh", run_id, "--dry-run"],
            cwd=clean_root,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "source preflight: 입력 없는 설치 확인 dry-run" in result.stdout
    assert "checkpoint:report_outline" in result.stdout
