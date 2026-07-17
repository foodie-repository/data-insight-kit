"""Additive contracts for visual-quality convergence v5.1."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from dashboard_v5.contract import validate_v5_cross_contract
from tests.v5_fixtures import (
    minimal_chart_spec_v5,
    minimal_chart_spec_v51,
    minimal_dashboard_data_v5,
    minimal_dashboard_data_v51,
    minimal_layout_v5,
    minimal_layout_v51,
)


KIT_ROOT = Path(__file__).resolve().parents[1]


def _schema_errors(schema_name: str, payload: dict) -> list[str]:
    schema = json.loads(
        (KIT_ROOT / "schemas" / schema_name).read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(payload)]


def _plan_quality_issues(chart_spec: dict, layout: dict) -> list[str]:
    import dashboard_v5.contract as contract

    validate = getattr(contract, "validate_v51_plan_quality", None)
    assert callable(validate), "dashboard_v5.contract.validate_v51_plan_quality missing"
    return validate(chart_spec, layout)


def _execution_quality_issues(
    chart_spec: dict, layout: dict, data: dict
) -> list[str]:
    import dashboard_v5.contract as contract

    validate = getattr(contract, "validate_v51_execution_quality", None)
    assert callable(
        validate
    ), "dashboard_v5.contract.validate_v51_execution_quality missing"
    return validate(chart_spec, layout, data)


def test_existing_v5_documents_remain_schema_valid_without_v51_opt_in():
    assert _schema_errors("chart_spec.schema.json", minimal_chart_spec_v5()) == []
    assert _schema_errors("dashboard_layout.schema.json", minimal_layout_v5()) == []


def test_v51_chart_and_layout_documents_are_schema_valid():
    assert _schema_errors("chart_spec.schema.json", minimal_chart_spec_v51()) == []
    assert _schema_errors("dashboard_layout.schema.json", minimal_layout_v51()) == []


def test_v51_chart_spec_requires_decision_brief_and_visual_contract():
    chart_spec = minimal_chart_spec_v51()
    chart_spec["quality_contract"].pop("decision_brief")
    chart_spec["charts"][0].pop("visual_contract")

    errors = _schema_errors("chart_spec.schema.json", chart_spec)

    assert any("'decision_brief' is a required property" in error for error in errors)
    assert any("'visual_contract' is a required property" in error for error in errors)


def test_v51_layout_requires_component_purpose_lineage_and_empty_behavior():
    layout = minimal_layout_v51()
    component = layout["components"][1]
    component.pop("purpose")
    component.pop("decision_link")
    component.pop("evidence_refs")
    component.pop("empty_behavior")

    errors = _schema_errors("dashboard_layout.schema.json", layout)

    for field in ("purpose", "decision_link", "evidence_refs", "empty_behavior"):
        assert any(f"'{field}' is a required property" in error for error in errors)


def test_v51_cross_contract_rejects_one_sided_quality_declaration():
    issues = validate_v5_cross_contract(
        minimal_chart_spec_v51(), minimal_layout_v5(), minimal_dashboard_data_v5()
    )

    assert any("v5.1 quality contract mismatch" in issue for issue in issues)


def test_v51_cross_contract_rejects_visual_variant_chart_type_mismatch():
    chart_spec = minimal_chart_spec_v51()
    chart_spec["charts"][0]["visual_contract"]["variant"] = "line"

    issues = validate_v5_cross_contract(
        chart_spec, minimal_layout_v51(), minimal_dashboard_data_v5()
    )

    assert any("visual variant" in issue and "chart.type" in issue for issue in issues)


def test_v51_plan_quality_accepts_complete_minimal_contract():
    assert _plan_quality_issues(
        minimal_chart_spec_v51(), minimal_layout_v51()
    ) == []


def test_v51_plan_quality_rejects_audience_and_metric_decision_mismatch():
    chart_spec = minimal_chart_spec_v51()
    chart_spec["quality_contract"]["decision_brief"]["primary_audience"] = "mixed"
    chart_spec["quality_contract"]["metrics"][0]["decision_link"] = "other-decision"

    issues = _plan_quality_issues(chart_spec, minimal_layout_v51())

    assert any("primary_audience" in issue and "meta.audience" in issue for issue in issues)
    assert any("metric count decision_link" in issue for issue in issues)


def test_v51_cross_contract_includes_plan_quality_issues():
    chart_spec = minimal_chart_spec_v51()
    chart_spec["quality_contract"]["decision_brief"]["primary_audience"] = "mixed"

    issues = validate_v5_cross_contract(
        chart_spec, minimal_layout_v51(), minimal_dashboard_data_v5()
    )

    assert any("primary_audience" in issue and "meta.audience" in issue for issue in issues)


def test_v51_plan_quality_rejects_duplicate_questions_and_missing_metric_lineage():
    chart_spec = minimal_chart_spec_v51()
    duplicate = deepcopy(chart_spec["charts"][0])
    duplicate["id"] = "c2"
    duplicate["dashboard_mapping"]["chart_id"] = "c2"
    chart_spec["charts"].append(duplicate)
    chart_spec["charts"][0]["data_requirements"]["measures"] = ["unknown_metric"]

    issues = _plan_quality_issues(chart_spec, minimal_layout_v51())

    assert any("duplicate chart question" in issue for issue in issues)
    assert any("does not reference a declared metric" in issue for issue in issues)


def test_v51_plan_quality_rejects_insufficient_trend_and_unapplied_fallback():
    chart_spec = minimal_chart_spec_v51()
    plan = chart_spec["charts"][0]
    plan["chart"]["type"] = "line"
    visual = plan["visual_contract"]
    visual["family"] = "trend"
    visual["variant"] = "line"
    visual["data_sufficiency"].update(
        {
            "status": "sufficient",
            "observed_points": 2,
            "minimum_points": 2,
            "fallback_chart": "bar",
        }
    )

    issues = _plan_quality_issues(chart_spec, minimal_layout_v51())
    assert any("line requires at least 3 observed points" in issue for issue in issues)

    visual["data_sufficiency"]["status"] = "fallback_required"
    issues = _plan_quality_issues(chart_spec, minimal_layout_v51())
    assert any("fallback chart 'bar' is not applied" in issue for issue in issues)


def test_v51_plan_quality_rejects_scatter_with_too_few_distinct_axis_values():
    chart_spec = minimal_chart_spec_v51()
    plan = chart_spec["charts"][0]
    plan["chart"]["type"] = "scatter"
    visual = plan["visual_contract"]
    visual["family"] = "relationship"
    visual["variant"] = "scatter"
    visual["data_sufficiency"].update(
        {
            "observed_points": 20,
            "minimum_points": 20,
            "observed_distinct_x": 2,
            "observed_distinct_y": 3,
        }
    )

    issues = _plan_quality_issues(chart_spec, minimal_layout_v51())

    assert any("scatter requires at least 3 distinct values per axis" in issue for issue in issues)


def test_v51_plan_quality_rejects_sparse_heatmap_cells():
    chart_spec = minimal_chart_spec_v51()
    plan = chart_spec["charts"][0]
    plan["chart"]["type"] = "heatmap"
    visual = plan["visual_contract"]
    visual["family"] = "matrix"
    visual["variant"] = "heatmap"
    visual["data_sufficiency"].update(
        {
            "observed_points": 4,
            "minimum_points": 4,
            "observed_x_categories": 2,
            "observed_y_categories": 2,
            "cell_density": 0.25,
        }
    )

    issues = _plan_quality_issues(chart_spec, minimal_layout_v51())

    assert any("heatmap requires at least 50% cell density" in issue for issue in issues)


def test_v51_plan_quality_rejects_family_variant_mismatch():
    chart_spec = minimal_chart_spec_v51()
    chart_spec["charts"][0]["visual_contract"]["family"] = "trend"

    issues = _plan_quality_issues(chart_spec, minimal_layout_v51())

    assert any("family 'trend' does not allow variant 'bar'" in issue for issue in issues)


def test_v51_plan_quality_rejects_default_legend_for_more_than_eight_series():
    chart_spec = minimal_chart_spec_v51()
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["data_sufficiency"]["observed_series"] = 9
    visual["palette_policy"]["mode"] = "categorical_identity"
    visual["palette_policy"]["max_color_roots"] = 5
    visual["legend_strategy"] = "top"

    issues = _plan_quality_issues(chart_spec, minimal_layout_v51())

    assert any("more than 8 identity series" in issue for issue in issues)


def test_v51_plan_quality_rejects_component_decision_and_evidence_mismatch():
    layout = minimal_layout_v51()
    layout["components"][1]["decision_link"] = "other-decision"
    layout["components"][1]["evidence_refs"] = ["unknown_metric"]

    issues = _plan_quality_issues(minimal_chart_spec_v51(), layout)

    assert any("component kpis decision_link" in issue for issue in issues)
    assert any("component kpis evidence_refs" in issue for issue in issues)


def test_storyboard_summary_exposes_v51_decision_and_visual_plan(tmp_path):
    from scripts.checkpoint_gate import chart_spec_summary, dashboard_layout_summary

    chart_path = tmp_path / "chart_spec.json"
    layout_path = tmp_path / "dashboard_layout.json"
    chart_path.write_text(
        json.dumps(minimal_chart_spec_v51(), ensure_ascii=False), encoding="utf-8"
    )
    layout_path.write_text(
        json.dumps(minimal_layout_v51(), ensure_ascii=False), encoding="utf-8"
    )

    chart_summary = chart_spec_summary(chart_path)
    layout_summary = dashboard_layout_summary(layout_path)

    assert "판단 목적: 항목별 차이를 검토한다" in chart_summary
    assert "표현 계획: 비교 / 순위 / 막대 차트" in chart_summary
    assert "목적" in layout_summary
    assert "판단 연결" in layout_summary


def test_analyze_agent_requires_v51_planning_contract_fields():
    instructions = (KIT_ROOT / "agents" / "analyze.md").read_text(encoding="utf-8")

    for required_text in (
        'quality_contract.version="v5.1"',
        "observed_points",
        "observed_distinct_x",
        "cell_density",
        "fallback_required",
        "copy_context",
        "scale_policy",
        "palette_policy.midpoint",
        "non_color_channels",
        'quality_contract_version="v5.1"',
        "evidence_refs",
        "천 단위 구분기호",
    ):
        assert required_text in instructions


def test_visualize_agent_requires_v51_execution_contract():
    instructions = (KIT_ROOT / "agents" / "visualize.md").read_text(encoding="utf-8")

    for required_text in (
        "visual_contract.copy_context",
        "(단위: 실제 단위)",
        "title_mode=\"conclusion\"",
        "empty_behavior=\"hide\"",
        "empty_behavior=\"block\"",
        "0 기준선",
        "색만으로",
        "천 단위 구분기호",
    ):
        assert required_text in instructions


def test_v51_execution_quality_accepts_complete_minimal_documents():
    assert _execution_quality_issues(
        minimal_chart_spec_v51(), minimal_layout_v51(), minimal_dashboard_data_v51()
    ) == []


def test_v51_execution_quality_rejects_missing_visible_copy_context():
    data = minimal_dashboard_data_v51()
    chart = data["panels"][0]["charts"][0]
    chart["title"] = "항목 비교"
    chart["desc"] = "건수 요약"

    issues = _execution_quality_issues(
        minimal_chart_spec_v51(), minimal_layout_v51(), data
    )

    assert any("visible copy misses scope_label" in issue for issue in issues)
    assert any("visible copy misses comparison_period" in issue for issue in issues)
    assert any("visible copy misses unit_label" in issue for issue in issues)


def test_v51_conclusion_title_requires_grounded_numeric_evidence():
    chart_spec = minimal_chart_spec_v51()
    chart_spec["charts"][0]["visual_contract"]["copy_context"][
        "title_mode"
    ] = "conclusion"
    data = minimal_dashboard_data_v51()
    data["panels"][0]["charts"][0]["title"] = "전체 항목에서 B가 가장 많다"

    issues = _execution_quality_issues(chart_spec, minimal_layout_v51(), data)

    assert any("conclusion copy lacks grounded numeric evidence" in issue for issue in issues)


def test_v51_conclusion_title_accepts_numeric_evidence_from_plan():
    chart_spec = minimal_chart_spec_v51()
    chart_spec["charts"][0]["visual_contract"]["copy_context"][
        "title_mode"
    ] = "conclusion"
    data = minimal_dashboard_data_v51()
    chart = data["panels"][0]["charts"][0]
    chart["title"] = "전체 항목에서 B가 20건으로 가장 많다"
    chart["desc"] = "2026-07-14 기준 건수 (단위: 건)"

    assert _execution_quality_issues(
        chart_spec, minimal_layout_v51(), data
    ) == []


def test_v51_execution_quality_rejects_ungrouped_large_reader_quantities():
    data = minimal_dashboard_data_v51()
    data["panels"][0]["story"]["now"]["value"] = (
        "2026년 6월 거래량은 10970건입니다."
    )

    issues = _execution_quality_issues(
        minimal_chart_spec_v51(), minimal_layout_v51(), data
    )

    assert any("ungrouped quantity '10970건'" in issue for issue in issues)


def test_v51_execution_quality_accepts_grouped_quantities_and_ignores_dates():
    data = minimal_dashboard_data_v51()
    data["meta"]["title"] = "2026년 6월 현황"
    data["panels"][0]["story"]["now"]["value"] = (
        "2026년 6월 거래량은 10,970건입니다."
    )

    issues = _execution_quality_issues(
        minimal_chart_spec_v51(), minimal_layout_v51(), data
    )

    assert not any("ungrouped quantity" in issue for issue in issues)


def test_v51_execution_quality_rejects_observed_count_mismatch():
    chart_spec = minimal_chart_spec_v51()
    chart_spec["charts"][0]["visual_contract"]["data_sufficiency"][
        "observed_points"
    ] = 3

    issues = _execution_quality_issues(
        chart_spec, minimal_layout_v51(), minimal_dashboard_data_v51()
    )

    assert any("declares 3 observed points but data has 2" in issue for issue in issues)


def test_v51_execution_quality_rejects_nonzero_bar_baseline():
    data = minimal_dashboard_data_v51()
    data["panels"][0]["charts"][0]["encoding"]["zero_baseline"] = False

    issues = _execution_quality_issues(
        minimal_chart_spec_v51(), minimal_layout_v51(), data
    )

    assert any("bar must use a zero baseline" in issue for issue in issues)


def test_v51_cross_contract_includes_execution_quality_issues():
    data = minimal_dashboard_data_v51()
    data["panels"][0]["charts"][0]["encoding"]["zero_baseline"] = False

    issues = validate_v5_cross_contract(
        minimal_chart_spec_v51(), minimal_layout_v51(), data
    )

    assert any("bar must use a zero baseline" in issue for issue in issues)


def test_v51_execution_quality_rejects_diverging_palette_without_midpoint():
    chart_spec = minimal_chart_spec_v51()
    chart_spec["charts"][0]["visual_contract"]["palette_policy"][
        "mode"
    ] = "diverging"

    issues = _execution_quality_issues(
        chart_spec, minimal_layout_v51(), minimal_dashboard_data_v51()
    )

    assert any("diverging palette requires a meaningful midpoint" in issue for issue in issues)


def test_v51_execution_quality_rejects_diverging_midpoint_outside_observed_values():
    chart_spec = minimal_chart_spec_v51()
    palette = chart_spec["charts"][0]["visual_contract"]["palette_policy"]
    palette.update({"mode": "diverging", "midpoint": 999})

    issues = _execution_quality_issues(
        chart_spec, minimal_layout_v51(), minimal_dashboard_data_v51()
    )

    assert any("diverging midpoint 999 is outside observed range" in issue for issue in issues)


def test_v51_execution_quality_rejects_different_unit_overlay():
    chart_spec = minimal_chart_spec_v51()
    plan = chart_spec["charts"][0]
    plan["chart"]["type"] = "line"
    visual = plan["visual_contract"]
    visual["comparison_intent"] = "movement"
    visual["family"] = "trend"
    visual["variant"] = "line"
    visual["scale_policy"] = "shared_scale"
    visual["data_sufficiency"].update(
        {"observed_points": 3, "minimum_points": 3, "observed_series": 2}
    )
    visual["palette_policy"].update(
        {"mode": "categorical_identity", "max_color_roots": 2}
    )
    visual["non_color_channels"] = ["label", "line_style"]
    visual["copy_context"].update(
        {
            "metric_label": "가격과 거래량",
            "comparison_period": "2026-05~2026-07",
            "unit_label": "만원, 건",
        }
    )

    layout = minimal_layout_v51()
    layout["components"][2]["render_options"]["series_layout"] = "overlay"
    data = minimal_dashboard_data_v51()
    chart = data["panels"][0]["charts"][0]
    chart["type"] = "line"
    chart["title"] = "전체 항목의 가격과 거래량"
    chart["desc"] = "2026-05~2026-07 (단위: 만원, 건)"
    chart["encoding"] = {
        "x": {
            "type": "time",
            "label": "월",
            "values": ["2026-05", "2026-06", "2026-07"],
        },
        "series": [
            {"label": "가격", "unit": "만원", "values": [10, 11, 12]},
            {"label": "거래량", "unit": "건", "values": [30, 20, 15]},
        ],
        "stack": "none",
    }

    issues = _execution_quality_issues(chart_spec, layout, data)

    assert any("different units cannot use overlay" in issue for issue in issues)


def test_v51_execution_quality_rejects_color_only_multi_series():
    chart_spec = minimal_chart_spec_v51()
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["data_sufficiency"]["observed_series"] = 2
    visual["palette_policy"]["mode"] = "categorical_identity"
    visual["non_color_channels"] = []

    issues = _execution_quality_issues(
        chart_spec, minimal_layout_v51(), minimal_dashboard_data_v51()
    )

    assert any("multi-series chart cannot rely on color alone" in issue for issue in issues)


def test_v51_execution_quality_rejects_more_than_five_color_roots():
    chart_spec = minimal_chart_spec_v51()
    chart_spec["charts"][0]["visual_contract"]["palette_policy"][
        "max_color_roots"
    ] = 6

    issues = _execution_quality_issues(
        chart_spec, minimal_layout_v51(), minimal_dashboard_data_v51()
    )

    assert any("palette exceeds 5 color roots" in issue for issue in issues)


def test_v51_execution_quality_rejects_empty_kpi_and_noop_control():
    data = minimal_dashboard_data_v51()
    data["kpis"][0]["value"] = ""
    layout = minimal_layout_v51()
    control = deepcopy(layout["components"][2])
    control.update(
        {
            "id": "noop-control",
            "kind": "control_bar",
            "role": "navigation",
            "renderer": "svg_css",
            "purpose": "interaction",
            "interactions": [],
        }
    )
    control["placement"]["desktop"]["order"] = 6
    control["placement"]["mobile"]["order"] = 6
    layout["components"].append(control)

    issues = _execution_quality_issues(minimal_chart_spec_v51(), layout, data)

    assert any("KPI k1 is empty" in issue for issue in issues)
    assert any("control noop-control has no state-changing interaction" in issue for issue in issues)


def test_v51_execution_quality_rejects_empty_chart_and_insight_when_blocking():
    data = minimal_dashboard_data_v51()
    chart = data["panels"][0]["charts"][0]
    chart["encoding"]["x"]["values"] = []
    chart["encoding"]["series"][0]["values"] = []
    data["panels"][0]["story"] = {}

    issues = _execution_quality_issues(
        minimal_chart_spec_v51(), minimal_layout_v51(), data
    )

    assert any("chart c1 is empty" in issue for issue in issues)
    assert any("insight component insight has no reader-facing content" in issue for issue in issues)


def test_v51_execution_quality_allows_empty_component_marked_hide():
    data = minimal_dashboard_data_v51()
    chart = data["panels"][0]["charts"][0]
    chart["encoding"]["x"]["values"] = []
    chart["encoding"]["series"][0]["values"] = []
    layout = minimal_layout_v51()
    layout["components"][2]["empty_behavior"] = "hide"

    issues = _execution_quality_issues(minimal_chart_spec_v51(), layout, data)

    assert not any("chart c1 is empty" in issue for issue in issues)


def test_v51_execution_quality_rejects_duplicate_component_purpose_and_evidence():
    layout = minimal_layout_v51()
    duplicate = deepcopy(layout["components"][3])
    duplicate["id"] = "duplicate-insight"
    duplicate["placement"]["desktop"]["order"] = 6
    duplicate["placement"]["mobile"]["order"] = 6
    layout["components"].append(duplicate)

    issues = _execution_quality_issues(
        minimal_chart_spec_v51(), layout, minimal_dashboard_data_v51()
    )

    assert any("duplicate component purpose/evidence" in issue for issue in issues)
