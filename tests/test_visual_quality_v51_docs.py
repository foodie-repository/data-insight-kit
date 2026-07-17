"""Operating-document coverage for the visual-quality v5.1 contract."""

from __future__ import annotations

from pathlib import Path


KIT_ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (KIT_ROOT / path).read_text(encoding="utf-8")


def test_design_system_links_v51_planning_and_visual_quality_contracts():
    document = _text("docs/dashboard-design-system.md")

    assert "docs/specs/visual-quality-convergence-v5.1.md" in document
    assert "계획 품질 계약" in document
    assert "시각 품질 계약" in document
    assert "문장 생성기" in document
    for term in ("copy_context", "scale_policy", "palette_policy", "non_color_channels"):
        assert term in document


def test_pipeline_contract_requires_four_viewports_and_hash_bound_eyes_on_review():
    document = _text("docs/pipeline-contract.md")

    assert "1440×1000" in document
    assert "736×1000" in document
    assert "390×844" in document
    assert "320×800" in document
    assert "outputs/visual_review.json" in document
    assert "screenshot hash" in document
    assert "status=pass" in document
    assert "quality_contract.version = \"v5.1\"" in document


def test_v51_docs_require_thousands_grouping_without_corrupting_dates_or_ids():
    spec = _text("docs/specs/visual-quality-convergence-v5.1.md")
    design = _text("docs/dashboard-design-system.md")
    contract = _text("docs/pipeline-contract.md")

    for document in (spec, design, contract):
        assert "천 단위 구분기호" in document
    assert "10,970건" in spec
    assert "238,228만원" in spec
    assert "날짜·기간" in spec
    assert "코드·ID" in spec


def test_v5_v51_smoke_comparison_records_both_runs_and_release_boundaries():
    comparison = _text("docs/v5-v51-smoke-comparison.md")

    for run_id in (
        "sbiz-gangnam-v5-freeform-smoke-20260714",
        "sbiz-gangnam-v51-visual-quality-smoke-20260717",
        "apt-sale-v5-freeform-smoke-20260714",
        "apt-sale-v51-visual-quality-smoke-20260717",
    ):
        assert run_id in comparison
    assert "10개 공통 기준" in comparison
    assert "WARN 개수" in comparison
    assert "runs/*" in comparison
    assert "git commit 대상이 아니다" in comparison


def test_public_readme_explains_v51_artifacts_and_shared_core_adapter_boundary():
    document = _text("README.md")

    assert "v5.1" in document
    assert "outputs/visual_review.json" in document
    assert "qa_render_compact.png" in document
    assert "qa_render_narrow.png" in document
    assert "Claude Code" in document and "Codex" in document
    assert "얇은 어댑터" in document
    assert "별도 kit" in document
    assert "docs/v5-v51-smoke-comparison.md" in document


def test_agents_and_shared_skill_require_every_render_and_actual_orchestrator_record():
    for path in ("AGENTS.md", "skills/run-pipeline/SKILL.md"):
        document = _text(path)
        for name in ("desktop", "compact", "mobile", "narrow"):
            assert f"qa_render_{name}.png" in document
        assert "visual_review.json" in document
        assert "오케스트레이터" in document
        assert "status=pass" in document
        assert "hash" in document


def test_changelog_resume_point_moves_to_snapshot_smoke_after_adapter_packaging():
    document = _text("CHANGELOG.md")
    progress = document.split("## [Unreleased] — dashboard profile v4", 1)[0]

    assert "v5.1 구현 Task 2~6 완료" in progress
    assert "b511b4f" in progress
    assert "다음 작업" in progress
    assert "Claude Code thin adapter 패키징 완료" in progress
    assert "Codex thin adapter 패키징 완료" in progress
    assert "snapshot smoke" in progress
