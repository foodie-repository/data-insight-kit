"""Allowlisted translation from dashboard chart data to ECharts options.

The mapper deliberately accepts only the structured dashboard_data contract.
It never accepts raw JavaScript, callbacks, formatter source, or arbitrary
ECharts option fragments from an agent-authored layout.
"""

from __future__ import annotations

from typing import Any


ALLOWED_RENDER_OPTIONS = {
    "orientation",
    "legend",
    "label_density",
    "series_layout",
}
ALLOWED_INTERACTIONS = {
    "tooltip",
    "legend_toggle",
    "data_zoom",
    "local_filter",
    "reset",
}

_ALLOWED_OPTION_VALUES = {
    "orientation": {"auto", "horizontal", "vertical"},
    "legend": {"top", "right", "bottom", "none"},
    "label_density": {"relaxed", "standard", "compact"},
    "series_layout": {"overlay", "stacked_panels"},
}

ROLE_COLORS = {
    "neutral": "#cbd5e1",
    "info": "#3157d5",
    "good": "#087e6b",
    "bad": "#b42318",
    "warn": "#a15c00",
    "cat1": "#4e79a7",
    "cat2": "#59a14f",
    "cat3": "#f28e2b",
    "cat4": "#e15759",
    "cat5": "#76b7b2",
    "cat6": "#edc948",
    "cat7": "#b07aa1",
    "cat8": "#ff9da7",
}

IDENTITY_COLORS = (
    ROLE_COLORS["cat1"],
    ROLE_COLORS["cat2"],
    ROLE_COLORS["cat3"],
    ROLE_COLORS["cat4"],
    ROLE_COLORS["cat5"],
)

HEATMAP_SEQUENTIAL_COLORS = [
    "#eff6ff",
    "#bfdbfe",
    "#60a5fa",
    "#2563eb",
    "#1e3a8a",
]

HEATMAP_DIVERGING_COLORS = (
    "#b42318",
    "#fecdca",
    "#dbeafe",
    "#3157d5",
)


class OptionError(ValueError):
    """Raised when untrusted layout data requests an unsupported option."""


def _numeric_precision(value: Any, declared: Any = None) -> int:
    if isinstance(declared, int) and not isinstance(declared, bool):
        return max(0, declared)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 0
    text = str(value)
    if "e" in text.lower() or "." not in text:
        return 0
    return min(6, len(text.rstrip("0").split(".", 1)[1]))


def _format_numeric_label(value: Any, precision: Any = None) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    digits = _numeric_precision(value, precision)
    return f"{value:,.{digits}f}"


def _role_color(role: Any) -> str:
    normalized = str(role or "neutral")
    try:
        return ROLE_COLORS[normalized]
    except KeyError as exc:
        raise OptionError(f"unsupported color role: {normalized}") from exc


def _validate_requests(
    render_options: dict[str, Any], interactions: list[str]
) -> None:
    unknown_options = sorted(set(render_options) - ALLOWED_RENDER_OPTIONS)
    if unknown_options:
        raise OptionError(f"unknown render option: {', '.join(unknown_options)}")
    for key, value in render_options.items():
        if value not in _ALLOWED_OPTION_VALUES[key]:
            raise OptionError(f"unsupported render option value: {key}={value!r}")
    unknown_interactions = sorted(set(interactions) - ALLOWED_INTERACTIONS)
    if unknown_interactions:
        raise OptionError(f"unknown interaction: {', '.join(unknown_interactions)}")


def _legend_option(position: str, interactive: bool) -> dict[str, Any]:
    legend: dict[str, Any] = {
        "show": position != "none",
        "selectedMode": interactive,
    }
    if position == "right":
        legend.update(
            {
                "right": 8,
                "top": 24,
                "bottom": 24,
                "orient": "vertical",
            }
        )
    elif position == "bottom":
        legend.update({"bottom": 0, "left": "center"})
    else:
        legend.update({"top": 0, "left": "center"})
    return legend


def _axis_label(label_density: str) -> dict[str, Any]:
    return {
        "interval": {"relaxed": 1, "standard": "auto", "compact": 0}[
            label_density
        ],
        "hideOverlap": True,
    }


def _merge_option(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_option(target[key], value)
        else:
            target[key] = value


def _upsert_media_option(
    option: dict[str, Any], query: dict[str, Any], patch: dict[str, Any]
) -> None:
    for item in option.setdefault("media", []):
        if item.get("query") == query:
            _merge_option(item.setdefault("option", {}), patch)
            return
    option["media"].append({"query": query, "option": patch})


def _value_axis(
    name: str = "", *, name_gap: int = 32, name_rotate: int | None = None
) -> dict[str, Any]:
    axis: dict[str, Any] = {
        "type": "value",
        "splitNumber": 3,
        "axisLabel": {"hideOverlap": True},
    }
    if name:
        axis.update(
            {
                "name": name,
                "nameLocation": "middle",
                "nameGap": name_gap,
            }
        )
        if name_rotate is not None:
            axis["nameRotate"] = name_rotate
    return axis


def _category_axes(
    encoding: dict[str, Any], orientation: str, label_density: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    category = {
        "type": "category",
        "name": encoding.get("x", {}).get("label", ""),
        "data": list(encoding.get("x", {}).get("values") or []),
        "axisLabel": _axis_label(label_density),
    }
    value = _value_axis()
    if orientation == "horizontal":
        return value, category
    category.update({"nameLocation": "middle", "nameGap": 32})
    return category, value


def _category_series(
    chart_type: str, encoding: dict[str, Any], orientation: str
) -> list[dict[str, Any]]:
    series_type = "line" if chart_type in {"line", "area"} else "bar"
    stack_mode = encoding.get("stack")
    stack_key = "dashboard-stack" if stack_mode in {"stacked", "stacked_100"} else None
    result = []
    for source in encoding.get("series") or []:
        values = list(source.get("values") or [])
        point_roles = source.get("point_roles")
        if point_roles is not None:
            if len(point_roles) != len(values):
                raise OptionError(
                    "point_roles length must match category series values length"
                )
            data: list[Any] = [
                {
                    "value": value,
                    "itemStyle": {"color": _role_color(role)},
                }
                for value, role in zip(values, point_roles)
            ]
        else:
            data = values
        series: dict[str, Any] = {
            "name": source.get("label", ""),
            "type": series_type,
            "data": data,
        }
        if point_roles is None:
            series["itemStyle"] = {"color": _role_color(source.get("role"))}
        if stack_key:
            series["stack"] = stack_key
        if chart_type == "area":
            series["areaStyle"] = {}
        if orientation == "horizontal" and series_type == "bar":
            series["encode"] = {"x": "value", "y": "itemName"}
        result.append(series)
    return result


def _histogram_option(encoding: dict[str, Any]) -> tuple[dict, dict, list[dict]]:
    bins = encoding.get("bins") or []
    labels = [
        f"{_format_numeric_label(item['range'][0])}–"
        f"{_format_numeric_label(item['range'][1])}"
        for item in bins
    ]
    series = [{"type": "bar", "name": "빈도", "data": [item["count"] for item in bins]}]
    return {"type": "category", "data": labels}, {"type": "value"}, series


def _scatter_option(encoding: dict[str, Any]) -> tuple[dict, dict, list[dict]]:
    points = encoding.get("points") or []
    data = []
    for item in points:
        value = [item["x"], item["y"]]
        if item.get("role") is None:
            data.append(value)
        else:
            data.append(
                {
                    "value": value,
                    "itemStyle": {"color": _role_color(item.get("role"))},
                }
            )
    return (
        _value_axis(encoding.get("x", {}).get("label", "")),
        _value_axis(
            encoding.get("y", {}).get("label", ""),
            name_gap=58,
            name_rotate=90,
        ),
        [{"type": "scatter", "data": data}],
    )


def _heatmap_option(
    encoding: dict[str, Any], label_density: str
) -> tuple[dict, dict, list[dict]]:
    x_values = list(encoding.get("x", {}).get("values") or [])
    y_values = list(encoding.get("y", {}).get("values") or [])
    x_index = {value: index for index, value in enumerate(x_values)}
    y_index = {value: index for index, value in enumerate(y_values)}
    cells = encoding.get("cells") or []
    data = [[x_index[item["x"]], y_index[item["y"]], item["value"]] for item in cells]
    x_axis_label = _axis_label(label_density)
    y_axis_label = _axis_label(label_density)
    if label_density == "compact":
        x_axis_label.update({"rotate": 35, "hideOverlap": False, "fontSize": 10})
        y_axis_label.update({"hideOverlap": False, "fontSize": 10})
    return (
        {
            "type": "category",
            "name": encoding.get("x", {}).get("label", ""),
            "nameLocation": "middle",
            "nameGap": 56,
            "data": x_values,
            "axisLabel": x_axis_label,
        },
        {
            "type": "category",
            "name": encoding.get("y", {}).get("label", ""),
            "nameLocation": "middle",
            "nameGap": 68,
            "nameRotate": 90,
            "data": y_values,
            "axisLabel": y_axis_label,
        },
        [{"type": "heatmap", "data": data}],
    )


def _boxplot_option(encoding: dict[str, Any]) -> tuple[dict, dict, list[dict]]:
    boxes = encoding.get("boxes") or []
    data = [
        [item["min"], item["q1"], item["median"], item["q3"], item["max"]]
        for item in boxes
    ]
    return (
        {"type": "category", "data": [item["label"] for item in boxes]},
        {"type": "value", "name": encoding.get("y", {}).get("label", "")},
        [{"type": "boxplot", "data": data}],
    )


def _waterfall_option(encoding: dict[str, Any]) -> tuple[dict, dict, list[dict]]:
    steps = encoding.get("steps") or []
    bridge: list[float | int] = []
    visible: list[float | int] = []
    running: float | int = 0
    for step in steps:
        value = step["value"]
        kind = step["kind"]
        if kind in {"start", "total"}:
            bridge.append(0)
            visible.append(value)
            running = value
        else:
            bridge.append(running if value >= 0 else running + value)
            visible.append(abs(value))
            running += value
    return (
        {"type": "category", "data": [item["label"] for item in steps]},
        {"type": "value", "name": encoding.get("y", {}).get("label", "")},
        [
            {
                "type": "bar",
                "stack": "waterfall",
                "silent": True,
                "itemStyle": {"color": "transparent"},
                "data": bridge,
            },
            {"type": "bar", "stack": "waterfall", "data": visible},
        ],
    )


def _slope_option(encoding: dict[str, Any]) -> tuple[dict, dict, list[dict]]:
    x = encoding.get("x", {})
    series = []
    for item in encoding.get("series") or []:
        mapped = {
            "name": item.get("label", ""),
            "type": "line",
            "data": [item["start"], item["end"]],
        }
        if item.get("role") is not None:
            color = _role_color(item.get("role"))
            mapped["itemStyle"] = {"color": color}
            mapped["lineStyle"] = {"color": color}
        series.append(mapped)
    return (
        {"type": "category", "data": [x.get("start_label"), x.get("end_label")]},
        {"type": "value", "name": encoding.get("y", {}).get("label", "")},
        series,
    )


def build_echarts_option(
    chart: dict[str, Any],
    render_options: dict[str, Any],
    interactions: list[str],
    *,
    visual_contract: dict[str, Any] | None = None,
    identity_colors: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Translate one validated chart without recomputing or interpolating values."""
    _validate_requests(render_options, interactions)
    chart_type = str(chart.get("type") or "")
    encoding = chart.get("encoding") if isinstance(chart.get("encoding"), dict) else {}
    orientation = str(render_options.get("orientation", "auto"))
    legend_position = str(render_options.get("legend", "top"))
    label_density = str(render_options.get("label_density", "standard"))
    series_layout = str(render_options.get("series_layout", "overlay"))
    visual_contract = visual_contract or {}
    identity_colors = identity_colors or {}

    option: dict[str, Any] = {
        "animation": False,
        "aria": {"enabled": True, "decal": {"show": False}},
        "textStyle": {"fontFamily": "system-ui, sans-serif"},
        "tooltip": {"show": "tooltip" in interactions, "trigger": "axis"},
        "legend": _legend_option(
            legend_position, "legend_toggle" in interactions
        ),
        "grid": {
            "left": 48,
            "right": 24,
            "top": 48,
            "bottom": 44,
            "containLabel": True,
        },
    }
    if visual_contract:
        option["tooltip"]["confine"] = True

    if chart_type in {"line", "area", "bar", "stacked_bar"}:
        x_axis, y_axis = _category_axes(encoding, orientation, label_density)
        series = _category_series(chart_type, encoding, orientation)
    elif chart_type == "histogram":
        x_axis, y_axis, series = _histogram_option(encoding)
    elif chart_type == "scatter":
        x_axis, y_axis, series = _scatter_option(encoding)
    elif chart_type == "heatmap":
        x_axis, y_axis, series = _heatmap_option(encoding, label_density)
        values = [item[2] for item in series[0]["data"]]
        if values:
            observed_min = min(values)
            observed_max = max(values)
            if observed_min == observed_max:
                visual_min = min(0, observed_min)
                visual_max = max(0, observed_max)
                if visual_min == visual_max:
                    visual_max = 1
            else:
                visual_min = observed_min
                visual_max = observed_max
        else:
            visual_min, visual_max = 0, 1
        option["visualMap"] = {
            "min": visual_min,
            "max": visual_max,
            "calculable": False,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "dimension": 2,
            "text": ["높음", "낮음"],
            "textGap": 8,
            "inRange": {"color": HEATMAP_SEQUENTIAL_COLORS},
        }
        palette = visual_contract.get("palette_policy") or {}
        midpoint = palette.get("midpoint")
        if (
            palette.get("mode") == "diverging"
            and isinstance(midpoint, (int, float))
            and observed_min <= midpoint <= observed_max
        ):
            pieces: list[dict[str, Any]] = []
            if observed_min < midpoint:
                lower_split = observed_min + (midpoint - observed_min) / 2
                pieces.extend(
                    [
                        {
                            "min": observed_min,
                            "lt": lower_split,
                            "color": HEATMAP_DIVERGING_COLORS[0],
                        },
                        {
                            "min": lower_split,
                            "lte": midpoint,
                            "color": HEATMAP_DIVERGING_COLORS[1],
                        },
                    ]
                )
            if midpoint < observed_max:
                upper_split = midpoint + (observed_max - midpoint) / 2
                pieces.extend(
                    [
                        {
                            "gt": midpoint,
                            "lte": upper_split,
                            "color": HEATMAP_DIVERGING_COLORS[2],
                        },
                        {
                            "gt": upper_split,
                            "max": observed_max,
                            "color": HEATMAP_DIVERGING_COLORS[3],
                        },
                    ]
                )
            option["visualMap"] = {
                "type": "piecewise",
                "pieces": pieces,
                "selectedMode": False,
                "orient": "horizontal",
                "left": "center",
                "bottom": 0,
                "dimension": 2,
                "text": ["높음", "낮음"],
                "textGap": 8,
            }
        option["grid"].update({"left": 84, "top": 24, "bottom": 96})
        option["aria"]["decal"]["show"] = False
    elif chart_type == "boxplot":
        x_axis, y_axis, series = _boxplot_option(encoding)
    elif chart_type == "waterfall":
        x_axis, y_axis, series = _waterfall_option(encoding)
    elif chart_type == "slope":
        x_axis, y_axis, series = _slope_option(encoding)
    else:
        raise OptionError(f"unsupported chart type: {chart_type or '<missing>'}")

    palette_mode = (visual_contract.get("palette_policy") or {}).get("mode")
    source_series = encoding.get("series") or []
    if palette_mode == "categorical_identity":
        for mapped, source in zip(series, source_series):
            color = identity_colors.get(str(source.get("label") or ""))
            if not color:
                continue
            mapped["itemStyle"] = {**mapped.get("itemStyle", {}), "color": color}
            if mapped.get("type") == "line":
                mapped["lineStyle"] = {
                    **mapped.get("lineStyle", {}),
                    "color": color,
                }

    non_color_channels = set(visual_contract.get("non_color_channels") or [])
    line_styles = ("solid", "dashed", "dotted")
    symbols = ("circle", "diamond", "rect", "triangle", "roundRect")
    for index, mapped in enumerate(series):
        if mapped.get("type") == "line" and "line_style" in non_color_channels:
            mapped["lineStyle"] = {
                **mapped.get("lineStyle", {}),
                "type": line_styles[index % len(line_styles)],
                "width": 2.5,
            }
        if mapped.get("type") == "line" and "shape" in non_color_channels:
            mapped["symbol"] = symbols[index % len(symbols)]
        if "open_fill" in non_color_channels:
            base_color = (mapped.get("itemStyle") or {}).get("color") or _role_color(
                "neutral"
            )
            if mapped.get("type") == "line":
                mapped["lineStyle"] = {
                    **mapped.get("lineStyle", {}),
                    "color": base_color,
                }
                mapped["symbolSize"] = 7
            mapped["itemStyle"] = {
                **mapped.get("itemStyle", {}),
                "color": "#ffffff",
                "borderColor": base_color,
                "borderWidth": 2,
            }

    if visual_contract.get("label_strategy") == "direct":
        longest = max((len(str(item.get("name") or "")) for item in series), default=0)
        for index, mapped in enumerate(series):
            if mapped.get("type") == "line":
                mapped["endLabel"] = {
                    "show": True,
                    "formatter": "{a}",
                    "distance": 8,
                }
                mapped["labelLayout"] = {"moveOverlap": "shiftY"}
            elif mapped.get("type") == "bar":
                position = "right" if orientation == "horizontal" else "top"
                mapped["label"] = {
                    "show": True,
                    "position": position,
                }
                source = source_series[index] if index < len(source_series) else {}
                precision = (source.get("format") or {}).get("precision")
                formatted_data: list[Any] = []
                for item in mapped.get("data") or []:
                    if isinstance(item, dict):
                        value = item.get("value")
                        if not isinstance(value, (int, float)) or isinstance(value, bool):
                            formatted_data.append(item)
                            continue
                        item = dict(item)
                        item["label"] = {
                            **(item.get("label") or {}),
                            "show": True,
                            "position": position,
                            "formatter": _format_numeric_label(value, precision),
                        }
                        formatted_data.append(item)
                    elif isinstance(item, (int, float)) and not isinstance(item, bool):
                        formatted_data.append(
                            {
                                "value": item,
                                "label": {
                                    "show": True,
                                    "position": position,
                                    "formatter": _format_numeric_label(item, precision),
                                },
                            }
                        )
                    else:
                        formatted_data.append(item)
                mapped["data"] = formatted_data
        option["grid"]["right"] = max(
            option["grid"]["right"], min(280, longest * 9 + 48)
        )

    if series_layout == "stacked_panels":
        if chart_type not in {"line", "area"} or len(series) < 2:
            raise OptionError(
                "series_layout=stacked_panels requires a multi-series line or area chart"
            )
        series_count = len(series)
        gap_percent = 8
        top_percent = 7
        bottom_percent = 11
        height_percent = (
            100 - top_percent - bottom_percent - gap_percent * (series_count - 1)
        ) / series_count
        grids: list[dict[str, Any]] = []
        x_axes: list[dict[str, Any]] = []
        y_axes: list[dict[str, Any]] = []
        line_styles = ("solid", "dashed", "dotted")
        symbols = ("circle", "diamond", "rect")
        source_series = encoding.get("series") or []
        for index, (mapped, source) in enumerate(zip(series, source_series)):
            top = top_percent + index * (height_percent + gap_percent)
            grids.append(
                {
                    "left": 64,
                    "right": 24,
                    "top": f"{top:.1f}%",
                    "height": f"{height_percent:.1f}%",
                    "containLabel": True,
                }
            )
            local_x = dict(x_axis)
            local_x["gridIndex"] = index
            local_x["axisLabel"] = dict(x_axis.get("axisLabel") or {})
            if index < series_count - 1:
                local_x["name"] = ""
                local_x["axisLabel"]["show"] = False
                local_x["axisTick"] = {"show": False}
            x_axes.append(local_x)
            local_y = _value_axis(str(source.get("label") or ""))
            local_y.update(
                {
                    "gridIndex": index,
                    "nameLocation": "end",
                    "nameGap": 8,
                    "nameTextStyle": {
                        "color": (mapped.get("lineStyle") or {}).get("color")
                        or mapped["itemStyle"]["color"],
                        "fontWeight": 600,
                    },
                }
            )
            y_axes.append(local_y)
            mapped["xAxisIndex"] = index
            mapped["yAxisIndex"] = index
            mapped["lineStyle"] = {
                "type": line_styles[index % len(line_styles)],
                "width": 2.5,
            }
            mapped["symbol"] = symbols[index % len(symbols)]
        option["grid"] = grids
        x_axis = x_axes
        y_axis = y_axes

    option.update({"xAxis": x_axis, "yAxis": y_axis, "series": series})
    scale_policy = visual_contract.get("scale_policy")
    value_axes: list[dict[str, Any]] = []
    for axis in (x_axis, y_axis):
        axes = axis if isinstance(axis, list) else [axis]
        value_axes.extend(
            item for item in axes if isinstance(item, dict) and item.get("type") == "value"
        )
    if scale_policy == "zero_baseline":
        for axis in value_axes:
            # ECharts includes zero when scale is false while still expanding the
            # domain to negative observations. Setting min=0 would clip declines.
            axis["scale"] = False
            axis.pop("min", None)
    elif scale_policy == "focused_range_with_cue":
        for axis in value_axes:
            axis["scale"] = True
        option["graphic"] = [
            {
                "type": "text",
                "right": 12,
                "top": 8,
                "silent": True,
                "style": {
                    "text": "축 범위 확대",
                    "fill": "#667085",
                    "fontSize": 11,
                },
            }
        ]
    elif scale_policy == "indexed_baseline":
        for axis in value_axes:
            axis["scale"] = True
        for mapped in series:
            if mapped.get("type") != "line":
                continue
            mapped["markLine"] = {
                "silent": True,
                "symbol": ["none", "none"],
                "lineStyle": {"color": "#98a2b3", "type": "dashed"},
                "label": {"show": True, "formatter": "기준 100"},
                "data": [{"name": "기준 100", "yAxis": 100}],
            }
    legend_visible = (
        series_layout != "stacked_panels"
        and legend_position != "none"
        and len(series) > 1
    )
    option["legend"]["show"] = legend_visible
    if legend_visible:
        if legend_position == "right":
            option["legend"]["type"] = "scroll"
            longest = max(
                (len(str(item.get("name") or "")) for item in series), default=0
            )
            legend_reserve = min(280, max(164, longest * 9 + 48))
            option["grid"]["right"] = max(
                option["grid"]["right"], legend_reserve
            )
            _upsert_media_option(
                option,
                {"maxWidth": 480},
                {
                    "legend": {
                        "type": "scroll",
                        "orient": "horizontal",
                        "left": 24,
                        "right": 24,
                        "top": "auto",
                        "bottom": 8,
                    },
                    "grid": {"right": 24, "bottom": 96},
                },
            )
        elif legend_position == "top":
            option["grid"]["top"] = max(option["grid"]["top"], 72)
        elif legend_position == "bottom":
            option["grid"]["bottom"] = max(option["grid"]["bottom"], 76)
    if chart_type != "heatmap" and len(series) > 1 and series_layout != "stacked_panels":
        option["aria"]["decal"]["show"] = True
    if (
        visual_contract.get("mobile_strategy") == "top_n_with_detail"
        and chart_type in {"line", "area", "bar", "stacked_bar"}
        and len((encoding.get("x") or {}).get("values") or []) > 8
    ):
        category_key = "yAxis" if orientation == "horizontal" else "xAxis"
        categories = list((encoding.get("x") or {}).get("values") or [])[:8]
        _upsert_media_option(
            option,
            {"maxWidth": 480},
            {
                category_key: {"data": categories},
                "series": [
                    {"data": list(mapped.get("data") or [])[:8]}
                    for mapped in series
                ],
            },
        )
    if "data_zoom" in interactions:
        zoom_axes = list(range(len(series))) if series_layout == "stacked_panels" else None
        option["dataZoom"] = [
            {"type": "inside", **({"xAxisIndex": zoom_axes} if zoom_axes else {})},
            {"type": "slider", **({"xAxisIndex": zoom_axes} if zoom_axes else {})},
        ]
    return option
