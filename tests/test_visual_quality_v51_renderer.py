"""Renderer behavior for the opt-in visual-quality v5.1 contract."""

from __future__ import annotations

from copy import deepcopy
import json

from dashboard_v5.compiler import build_options_by_component, compile_dashboard
from tests.test_dashboard_v5_compiler import KIT_ROOT
from tests.v5_fixtures import (
    minimal_chart_spec_v51,
    minimal_dashboard_data_v51,
    minimal_layout_v51,
)


def _line_documents(series_count: int = 2) -> tuple[dict, dict, dict]:
    chart_spec = minimal_chart_spec_v51()
    layout = minimal_layout_v51()
    data = minimal_dashboard_data_v51()

    plan = chart_spec["charts"][0]
    plan["chart"]["type"] = "line"
    visual = plan["visual_contract"]
    visual.update(
        {
            "comparison_intent": "movement",
            "family": "trend",
            "variant": "line",
            "scale_policy": "shared_scale",
            "label_strategy": "mixed",
            "legend_strategy": "top",
            "mobile_strategy": "reflow",
        }
    )
    visual["data_sufficiency"].update(
        {
            "observed_points": 3,
            "observed_series": series_count,
            "minimum_points": 3,
            "minimum_series": 1,
        }
    )
    visual["palette_policy"].update(
        {
            "mode": "categorical_identity",
            "max_color_roots": min(series_count, 5),
        }
    )
    visual["non_color_channels"] = ["label", "line_style"]
    visual["copy_context"].update(
        {
            "metric_label": "월별 지수",
            "comparison_period": "2026-05~2026-07",
            "unit_label": "지수",
        }
    )

    component = next(
        item for item in layout["components"] if item["kind"] == "chart"
    )
    component["render_options"].update(
        {"series_layout": "overlay", "legend": "top"}
    )

    chart = data["panels"][0]["charts"][0]
    chart.update(
        {
            "type": "line",
            "title": "전체 항목의 월별 지수",
            "desc": "2026-05~2026-07 (단위: 지수)",
            "encoding": {
                "x": {
                    "type": "time",
                    "label": "월",
                    "values": ["2026-05", "2026-06", "2026-07"],
                },
                "series": [
                    {
                        "label": f"계열 {index + 1}",
                        "unit": "지수",
                        "values": [100 + index, 102 + index, 104 + index],
                    }
                    for index in range(series_count)
                ],
                "stack": "none",
            },
        }
    )
    return chart_spec, layout, data


def _hero_option(chart_spec: dict, layout: dict, data: dict) -> dict:
    return build_options_by_component(layout, data, chart_spec)["hero-chart"]


def test_v51_independent_panels_override_layout_overlay():
    chart_spec, layout, data = _line_documents()
    chart_spec["charts"][0]["visual_contract"][
        "scale_policy"
    ] = "independent_panels"
    data["panels"][0]["charts"][0]["encoding"]["series"][1]["unit"] = "건"
    chart_spec["charts"][0]["visual_contract"]["copy_context"][
        "unit_label"
    ] = "지수, 건"
    data["panels"][0]["charts"][0]["desc"] = (
        "2026-05~2026-07 (단위: 지수, 건)"
    )

    option = _hero_option(chart_spec, layout, data)

    assert len(option["grid"]) == 2
    assert option["series"][0]["yAxisIndex"] == 0
    assert option["series"][1]["yAxisIndex"] == 1
    assert option["legend"]["show"] is False


def test_v51_indexed_baseline_adds_visible_100_reference():
    chart_spec, layout, data = _line_documents(series_count=1)
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["scale_policy"] = "indexed_baseline"
    visual["palette_policy"].update(
        {"mode": "single_measure", "max_color_roots": 1}
    )
    visual["legend_strategy"] = "none"

    option = _hero_option(chart_spec, layout, data)

    reference = option["series"][0]["markLine"]
    assert reference["data"] == [{"name": "기준 100", "yAxis": 100}]
    assert reference["label"]["show"] is True


def test_v51_focused_range_sets_scale_and_visible_axis_cue():
    chart_spec, layout, data = _line_documents(series_count=1)
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["scale_policy"] = "focused_range_with_cue"
    visual["palette_policy"].update(
        {"mode": "single_measure", "max_color_roots": 1}
    )
    visual["legend_strategy"] = "none"

    option = _hero_option(chart_spec, layout, data)

    assert option["yAxis"]["scale"] is True
    assert option["graphic"][0]["style"]["text"] == "축 범위 확대"


def test_v51_zero_baseline_preserves_negative_bar_values():
    chart_spec = minimal_chart_spec_v51()
    layout = minimal_layout_v51()
    data = minimal_dashboard_data_v51()
    chart = data["panels"][0]["charts"][0]
    chart["encoding"]["series"][0]["values"] = [-15.2, 5.7]

    option = _hero_option(chart_spec, layout, data)

    assert option["series"][0]["data"] == [-15.2, 5.7]
    assert option["yAxis"]["scale"] is False
    assert "min" not in option["yAxis"]


def test_v51_direct_bar_labels_group_thousands_without_changing_values():
    chart_spec = minimal_chart_spec_v51()
    layout = minimal_layout_v51()
    data = minimal_dashboard_data_v51()
    chart_spec["charts"][0]["visual_contract"]["label_strategy"] = "direct"
    chart = data["panels"][0]["charts"][0]
    chart["encoding"]["series"][0]["values"] = [10970, 504]
    chart["encoding"]["series"][0]["format"] = {"precision": 0}

    option = _hero_option(chart_spec, layout, data)
    points = option["series"][0]["data"]

    assert [point["value"] for point in points] == [10970, 504]
    assert points[0]["label"]["formatter"] == "10,970"
    assert points[1]["label"]["formatter"] == "504"


def test_v51_histogram_range_labels_group_thousands():
    from dashboard_v5.echarts_options import build_echarts_option
    from tests.test_dashboard_v5_compiler import chart_fixture

    chart = chart_fixture("histogram")
    chart["encoding"]["bins"] = [
        {"range": [50000, 75000], "count": 6},
        {"range": [75000, 100000], "count": 8},
    ]

    option = build_echarts_option(
        chart,
        {},
        [],
        visual_contract={"label_strategy": "axis"},
        identity_colors={},
    )

    assert option["xAxis"]["data"] == ["50,000–75,000", "75,000–100,000"]


def test_v51_tooltip_is_confined_to_chart_viewport():
    chart_spec, layout, data = _line_documents()
    option = _hero_option(chart_spec, layout, data)

    assert option["tooltip"]["confine"] is True


def test_v51_direct_labels_replace_legend_and_add_non_color_styles():
    chart_spec, layout, data = _line_documents()
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["label_strategy"] = "direct"
    visual["legend_strategy"] = "direct_labels"

    option = _hero_option(chart_spec, layout, data)

    assert option["legend"]["show"] is False
    assert all(item["endLabel"]["show"] is True for item in option["series"])
    assert option["series"][0]["lineStyle"]["type"] != option["series"][1][
        "lineStyle"
    ]["type"]


def test_v51_panel_channel_separates_series_even_with_shared_scale():
    chart_spec, layout, data = _line_documents()
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["non_color_channels"] = ["label", "panel"]

    option = _hero_option(chart_spec, layout, data)

    assert len(option["grid"]) == 2


def test_v51_open_fill_channel_uses_hollow_series_symbols():
    chart_spec, layout, data = _line_documents()
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["non_color_channels"] = ["label", "open_fill"]

    option = _hero_option(chart_spec, layout, data)

    for series in option["series"]:
        assert series["itemStyle"]["color"] == "#ffffff"
        assert series["itemStyle"]["borderColor"] == series["lineStyle"]["color"]
        assert series["itemStyle"]["borderWidth"] == 2


def test_v51_paginated_legend_uses_five_stable_colors_for_nine_series():
    chart_spec, layout, data = _line_documents(series_count=9)
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["legend_strategy"] = "paginated"
    visual["mobile_strategy"] = "paginated_legend"
    visual["palette_policy"]["max_color_roots"] = 5

    option = _hero_option(chart_spec, layout, data)

    colors = {item["itemStyle"]["color"] for item in option["series"]}
    assert len(colors) == 5
    assert option["legend"]["show"] is True
    assert option["legend"]["type"] == "scroll"
    assert option["media"][0]["option"]["legend"]["type"] == "scroll"


def test_v51_identity_colors_stay_stable_when_series_order_changes():
    chart_spec, layout, data = _line_documents()
    second_plan = deepcopy(chart_spec["charts"][0])
    second_plan["id"] = "c2"
    second_plan["dashboard_mapping"]["chart_id"] = "c2"
    chart_spec["charts"].append(second_plan)
    second_chart = deepcopy(data["panels"][0]["charts"][0])
    second_chart["id"] = "c2"
    second_chart["encoding"]["series"].reverse()
    data["panels"][0]["charts"].append(second_chart)
    second_component = deepcopy(
        next(item for item in layout["components"] if item["kind"] == "chart")
    )
    second_component["id"] = "second-chart"
    second_component["data_refs"] = ["c2"]
    layout["components"].append(second_component)

    options = build_options_by_component(layout, data, chart_spec)
    first_colors = {
        item["name"]: item["itemStyle"]["color"]
        for item in options["hero-chart"]["series"]
    }
    second_colors = {
        item["name"]: item["itemStyle"]["color"]
        for item in options["second-chart"]["series"]
    }

    assert first_colors == second_colors


def test_v51_top_n_mobile_option_keeps_full_detail_outside_chart():
    chart_spec = minimal_chart_spec_v51()
    layout = minimal_layout_v51()
    data = minimal_dashboard_data_v51()
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["mobile_strategy"] = "top_n_with_detail"
    visual["data_sufficiency"]["observed_points"] = 24
    categories = [f"항목 {index:02d}" for index in range(24)]
    chart = data["panels"][0]["charts"][0]
    chart["encoding"]["x"]["values"] = categories
    chart["encoding"]["series"][0]["values"] = list(range(24))

    option = _hero_option(chart_spec, layout, data)
    narrow = next(item for item in option["media"] if item["query"] == {"maxWidth": 480})

    assert narrow["option"]["xAxis"]["data"] == categories[:8]
    assert narrow["option"]["series"][0]["data"] == list(range(8))
    assert option["xAxis"]["data"] == categories


def test_v51_diverging_heatmap_uses_declared_midpoint():
    from dashboard_v5.echarts_options import build_echarts_option
    from tests.test_dashboard_v5_compiler import chart_fixture

    chart = chart_fixture("heatmap")
    chart["encoding"]["x"]["values"] = ["A", "B"]
    chart["encoding"]["cells"] = [
        {"x": "A", "y": "B", "value": -2},
        {"x": "B", "y": "B", "value": 8},
    ]
    visual = {
        "palette_policy": {"mode": "diverging", "midpoint": 0},
        "non_color_channels": ["label"],
    }

    option = build_echarts_option(
        chart, {}, [], visual_contract=visual, identity_colors={}
    )

    assert option["visualMap"]["type"] == "piecewise"
    assert any(piece.get("lte") == 0 for piece in option["visualMap"]["pieces"])
    assert any(piece.get("gt") == 0 for piece in option["visualMap"]["pieces"])


def test_v51_longest_direct_or_legend_label_reserves_plot_space():
    chart_spec, layout, data = _line_documents()
    visual = chart_spec["charts"][0]["visual_contract"]
    visual["legend_strategy"] = "right"
    data["panels"][0]["charts"][0]["encoding"]["series"][1]["label"] = (
        "아주 긴 비교 계열 이름으로도 잘리지 않아야 함"
    )

    option = _hero_option(chart_spec, layout, data)

    assert option["grid"]["right"] >= 220


def test_v51_compiled_template_exposes_mobile_fallback_and_opt_in_reflow(tmp_path):
    chart_spec = minimal_chart_spec_v51()
    layout = minimal_layout_v51()
    data = minimal_dashboard_data_v51()
    chart_spec["charts"][0]["visual_contract"][
        "mobile_strategy"
    ] = "table_fallback"
    component = next(
        item for item in layout["components"] if item["kind"] == "chart"
    )
    component["empty_behavior"] = "hide"

    chart_path = tmp_path / "chart_spec.json"
    layout_path = tmp_path / "dashboard_layout.json"
    data_path = tmp_path / "dashboard_data.json"
    output_path = tmp_path / "dashboard.html"
    chart_path.write_text(json.dumps(chart_spec), encoding="utf-8")
    layout_path.write_text(json.dumps(layout), encoding="utf-8")
    data_path.write_text(json.dumps(data), encoding="utf-8")

    compile_dashboard(
        chart_path,
        layout_path,
        data_path,
        output_path,
        KIT_ROOT,
    )
    html = output_path.read_text(encoding="utf-8")

    assert "const PRESENTATION_BY_COMPONENT" in html
    assert 'el.dataset.mobileStrategy = presentation.mobile_strategy' in html
    assert 'component.empty_behavior === "hide"' in html
    assert ".chart-fallback-table" in html
    assert "function bindMobileFallback" in html
    assert '[data-fallback-active="true"]' in html
    assert '@media (max-width: 840px)' in html
    assert '@media (max-width: 360px)' in html
    assert '[data-quality-contract="v5.1"]' in html
