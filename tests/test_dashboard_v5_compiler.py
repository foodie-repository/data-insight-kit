"""Dashboard freeform v5 compiler and ECharts option tests."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import NamedTuple

import pytest

from tests.v5_fixtures import (
    minimal_chart_spec_v5,
    minimal_dashboard_data_v5,
    minimal_layout_v5,
)


KIT_ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chart_fixture(chart_type: str) -> dict:
    category = {
        "x": {"type": "category", "label": "항목", "values": ["A", "B"]},
        "series": [{"label": "값", "unit": "건", "values": [10, 20]}],
        "stack": "none",
    }
    encodings = {
        "line": category,
        "area": category,
        "bar": category,
        "stacked_bar": {**category, "stack": "stacked"},
        "histogram": {
            "x": {"label": "값", "unit": "건"},
            "bin_inclusion": "[lo,hi)",
            "bins": [
                {"range": [0, 10], "count": 3},
                {"range": [10, 20], "count": 5},
            ],
        },
        "scatter": {
            "x": {"label": "x", "unit": "점"},
            "y": {"label": "y", "unit": "점"},
            "points": [{"x": 1, "y": 2}, {"x": 2, "y": 3}],
        },
        "heatmap": {
            "x": {"label": "x", "values": ["A"]},
            "y": {"label": "y", "values": ["B"]},
            "value": {"label": "값", "unit": "건"},
            "cells": [{"x": "A", "y": "B", "value": 4}],
        },
        "boxplot": {
            "x": {"label": "그룹"},
            "y": {"label": "값", "unit": "점"},
            "boxes": [
                {"label": "A", "min": 1, "q1": 2, "median": 3, "q3": 4, "max": 5}
            ],
        },
        "waterfall": {
            "x": {"label": "단계"},
            "y": {"label": "값", "unit": "건"},
            "steps": [
                {"label": "시작", "value": 10, "kind": "start"},
                {"label": "증가", "value": 3, "kind": "increase"},
                {"label": "합계", "value": 13, "kind": "total"},
            ],
        },
        "slope": {
            "x": {"label": "시점", "start_label": "전", "end_label": "후"},
            "y": {"label": "값", "unit": "건"},
            "series": [{"label": "A", "start": 10, "end": 15}],
        },
    }
    return {
        "id": f"{chart_type}-chart",
        "type": chart_type,
        "title": chart_type,
        "desc": None,
        "encoding": deepcopy(encodings[chart_type]),
    }


@pytest.mark.parametrize(
    ("chart_type", "series_type"),
    [
        ("line", "line"),
        ("area", "line"),
        ("bar", "bar"),
        ("stacked_bar", "bar"),
        ("histogram", "bar"),
        ("scatter", "scatter"),
        ("heatmap", "heatmap"),
        ("boxplot", "boxplot"),
        ("waterfall", "bar"),
        ("slope", "line"),
    ],
)
def test_all_chart_types_map_to_pinned_echarts_series(chart_type, series_type):
    from dashboard_v5.echarts_options import build_echarts_option

    option = build_echarts_option(chart_fixture(chart_type), {}, ["tooltip"])
    assert option["series"][0]["type"] == series_type
    assert option["aria"]["enabled"] is True


def test_mapper_rejects_unknown_option_and_interaction():
    from dashboard_v5.echarts_options import OptionError, build_echarts_option

    with pytest.raises(OptionError, match="render option"):
        build_echarts_option(chart_fixture("bar"), {"raw_js": "alert(1)"}, [])
    with pytest.raises(OptionError, match="interaction"):
        build_echarts_option(chart_fixture("bar"), {}, ["cross_filter"])


def test_vendor_manifest_matches_local_bundle():
    manifest = json.loads((KIT_ROOT / "templates/vendor/manifest.json").read_text())
    assert manifest["version"] == "6.1.0"
    assert manifest["sha256"] == sha256_file(
        KIT_ROOT / "templates/vendor/echarts.min.js"
    )
    assert (
        manifest["sha256"]
        == "b66b25aeb4df84e33199dc21694014d336d222cbd9deb0e5a7c14bd6aa0d0fd0"
    )


def test_data_zoom_is_opt_in_and_category_values_are_not_recomputed():
    from dashboard_v5.echarts_options import build_echarts_option

    chart = chart_fixture("bar")
    plain = build_echarts_option(chart, {}, [])
    zoomed = build_echarts_option(chart, {}, ["data_zoom"])
    assert "dataZoom" not in plain
    assert [item["type"] for item in zoomed["dataZoom"]] == ["inside", "slider"]
    assert zoomed["xAxis"]["data"] == ["A", "B"]
    assert zoomed["series"][0]["data"] == [10, 20]


def test_legend_toggle_is_opt_in():
    from dashboard_v5.echarts_options import build_echarts_option

    plain = build_echarts_option(chart_fixture("bar"), {}, [])
    interactive = build_echarts_option(chart_fixture("bar"), {}, ["legend_toggle"])
    assert plain["legend"]["selectedMode"] is False
    assert interactive["legend"]["selectedMode"] is True


def test_single_series_hides_redundant_legend_even_when_layout_requests_right():
    from dashboard_v5.echarts_options import build_echarts_option

    option = build_echarts_option(
        chart_fixture("bar"), {"legend": "right"}, []
    )

    assert option["legend"]["show"] is False


def test_multi_series_line_can_use_aligned_stacked_panels_with_direct_labels():
    from dashboard_v5.echarts_options import build_echarts_option

    chart = chart_fixture("line")
    chart["encoding"]["x"] = {
        "type": "time",
        "label": "월",
        "values": ["2022-01", "2022-02", "2022-03"],
    }
    chart["encoding"]["series"] = [
        {
            "label": "가격 지수",
            "unit": "2022-01=100",
            "values": [100.0, 101.2, 108.7],
            "role": "info",
        },
        {
            "label": "거래량 지수",
            "unit": "2022-01=100",
            "values": [100.0, 820.0, 56.8],
            "role": "neutral",
        },
    ]

    option = build_echarts_option(
        chart,
        {"series_layout": "stacked_panels", "legend": "none"},
        ["tooltip"],
    )

    assert len(option["grid"]) == 2
    assert len(option["xAxis"]) == 2
    assert len(option["yAxis"]) == 2
    assert option["xAxis"][0]["axisLabel"]["show"] is False
    assert option["xAxis"][1]["name"] == "월"
    assert option["yAxis"][0]["name"] == "가격 지수"
    assert option["yAxis"][1]["name"] == "거래량 지수"
    assert option["yAxis"][0]["nameTextStyle"]["color"] == option["series"][0]["itemStyle"]["color"]
    assert option["yAxis"][1]["nameTextStyle"]["color"] == option["series"][1]["itemStyle"]["color"]
    assert option["series"][0]["xAxisIndex"] == 0
    assert option["series"][0]["yAxisIndex"] == 0
    assert option["series"][1]["xAxisIndex"] == 1
    assert option["series"][1]["yAxisIndex"] == 1
    assert option["series"][0]["lineStyle"]["type"] != option["series"][1]["lineStyle"]["type"]
    assert option["legend"]["show"] is False


@pytest.mark.parametrize(
    ("position", "grid_key", "minimum"),
    [
        ("right", "right", 150),
        ("top", "top", 72),
        ("bottom", "bottom", 72),
    ],
)
def test_multi_series_legend_reserves_plot_space(position, grid_key, minimum):
    from dashboard_v5.echarts_options import build_echarts_option

    chart = chart_fixture("bar")
    second = deepcopy(chart["encoding"]["series"][0])
    second["label"] = "비교값"
    chart["encoding"]["series"].append(second)

    option = build_echarts_option(chart, {"legend": position}, [])

    assert option["legend"]["show"] is True
    assert option["grid"][grid_key] >= minimum


def test_right_legend_uses_scroll_and_moves_below_plot_on_narrow_canvas():
    from dashboard_v5.echarts_options import build_echarts_option

    chart = chart_fixture("slope")
    for index in range(2, 12):
        chart["encoding"]["series"].append(
            {"label": f"지역 {index}", "start": index, "end": index + 1}
        )

    option = build_echarts_option(chart, {"legend": "right"}, [])

    assert option["legend"]["type"] == "scroll"
    assert option["legend"]["right"] == 8
    assert option["legend"]["top"] == 24
    assert option["legend"]["bottom"] == 24
    narrow = option["media"][0]
    assert narrow["query"] == {"maxWidth": 480}
    assert narrow["option"]["legend"]["orient"] == "horizontal"
    assert narrow["option"]["legend"]["left"] == 24
    assert narrow["option"]["legend"]["right"] == 24
    assert narrow["option"]["legend"]["bottom"] == 8
    assert narrow["option"]["grid"]["right"] == 24
    assert narrow["option"]["grid"]["bottom"] >= 88


def test_single_series_bar_uses_neutral_context_and_one_semantic_highlight():
    from dashboard_v5.echarts_options import build_echarts_option

    chart = chart_fixture("bar")
    chart["encoding"]["series"][0]["point_roles"] = ["neutral", "info"]

    option = build_echarts_option(chart, {}, [])

    assert option["series"][0]["data"] == [
        {"value": 10, "itemStyle": {"color": "#cbd5e1"}},
        {"value": 20, "itemStyle": {"color": "#3157d5"}},
    ]
    assert option["aria"]["decal"]["show"] is False


def test_single_series_bar_defaults_to_neutral_without_point_roles():
    from dashboard_v5.echarts_options import build_echarts_option

    option = build_echarts_option(chart_fixture("bar"), {}, [])

    assert option["series"][0]["itemStyle"]["color"] == "#cbd5e1"
    assert option["series"][0]["data"] == [10, 20]


def test_category_series_rejects_point_role_length_mismatch():
    from dashboard_v5.echarts_options import OptionError, build_echarts_option

    chart = chart_fixture("bar")
    chart["encoding"]["series"][0]["point_roles"] = ["info"]

    with pytest.raises(OptionError, match="point_roles length"):
        build_echarts_option(chart, {}, [])


def test_specialized_chart_encodings_are_translated_without_aggregation():
    from dashboard_v5.echarts_options import build_echarts_option

    histogram = build_echarts_option(chart_fixture("histogram"), {}, [])
    scatter = build_echarts_option(chart_fixture("scatter"), {}, [])
    heatmap = build_echarts_option(chart_fixture("heatmap"), {}, [])
    boxplot = build_echarts_option(chart_fixture("boxplot"), {}, [])
    slope = build_echarts_option(chart_fixture("slope"), {}, [])

    assert histogram["xAxis"]["data"] == ["0–10", "10–20"]
    assert histogram["series"][0]["data"] == [3, 5]
    assert scatter["series"][0]["data"] == [[1, 2], [2, 3]]
    assert heatmap["series"][0]["data"] == [[0, 0, 4]]
    assert heatmap["visualMap"]["min"] == 0
    assert heatmap["visualMap"]["max"] == 4
    assert heatmap["aria"]["decal"]["show"] is False
    assert boxplot["series"][0]["data"] == [[1, 2, 3, 4, 5]]
    assert slope["xAxis"]["data"] == ["전", "후"]
    assert slope["series"][0]["data"] == [10, 15]


def test_scatter_and_slope_preserve_semantic_color_roles():
    from dashboard_v5.echarts_options import build_echarts_option

    scatter_chart = chart_fixture("scatter")
    scatter_chart["encoding"]["points"][0]["role"] = "info"
    scatter_chart["encoding"]["points"][1]["role"] = "neutral"
    slope_chart = chart_fixture("slope")
    slope_chart["encoding"]["series"][0]["role"] = "warn"

    scatter = build_echarts_option(scatter_chart, {}, [])
    slope = build_echarts_option(slope_chart, {}, [])

    assert scatter["series"][0]["data"][0]["value"] == [1, 2]
    assert scatter["series"][0]["data"][0]["itemStyle"]["color"] == "#3157d5"
    assert scatter["series"][0]["data"][1]["itemStyle"]["color"] == "#cbd5e1"
    assert slope["series"][0]["itemStyle"]["color"] == "#a15c00"
    assert slope["series"][0]["lineStyle"]["color"] == "#a15c00"


def test_heatmap_visual_map_uses_observed_value_range():
    from dashboard_v5.echarts_options import build_echarts_option

    chart = chart_fixture("heatmap")
    chart["encoding"]["x"]["values"] = ["A", "B"]
    chart["encoding"]["cells"] = [
        {"x": "A", "y": "B", "value": 0.75},
        {"x": "B", "y": "B", "value": 3.83},
    ]

    option = build_echarts_option(chart, {}, [])

    assert option["visualMap"]["min"] == 0.75
    assert option["visualMap"]["max"] == 3.83


def test_heatmap_uses_high_contrast_sequential_scale_with_end_labels():
    from dashboard_v5.echarts_options import build_echarts_option

    option = build_echarts_option(chart_fixture("heatmap"), {}, [])

    assert option["visualMap"]["inRange"]["color"] == [
        "#eff6ff",
        "#bfdbfe",
        "#60a5fa",
        "#2563eb",
        "#1e3a8a",
    ]
    assert option["visualMap"]["text"] == ["높음", "낮음"]


def test_heatmap_shows_axis_names_and_all_labels_in_compact_mode():
    from dashboard_v5.echarts_options import build_echarts_option

    option = build_echarts_option(
        chart_fixture("heatmap"), {"label_density": "compact"}, []
    )

    assert option["xAxis"]["name"] == "x"
    assert option["xAxis"]["nameLocation"] == "middle"
    assert option["xAxis"]["axisLabel"]["interval"] == 0
    assert option["xAxis"]["axisLabel"]["rotate"] == 35
    assert option["yAxis"]["name"] == "y"
    assert option["yAxis"]["nameLocation"] == "middle"
    assert option["yAxis"]["nameRotate"] == 90
    assert option["yAxis"]["axisLabel"]["interval"] == 0
    assert option["grid"]["left"] == 84
    assert option["grid"]["bottom"] == 96


def test_vertical_category_axis_centers_its_name_instead_of_clipping_at_edge():
    from dashboard_v5.echarts_options import build_echarts_option

    option = build_echarts_option(chart_fixture("bar"), {}, [])

    assert option["xAxis"]["nameLocation"] == "middle"
    assert option["xAxis"]["nameGap"] == 32


def test_value_axes_limit_ticks_hide_overlap_and_center_axis_names():
    from dashboard_v5.echarts_options import build_echarts_option

    horizontal_bar = build_echarts_option(
        chart_fixture("bar"), {"orientation": "horizontal"}, []
    )
    scatter = build_echarts_option(chart_fixture("scatter"), {}, [])

    assert horizontal_bar["xAxis"]["splitNumber"] == 3
    assert horizontal_bar["xAxis"]["axisLabel"]["hideOverlap"] is True
    assert scatter["xAxis"]["nameLocation"] == "middle"
    assert scatter["xAxis"]["nameGap"] == 32
    assert scatter["xAxis"]["splitNumber"] == 3
    assert scatter["xAxis"]["axisLabel"]["hideOverlap"] is True
    assert scatter["yAxis"]["nameLocation"] == "middle"
    assert scatter["yAxis"]["nameRotate"] == 90


def test_waterfall_uses_transparent_bridge_and_visible_values():
    from dashboard_v5.echarts_options import build_echarts_option

    option = build_echarts_option(chart_fixture("waterfall"), {}, [])
    bridge, visible = option["series"]
    assert bridge["itemStyle"]["color"] == "transparent"
    assert bridge["data"] == [0, 10, 0]
    assert visible["data"] == [10, 3, 13]


def test_mapper_rejects_unknown_chart_type_and_option_value():
    from dashboard_v5.echarts_options import OptionError, build_echarts_option

    chart = chart_fixture("bar")
    chart["type"] = "pie"
    with pytest.raises(OptionError, match="chart type"):
        build_echarts_option(chart, {}, [])
    with pytest.raises(OptionError, match="option value"):
        build_echarts_option(chart_fixture("bar"), {"legend": "floating"}, [])


class FixturePaths(NamedTuple):
    chart_spec: Path
    layout: Path
    data: Path


def write_v5_fixture(root: Path, data: dict | None = None) -> FixturePaths:
    root.mkdir(parents=True, exist_ok=True)
    paths = FixturePaths(
        root / "chart_spec.json",
        root / "dashboard_layout.json",
        root / "dashboard_data.json",
    )
    paths.chart_spec.write_text(json.dumps(minimal_chart_spec_v5()), encoding="utf-8")
    paths.layout.write_text(json.dumps(minimal_layout_v5()), encoding="utf-8")
    paths.data.write_text(
        json.dumps(data or minimal_dashboard_data_v5()), encoding="utf-8"
    )
    return paths


def compile_fixture(root: Path, data: dict | None = None) -> str:
    from dashboard_v5.compiler import compile_dashboard

    paths = write_v5_fixture(root, data=data)
    output = root / "dashboard.html"
    compile_dashboard(*paths, output_path=output, kit_root=KIT_ROOT)
    return output.read_text(encoding="utf-8")


def extract_embedded_constant(html: str, name: str) -> dict:
    match = re.search(rf"const {name} = (.+);\n", html)
    assert match is not None
    return json.loads(match.group(1))


def test_compile_writes_self_contained_html_and_hash_manifest(tmp_path):
    from dashboard_v5.compiler import compile_dashboard

    paths = write_v5_fixture(tmp_path)
    output = tmp_path / "dashboard.html"
    manifest = compile_dashboard(*paths, output_path=output, kit_root=KIT_ROOT)
    html = output.read_text(encoding="utf-8")
    assert "{PLACE_" not in html
    assert "echarts.init" in html
    assert not re.search(
        r'<(?:script|link)[^>]+(?:src|href)=["\']https?://', html, re.IGNORECASE
    )
    assert manifest["layout_revision"] == 1
    assert manifest["inputs"]["dashboard_layout"]["sha256"] == sha256_file(
        paths.layout
    )
    assert json.loads((tmp_path / "dashboard_build_manifest.json").read_text()) == manifest
    assert "el.dataset.componentId = component.id" in html
    assert 'echarts.init(node, null, {renderer: "canvas"})' in html
    template = (KIT_ROOT / "templates" / "dashboard_v5.html").read_text()
    assert "innerHTML" not in template


def test_compile_escapes_script_breakout(tmp_path):
    data = minimal_dashboard_data_v5()
    data["meta"]["title"] = "</script><script>alert(1)</script>"
    html = compile_fixture(tmp_path, data=data)
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script\\u003e" in html


def test_compile_is_structurally_deterministic(tmp_path):
    first = compile_fixture(tmp_path / "a")
    second = compile_fixture(tmp_path / "b")
    assert extract_embedded_constant(first, "LAYOUT") == extract_embedded_constant(
        second, "LAYOUT"
    )
    assert extract_embedded_constant(
        first, "OPTIONS_BY_COMPONENT"
    ) == extract_embedded_constant(second, "OPTIONS_BY_COMPONENT")


def test_compiled_template_locks_wide_canvas_units_and_compact_source_copy(tmp_path):
    html = compile_fixture(tmp_path)

    assert 'width: min(100%, 1720px)' in html
    assert '.dashboard-component[data-kind="source_note"]' in html
    assert 'box-shadow: none' in html
    assert '`(단위: ${[...units].join(", ")})`' in html
    assert 'const labels = {now: "현재", why: "배경", so: "해석", act: "확인 기준"}' in html
    assert 'source.ref.split(/[\\\\/]/).at(-1)' in html
    assert 'sourceRef.title = source.ref' in html


def test_compiled_template_separates_kpi_units_and_formats_period_delta_as_percent(
    tmp_path,
):
    html = compile_fixture(tmp_path)

    assert '.kpi-unit' in html
    assert '`(단위: ${kpi.unit})`' in html
    assert 'function formatKpiComparison(kpi)' in html
    assert 'comparison.kind === "period_delta"' in html
    assert 'formatNumber(Math.abs(comparison.delta), 1)}%`' in html
    assert '`${formatNumber(kpi.value, precision)}${kpi.unit || ""}`' not in html
    assert '.kpi-comparison[data-status="good"]' in html
    assert '.kpi-comparison[data-status="bad"]' in html
    assert '.kpi-comparison[data-direction="up"]' not in html


def test_compiled_template_keeps_mobile_kpis_two_column_and_uses_short_table_title(
    tmp_path,
):
    html = compile_fixture(tmp_path)

    assert '@media (max-width: 420px)' not in html
    assert 'titleFor(el, component, "비교에 사용한 세부 수치")' in html


def test_compiled_template_formats_structured_numbers_across_axes_tooltips_and_tables(
    tmp_path,
):
    html = compile_fixture(tmp_path)

    assert "function formatDisplayValue(value, numeric = false, precision = null)" in html
    assert "function applyCanonicalNumberFormatting(option)" in html
    assert "option.tooltip.valueFormatter" in html
    assert 'axis.type === "value"' in html
    assert "tableData.numericColumns" in html
    assert 'column.type === "number"' in html


def test_render_dashboard_v5_cli_writes_html_and_manifest(tmp_path):
    paths = write_v5_fixture(tmp_path)
    output = tmp_path / "dashboard.html"
    result = subprocess.run(
        [
            sys.executable,
            str(KIT_ROOT / "scripts" / "render_dashboard_v5.py"),
            "--chart-spec",
            str(paths.chart_spec),
            "--layout",
            str(paths.layout),
            "--data",
            str(paths.data),
            "--output",
            str(output),
        ],
        cwd=KIT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.exists()
    assert (tmp_path / "dashboard_build_manifest.json").exists()


def test_compiler_fails_closed_for_non_v5_contract(tmp_path):
    from dashboard_v5.compiler import compile_dashboard
    from dashboard_v5.contract import ContractError

    paths = write_v5_fixture(tmp_path)
    data = json.loads(paths.data.read_text())
    data["meta"]["dashboard_profile_contract"] = "v4"
    paths.data.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContractError, match="contract mismatch"):
        compile_dashboard(
            *paths, output_path=tmp_path / "dashboard.html", kit_root=KIT_ROOT
        )
    assert not (tmp_path / "dashboard.html").exists()


def test_compiler_rejects_tampered_vendor_checksum(tmp_path):
    from dashboard_v5.compiler import compile_dashboard
    from dashboard_v5.contract import ContractError

    paths = write_v5_fixture(tmp_path / "fixture")
    fake_kit = tmp_path / "kit"
    (fake_kit / "templates" / "vendor").mkdir(parents=True)
    shutil.copy2(
        KIT_ROOT / "templates" / "dashboard_v5.html",
        fake_kit / "templates" / "dashboard_v5.html",
    )
    shutil.copy2(
        KIT_ROOT / "templates" / "vendor" / "manifest.json",
        fake_kit / "templates" / "vendor" / "manifest.json",
    )
    bundle = (KIT_ROOT / "templates" / "vendor" / "echarts.min.js").read_bytes()
    (fake_kit / "templates" / "vendor" / "echarts.min.js").write_bytes(
        bundle + b"\n// tampered\n"
    )
    with pytest.raises(ContractError, match="vendor checksum"):
        compile_dashboard(
            *paths,
            output_path=tmp_path / "dashboard.html",
            kit_root=fake_kit,
        )
