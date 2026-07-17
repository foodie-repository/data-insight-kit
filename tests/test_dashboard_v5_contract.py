"""Dashboard freeform v5 layout and renderer contract tests."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.v5_fixtures import (
    minimal_chart_spec_v5,
    minimal_dashboard_data_v5,
    minimal_layout_v5,
)


def test_select_renderer_requires_explicit_triple_v5_contract():
    try:
        from dashboard_v5.contract import select_renderer
    except ModuleNotFoundError:
        pytest.fail("dashboard_v5.contract.select_renderer is not implemented")

    assert (
        select_renderer(
            minimal_chart_spec_v5(),
            minimal_dashboard_data_v5(),
            minimal_layout_v5(),
        )
        == "v5"
    )


def test_v5_without_layout_fails_closed():
    try:
        from dashboard_v5.contract import ContractError, select_renderer
    except ModuleNotFoundError:
        pytest.fail("dashboard_v5.contract renderer contract is not implemented")

    with pytest.raises(ContractError, match="v5.*dashboard_layout"):
        select_renderer(minimal_chart_spec_v5(), minimal_dashboard_data_v5(), None)


def test_legacy_and_v4_routes_stay_unchanged():
    from dashboard_v5.contract import select_renderer

    chart_spec = minimal_chart_spec_v5()
    data = minimal_dashboard_data_v5()
    chart_spec["dashboard_design"].pop("contract_version")
    data["meta"].pop("dashboard_profile_contract")
    assert select_renderer(chart_spec, data, None) == "legacy"

    chart_spec["dashboard_design"]["contract_version"] = "v4"
    data["meta"]["dashboard_profile_contract"] = "v4"
    assert select_renderer(chart_spec, data, None) == "v4"


def test_renderer_rejects_chart_data_contract_mismatch():
    from dashboard_v5.contract import ContractError, select_renderer

    data = minimal_dashboard_data_v5()
    data["meta"]["dashboard_profile_contract"] = "v4"
    with pytest.raises(ContractError, match="contract mismatch"):
        select_renderer(minimal_chart_spec_v5(), data, minimal_layout_v5())


@pytest.mark.parametrize("contract", [None, "v4"])
def test_legacy_and_v4_reject_unapproved_layout(contract):
    from dashboard_v5.contract import ContractError, select_renderer

    chart_spec = deepcopy(minimal_chart_spec_v5())
    data = deepcopy(minimal_dashboard_data_v5())
    if contract is None:
        chart_spec["dashboard_design"].pop("contract_version")
        data["meta"].pop("dashboard_profile_contract")
    else:
        chart_spec["dashboard_design"]["contract_version"] = contract
        data["meta"]["dashboard_profile_contract"] = contract
    with pytest.raises(ContractError, match="cannot include dashboard_layout"):
        select_renderer(chart_spec, data, minimal_layout_v5())


def _validate_layout(layout):
    import dashboard_v5.contract as contract

    validate_layout = getattr(contract, "validate_layout", None)
    assert callable(validate_layout), "dashboard_v5.contract.validate_layout is not implemented"
    return validate_layout(layout)


def test_validate_layout_accepts_minimal_v5_layout():
    assert _validate_layout(minimal_layout_v5()) == []


def test_layout_schema_accepts_aligned_stacked_series_panels():
    layout = minimal_layout_v5()
    layout["components"][2]["render_options"]["series_layout"] = "stacked_panels"

    assert _validate_layout(layout) == []


def test_validate_layout_reports_required_schema_field():
    layout = minimal_layout_v5()
    del layout["revision"]
    assert any("revision" in issue for issue in _validate_layout(layout))


def test_validate_layout_rejects_duplicate_component_id_and_orders():
    layout = minimal_layout_v5()
    duplicate = deepcopy(layout["components"][-1])
    duplicate["placement"]["desktop"]["order"] = 1
    duplicate["placement"]["mobile"]["order"] = 1
    layout["components"].append(duplicate)
    issues = _validate_layout(layout)
    assert any("component id" in issue for issue in issues)
    assert any("desktop order" in issue for issue in issues)
    assert any("mobile order" in issue for issue in issues)


def test_validate_layout_requires_visible_control_and_reset_for_stateful_chart():
    layout = minimal_layout_v5()
    chart = next(item for item in layout["components"] if item["kind"] == "chart")
    chart["interactions"] = ["tooltip", "data_zoom"]

    issues = _validate_layout(layout)

    assert any("visible state/reset" in issue for issue in issues)


def test_validate_layout_rejects_grid_overflow_and_mobile_partial_span():
    layout = minimal_layout_v5()
    chart = layout["components"][2]
    chart["placement"]["desktop"]["column_start"] = 8
    chart["placement"]["desktop"]["span"] = 8
    chart["placement"]["mobile"]["span"] = 6
    issues = _validate_layout(layout)
    assert any("12-column" in issue for issue in issues)
    assert any("mobile span" in issue for issue in issues)


def test_validate_layout_rejects_kind_renderer_mismatch():
    layout = minimal_layout_v5()
    layout["components"][2]["renderer"] = "svg_css"
    assert any("kind/renderer" in issue for issue in _validate_layout(layout))


def test_validate_layout_rejects_multiple_heroes():
    layout = minimal_layout_v5()
    layout["components"][3]["role"] = "hero"
    assert any("hero" in issue for issue in _validate_layout(layout))


def test_validate_layout_rejects_support_wider_than_hero():
    layout = minimal_layout_v5()
    layout["components"][3]["placement"]["desktop"]["span"] = 9
    assert any("support" in issue and "hero" in issue for issue in _validate_layout(layout))


def test_validate_layout_rejects_unknown_component_property():
    layout = minimal_layout_v5()
    layout["components"][0]["raw_html"] = "<div>unsafe</div>"
    assert any("raw_html" in issue for issue in _validate_layout(layout))


@pytest.mark.parametrize(
    ("schema_name", "document_factory"),
    [
        ("chart_spec.schema.json", minimal_chart_spec_v5),
        ("dashboard_data.schema.json", minimal_dashboard_data_v5),
    ],
)
def test_existing_chart_and_data_schemas_accept_additive_v5_contract(
    schema_name, document_factory
):
    kit_root = Path(__file__).resolve().parents[1]
    schema = json.loads((kit_root / "schemas" / schema_name).read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(document_factory()))
    assert errors == []


def test_dashboard_data_schema_accepts_semantic_point_roles_for_category_series():
    kit_root = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (kit_root / "schemas" / "dashboard_data.schema.json").read_text(
            encoding="utf-8"
        )
    )
    data = minimal_dashboard_data_v5()
    data["panels"][0]["charts"][0]["encoding"]["series"][0]["point_roles"] = [
        "neutral",
        "info",
    ]

    errors = list(Draft202012Validator(schema).iter_errors(data))

    assert errors == []


def _validate_cross_contract(chart_spec, layout, data):
    import dashboard_v5.contract as contract

    validate = getattr(contract, "validate_v5_cross_contract", None)
    assert callable(
        validate
    ), "dashboard_v5.contract.validate_v5_cross_contract is not implemented"
    return validate(chart_spec, layout, data)


def test_v5_cross_contract_accepts_minimal_documents():
    assert (
        _validate_cross_contract(
            minimal_chart_spec_v5(),
            minimal_layout_v5(),
            minimal_dashboard_data_v5(),
        )
        == []
    )


def test_v5_cross_contract_accepts_spec_header_reference():
    layout = minimal_layout_v5()
    header = next(item for item in layout["components"] if item["kind"] == "header")
    header["data_refs"] = ["dashboard_data.meta"]

    assert (
        _validate_cross_contract(
            minimal_chart_spec_v5(),
            layout,
            minimal_dashboard_data_v5(),
        )
        == []
    )


def test_v5_cross_contract_rejects_run_profile_and_contract_mismatch():
    chart_spec = minimal_chart_spec_v5()
    layout = minimal_layout_v5()
    data = minimal_dashboard_data_v5()
    layout["run_id"] = "another-run"
    layout["profile_purpose"] = "executive_brief"
    data["meta"]["dashboard_profile_contract"] = "v4"
    issues = _validate_cross_contract(chart_spec, layout, data)
    assert any("run_id" in issue for issue in issues)
    assert any("profile" in issue for issue in issues)
    assert any("v5 contract" in issue for issue in issues)


def test_v5_cross_contract_rejects_missing_chart_reference():
    layout = minimal_layout_v5()
    layout["components"][2]["data_refs"] = ["missing-chart"]
    issues = _validate_cross_contract(
        minimal_chart_spec_v5(), layout, minimal_dashboard_data_v5()
    )
    assert any("missing-chart" in issue and "chart" in issue for issue in issues)


def test_v5_cross_contract_rejects_missing_story_and_source_reference():
    layout = minimal_layout_v5()
    data = minimal_dashboard_data_v5()
    data["panels"][0].pop("story")
    data["sources"][0]["id"] = "other-source"
    issues = _validate_cross_contract(minimal_chart_spec_v5(), layout, data)
    assert any("p1" in issue and "story" in issue for issue in issues)
    assert any("src1" in issue and "source" in issue for issue in issues)


def test_v5_cross_contract_rejects_duplicate_kpi_and_primary_chart_placement():
    layout = minimal_layout_v5()
    duplicate_kpis = deepcopy(layout["components"][1])
    duplicate_kpis["id"] = "duplicate-kpis"
    duplicate_kpis["placement"]["desktop"]["order"] = 6
    duplicate_kpis["placement"]["mobile"]["order"] = 6
    duplicate_chart = deepcopy(layout["components"][2])
    duplicate_chart["id"] = "duplicate-chart"
    duplicate_chart["placement"]["desktop"]["order"] = 7
    duplicate_chart["placement"]["mobile"]["order"] = 7
    layout["components"].extend([duplicate_kpis, duplicate_chart])
    issues = _validate_cross_contract(
        minimal_chart_spec_v5(), layout, minimal_dashboard_data_v5()
    )
    assert any("KPI k1" in issue and "exactly once" in issue for issue in issues)
    assert any("primary chart c1" in issue and "exactly once" in issue for issue in issues)


def test_v5_cross_contract_requires_visible_control_and_reset_for_stateful_chart():
    layout = minimal_layout_v5()
    chart = next(item for item in layout["components"] if item["kind"] == "chart")
    chart["interactions"] = ["tooltip", "data_zoom"]
    issues = _validate_cross_contract(
        minimal_chart_spec_v5(), layout, minimal_dashboard_data_v5()
    )
    assert any("visible state/reset" in issue for issue in issues)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_layout_lock_fixture(tmp_path):
    run = tmp_path / "runs" / "layout-lock"
    checkpoints = run / "outputs" / "checkpoints"
    checkpoints.mkdir(parents=True)
    layout_path = run / "outputs" / "dashboard_layout.json"
    layout_path.write_text(json.dumps(minimal_layout_v5()), encoding="utf-8")
    target = {
        "path": layout_path.as_posix(),
        "sha256": _sha256(layout_path),
        "revision": 1,
        "created_at": "2026-07-14T00:00:00Z",
    }
    question_path = checkpoints / "03_dashboard_storyboard_question.json"
    question_path.write_text(
        json.dumps(
            {
                "created_at": "2026-07-14T00:01:00Z",
                "approval_targets": {"dashboard_layout": target},
            }
        ),
        encoding="utf-8",
    )
    answer = {"question_ref": {"path": question_path.as_posix()}}
    return run, layout_path, answer


def test_checkpoint_schema_accepts_dashboard_layout_approval_target():
    kit_root = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (kit_root / "schemas/checkpoint_question.schema.json").read_text(encoding="utf-8")
    )
    target_schema = {
        **schema["properties"]["approval_targets"],
        "$defs": schema["$defs"],
    }
    target = {
        "dashboard_layout": {
            "path": "runs/r/outputs/dashboard_layout.json",
            "sha256": "a" * 64,
            "revision": 1,
            "created_at": "2026-07-14T00:00:00Z",
        }
    }
    assert list(Draft202012Validator(target_schema).iter_errors(target)) == []


def test_storyboard_question_target_locks_layout_hash_and_revision(tmp_path):
    checkpoint_gate = importlib.import_module("scripts.checkpoint_gate")
    run, layout_path, _answer = _write_layout_lock_fixture(tmp_path)
    targets = checkpoint_gate.approval_targets_for(run, "dashboard_storyboard")
    assert targets["dashboard_layout"]["sha256"] == _sha256(layout_path)
    assert targets["dashboard_layout"]["revision"] == 1


def test_stage_guard_rejects_layout_changed_after_storyboard_approval(tmp_path):
    stage_guard = importlib.import_module("scripts.stage_guard")
    lock_issues = getattr(stage_guard, "dashboard_layout_lock_issues", None)
    assert callable(lock_issues), "stage_guard.dashboard_layout_lock_issues is not implemented"
    run, layout_path, answer = _write_layout_lock_fixture(tmp_path)
    layout = json.loads(layout_path.read_text())
    layout["revision"] = 2
    layout_path.write_text(json.dumps(layout), encoding="utf-8")
    assert any("재승인" in issue for issue in lock_issues(run, answer))


def test_visualize_stage_entry_includes_layout_lock_check(monkeypatch, tmp_path):
    stage_guard = importlib.import_module("scripts.stage_guard")
    run, layout_path, answer = _write_layout_lock_fixture(tmp_path)
    layout = json.loads(layout_path.read_text())
    layout["components"][2]["placement"]["desktop"]["span"] = 12
    layout_path.write_text(json.dumps(layout), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        stage_guard,
        "effective_stage_requirements",
        lambda _run, _stage: ("dashboard_storyboard",),
    )
    monkeypatch.setattr(
        stage_guard,
        "latest_answers",
        lambda _run: {"dashboard_storyboard": answer},
    )
    monkeypatch.setattr(stage_guard, "validate_answer", lambda _run, _cp, _answer: [])
    assert stage_guard.assert_can_run("layout-lock", "visualize") == 3


def test_qa_independently_rejects_layout_hash_mismatch(tmp_path):
    qa_validate = importlib.import_module("qa.validate")
    lock_issues = getattr(qa_validate, "qa_dashboard_layout_lock_issues", None)
    assert callable(lock_issues), "qa_dashboard_layout_lock_issues is not implemented"
    run, layout_path, answer = _write_layout_lock_fixture(tmp_path)
    layout = json.loads(layout_path.read_text())
    layout["components"][2]["placement"]["desktop"]["span"] = 12
    layout_path.write_text(json.dumps(layout), encoding="utf-8")
    assert any("재승인" in issue for issue in lock_issues(run, answer))
