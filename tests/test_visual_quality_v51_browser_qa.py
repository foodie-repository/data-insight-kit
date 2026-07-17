"""Browser and eyes-on QA contracts for visual-quality v5.1."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess
import sys


EXPECTED_VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "compact": {"width": 736, "height": 1000},
    "mobile": {"width": 390, "height": 844},
    "narrow": {"width": 320, "height": 800},
}

OBSERVATIONS = {
    "copy_clarity": ["대상·기간·단위가 제목과 부제에서 바로 읽힌다."],
    "information_hierarchy": ["핵심 지표 다음에 주 차트가 배치된다."],
    "color_meaning": ["색과 선 모양이 함께 계열을 구분한다."],
    "scale_integrity": ["막대는 0 기준선을 사용한다."],
    "labels_legends": ["라벨과 범례가 plot을 가리지 않는다."],
    "spacing_density": ["네 화면에서 과도한 공백이나 잘림이 없다."],
}

KIT_ROOT = Path(__file__).resolve().parents[1]


def _visual_review_api():
    try:
        module = importlib.import_module("dashboard_v5.visual_review")
    except ModuleNotFoundError:
        return None, None, None
    return (
        getattr(module, "ensure_visual_review_draft", None),
        getattr(module, "record_visual_review", None),
        getattr(module, "validate_visual_review", None),
    )


def _write_screenshots(output_dir, names=EXPECTED_VIEWPORTS):
    for name in names:
        (output_dir / f"qa_render_{name}.png").write_bytes(f"png-{name}".encode())


def test_v51_browser_qa_uses_all_four_release_viewports():
    from dashboard_v5.browser_qa import VIEWPORTS

    assert VIEWPORTS == EXPECTED_VIEWPORTS


def test_v51_visual_blockers_cover_labels_tooltip_small_text_and_color_only():
    import dashboard_v5.browser_qa as browser_qa

    validate = getattr(browser_qa, "_visual_quality_blockers", None)
    assert callable(validate), "browser QA visual-quality blocker is missing"
    metrics = {
        "qualityContract": "v5.1",
        "smallEssentialText": [
            {"component": "hero-chart", "selector": "component-desc", "fontSize": 10}
        ],
        "chartVisuals": [
            {
                "id": "c1",
                "canvas": {"left": 0, "top": 0, "right": 320, "bottom": 220},
                "plots": [{"left": 40, "top": 30, "right": 280, "bottom": 190}],
                "legend": None,
                "labels": [
                    {"left": 250, "top": 180, "right": 330, "bottom": 204},
                    {"left": 260, "top": 184, "right": 315, "bottom": 208},
                ],
                "tooltipConfine": False,
                "decalEnabled": False,
                "seriesCues": [
                    {"lineType": "solid", "symbol": "circle", "endLabel": False},
                    {"lineType": "solid", "symbol": "circle", "endLabel": False},
                ],
            }
        ],
    }

    blocks = validate("narrow", metrics)

    assert "narrow essential text below 11px: hero-chart/component-desc" in blocks
    assert "narrow chart labels overlap: c1" in blocks
    assert "narrow chart label clipped by canvas: c1" in blocks
    assert "narrow chart tooltip is not confined: c1" in blocks
    assert "narrow chart series rely on color only: c1" in blocks


def test_visual_review_draft_blocks_until_all_screenshots_are_inspected(tmp_path):
    ensure_draft, _record_review, validate_review = _visual_review_api()
    assert callable(ensure_draft), "visual review draft builder is missing"
    assert callable(validate_review), "visual review validator is missing"
    _write_screenshots(tmp_path, names=("desktop", "mobile"))

    record = ensure_draft(tmp_path, EXPECTED_VIEWPORTS)
    issues = validate_review(record, tmp_path, EXPECTED_VIEWPORTS)

    assert any("qa_render_compact.png" in issue for issue in issues)
    assert any("qa_render_narrow.png" in issue for issue in issues)
    assert any("visual review is not complete" in issue for issue in issues)


def test_visual_review_pass_requires_hashes_all_observations_and_orchestrator(tmp_path):
    ensure_draft, record_review, validate_review = _visual_review_api()
    assert callable(ensure_draft), "visual review draft builder is missing"
    assert callable(record_review), "visual review recorder is missing"
    assert callable(validate_review), "visual review validator is missing"
    _write_screenshots(tmp_path)
    ensure_draft(tmp_path, EXPECTED_VIEWPORTS)

    record = record_review(
        tmp_path,
        status="pass",
        observations=OBSERVATIONS,
        reviewer_role="orchestrator",
        reviewed_at="2026-07-17T12:00:00+09:00",
    )

    assert validate_review(record, tmp_path, EXPECTED_VIEWPORTS) == []
    (tmp_path / "qa_render_narrow.png").write_bytes(b"changed")
    assert any(
        "hash mismatch" in issue
        for issue in validate_review(record, tmp_path, EXPECTED_VIEWPORTS)
    )


def test_existing_completed_visual_review_is_preserved_only_while_hashes_match(tmp_path):
    ensure_draft, record_review, _validate_review = _visual_review_api()
    assert callable(ensure_draft), "visual review draft builder is missing"
    assert callable(record_review), "visual review recorder is missing"
    _write_screenshots(tmp_path)
    ensure_draft(tmp_path, EXPECTED_VIEWPORTS)
    completed = record_review(
        tmp_path,
        status="pass",
        observations=OBSERVATIONS,
        reviewer_role="orchestrator",
        reviewed_at="2026-07-17T12:00:00+09:00",
    )

    preserved = ensure_draft(tmp_path, EXPECTED_VIEWPORTS)
    assert preserved == completed

    (tmp_path / "qa_render_compact.png").write_bytes(b"new-render")
    replaced = ensure_draft(tmp_path, EXPECTED_VIEWPORTS)
    assert replaced["status"] == "revise"
    assert replaced["reviewed_at"] is None
    assert not any(item["inspected"] for item in replaced["screenshots"].values())
    assert json.loads((tmp_path / "visual_review.json").read_text()) == replaced


def test_record_visual_review_cli_writes_orchestrator_observations(tmp_path):
    ensure_draft, _record_review, validate_review = _visual_review_api()
    assert callable(ensure_draft), "visual review draft builder is missing"
    assert callable(validate_review), "visual review validator is missing"
    _write_screenshots(tmp_path)
    ensure_draft(tmp_path, EXPECTED_VIEWPORTS)
    command = [
        sys.executable,
        str(KIT_ROOT / "scripts" / "record_visual_review.py"),
        str(tmp_path),
        "--status",
        "pass",
        "--reviewed-at",
        "2026-07-17T12:00:00+09:00",
    ]
    for category, values in OBSERVATIONS.items():
        command.extend([f"--{category.replace('_', '-')}", values[0]])

    result = subprocess.run(
        command,
        cwd=KIT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    record = json.loads((tmp_path / "visual_review.json").read_text())
    assert validate_review(record, tmp_path, EXPECTED_VIEWPORTS) == []
