"""Deterministic plan-quality checks for the v5.1 opt-in contract."""

from __future__ import annotations

import re
from typing import Any


_FAMILY_VARIANTS = {
    "trend": {"line", "area", "slope"},
    "comparison": {"bar", "slope"},
    "composition": {"bar", "stacked_bar"},
    "distribution": {"histogram", "boxplot"},
    "relationship": {"scatter"},
    "matrix": {"heatmap"},
    "decomposition": {"waterfall", "bar"},
}

_MINIMUM_POINTS = {
    "line": 3,
    "area": 3,
    "bar": 2,
    "stacked_bar": 2,
    "histogram": 20,
    "scatter": 20,
    "heatmap": 4,
    "boxplot": 5,
    "waterfall": 3,
    "slope": 2,
}

_NUMBER_TOKEN = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?")


def _compact_question(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or "").lower())
    return text.rstrip("?.!。？！")


def _numeric_tokens(value: Any) -> set[str]:
    return {match.replace(",", "") for match in _NUMBER_TOKEN.findall(str(value or ""))}


def _metric_index(chart_spec: dict) -> tuple[dict[str, dict], str | None]:
    quality = chart_spec.get("quality_contract") or {}
    brief = quality.get("decision_brief") or {}
    metrics = {
        str(metric.get("metric_id")): metric
        for metric in quality.get("metrics") or []
        if isinstance(metric, dict) and metric.get("metric_id")
    }
    decision_id = brief.get("decision_id")
    return metrics, str(decision_id) if decision_id else None


def _chart_quality_issues(
    chart_spec: dict,
    metrics: dict[str, dict],
    decision_id: str | None,
) -> list[str]:
    issues: list[str] = []
    seen_questions: dict[str, str] = {}

    for metric_id, metric in metrics.items():
        if metric.get("decision_link") != decision_id:
            issues.append(
                f"metric {metric_id} decision_link {metric.get('decision_link')!r} "
                f"does not match decision {decision_id!r}"
            )

    for plan in chart_spec.get("charts") or []:
        if not isinstance(plan, dict):
            continue
        chart_id = str(plan.get("id") or "<unknown>")
        question = _compact_question(plan.get("question"))
        if question:
            if question in seen_questions:
                issues.append(
                    f"duplicate chart question: {seen_questions[question]} and {chart_id}"
                )
            else:
                seen_questions[question] = chart_id

        measures = {
            str(value)
            for value in (plan.get("data_requirements") or {}).get("measures") or []
        }
        linked_metric_ids = measures & set(metrics)
        if not linked_metric_ids:
            issues.append(
                f"chart {chart_id} does not reference a declared metric in "
                "data_requirements.measures"
            )
        else:
            calculation_source = (plan.get("calculation") or {}).get("source_ref")
            linked_sources = {
                metrics[metric_id].get("source_ref") for metric_id in linked_metric_ids
            }
            if calculation_source not in linked_sources:
                issues.append(
                    f"chart {chart_id} calculation.source_ref {calculation_source!r} "
                    f"does not match linked metric sources {sorted(linked_sources)!r}"
                )

        visual = plan.get("visual_contract") or {}
        family = visual.get("family")
        variant = visual.get("variant")
        allowed_variants = _FAMILY_VARIANTS.get(str(family), set())
        if variant not in allowed_variants:
            issues.append(
                f"chart {chart_id} family {family!r} does not allow variant {variant!r}"
            )

        sufficiency = visual.get("data_sufficiency") or {}
        status = sufficiency.get("status")
        observed_points = sufficiency.get("observed_points")
        observed_series = sufficiency.get("observed_series")
        declared_minimum = sufficiency.get("minimum_points")
        default_minimum = _MINIMUM_POINTS.get(str(variant), 0)
        minimum_points = max(
            default_minimum,
            declared_minimum if isinstance(declared_minimum, int) else 0,
        )
        if (
            status == "sufficient"
            and isinstance(observed_points, int)
            and observed_points < minimum_points
        ):
            issues.append(
                f"chart {chart_id} {variant} requires at least {minimum_points} "
                f"observed points, got {observed_points}"
            )
        if status == "sufficient" and variant == "slope":
            if observed_points != 2:
                issues.append(
                    f"chart {chart_id} slope requires exactly 2 observed points, "
                    f"got {observed_points!r}"
                )
            if not isinstance(observed_series, int) or observed_series < 2:
                issues.append(
                    f"chart {chart_id} slope requires at least 2 observed series, "
                    f"got {observed_series!r}"
                )
        if status == "sufficient" and variant == "stacked_bar":
            if not isinstance(observed_series, int) or observed_series < 2:
                issues.append(
                    f"chart {chart_id} stacked_bar requires at least 2 observed series, "
                    f"got {observed_series!r}"
                )
        if status == "sufficient" and variant == "scatter":
            distinct_x = sufficiency.get("observed_distinct_x")
            distinct_y = sufficiency.get("observed_distinct_y")
            if (
                not isinstance(distinct_x, int)
                or not isinstance(distinct_y, int)
                or distinct_x < 3
                or distinct_y < 3
            ):
                issues.append(
                    f"chart {chart_id} scatter requires at least 3 distinct values "
                    f"per axis, got x={distinct_x!r}, y={distinct_y!r}"
                )
        if status == "sufficient" and variant == "heatmap":
            x_categories = sufficiency.get("observed_x_categories")
            y_categories = sufficiency.get("observed_y_categories")
            if (
                not isinstance(x_categories, int)
                or not isinstance(y_categories, int)
                or x_categories < 2
                or y_categories < 2
            ):
                issues.append(
                    f"chart {chart_id} heatmap requires at least 2 categories per axis, "
                    f"got x={x_categories!r}, y={y_categories!r}"
                )
            cell_density = sufficiency.get("cell_density")
            if not isinstance(cell_density, (int, float)) or cell_density < 0.5:
                issues.append(
                    f"chart {chart_id} heatmap requires at least 50% cell density, "
                    f"got {cell_density!r}"
                )
        if (
            status == "sufficient"
            and variant == "bar"
            and isinstance(observed_points, int)
            and observed_points > 20
            and visual.get("mobile_strategy")
            not in {"top_n_with_detail", "table_fallback"}
        ):
            issues.append(
                f"chart {chart_id} bar has {observed_points} categories without "
                "top-N or table fallback"
            )
        if status == "fallback_required":
            fallback = sufficiency.get("fallback_chart")
            if not fallback:
                issues.append(f"chart {chart_id} requires a fallback chart")
            elif variant != fallback:
                issues.append(
                    f"chart {chart_id} fallback chart {fallback!r} is not applied; "
                    f"variant is {variant!r}"
                )

        palette_mode = (visual.get("palette_policy") or {}).get("mode")
        if (
            palette_mode == "categorical_identity"
            and isinstance(observed_series, int)
            and observed_series > 8
            and visual.get("legend_strategy") not in {"direct_labels", "paginated"}
        ):
            issues.append(
                f"chart {chart_id} has more than 8 identity series but uses "
                f"legend strategy {visual.get('legend_strategy')!r}"
            )
    return issues


def _layout_quality_issues(
    chart_spec: dict,
    layout: dict,
    metrics: dict[str, dict],
    decision_id: str | None,
) -> list[str]:
    issues: list[str] = []
    chart_ids = {
        str(plan.get("id"))
        for plan in chart_spec.get("charts") or []
        if isinstance(plan, dict) and plan.get("id")
    }
    source_refs = {
        str(metric.get("source_ref"))
        for metric in metrics.values()
        if metric.get("source_ref")
    }
    valid_evidence = set(metrics) | chart_ids | source_refs | {"dashboard_data.meta"}

    for component in layout.get("components") or []:
        if not isinstance(component, dict):
            continue
        component_id = str(component.get("id") or "<unknown>")
        kind = component.get("kind")
        link = component.get("decision_link")
        if kind in {"header", "source_note"}:
            if link is not None:
                issues.append(
                    f"component {component_id} decision_link must be null for {kind}"
                )
        elif link != decision_id:
            issues.append(
                f"component {component_id} decision_link {link!r} does not match "
                f"decision {decision_id!r}"
            )

        evidence_refs = {
            str(value) for value in component.get("evidence_refs") or []
        }
        unknown = sorted(evidence_refs - valid_evidence)
        if unknown:
            issues.append(
                f"component {component_id} evidence_refs contain unknown ids: {unknown}"
            )
        if kind == "kpi_group" and not evidence_refs.intersection(metrics):
            issues.append(
                f"component {component_id} evidence_refs do not reference a metric"
            )
        if kind == "chart" and not evidence_refs.intersection(chart_ids):
            issues.append(
                f"component {component_id} evidence_refs do not reference a chart"
            )
        if kind in {"insight", "table"} and not evidence_refs.intersection(
            set(metrics) | chart_ids
        ):
            issues.append(
                f"component {component_id} evidence_refs do not reference a chart or metric"
            )
        if kind == "source_note" and not evidence_refs.intersection(source_refs):
            issues.append(
                f"component {component_id} evidence_refs do not reference a source"
            )
    return issues


def validate_v51_plan_quality(chart_spec: dict, layout: dict) -> list[str]:
    """Return deterministic semantic issues for an opted-in v5.1 plan."""

    quality = chart_spec.get("quality_contract") or {}
    if quality.get("version") != "v5.1":
        return []

    issues: list[str] = []
    brief = quality.get("decision_brief") or {}
    chart_audience = (chart_spec.get("meta") or {}).get("audience")
    if brief.get("primary_audience") != chart_audience:
        issues.append(
            "decision_brief.primary_audience does not match meta.audience: "
            f"{brief.get('primary_audience')!r} != {chart_audience!r}"
        )

    metrics, decision_id = _metric_index(chart_spec)
    issues.extend(_chart_quality_issues(chart_spec, metrics, decision_id))
    issues.extend(_layout_quality_issues(chart_spec, layout, metrics, decision_id))
    return issues


def _dashboard_charts(data: dict) -> dict[str, dict]:
    return {
        str(chart.get("id")): chart
        for panel in data.get("panels") or []
        if isinstance(panel, dict)
        for chart in panel.get("charts") or []
        if isinstance(chart, dict) and chart.get("id")
    }


def _chart_shape(chart: dict) -> tuple[int | None, int | None]:
    chart_type = chart.get("type")
    encoding = chart.get("encoding") or {}
    if chart_type in {"line", "area", "bar", "stacked_bar"}:
        x_values = (encoding.get("x") or {}).get("values") or []
        return len(x_values), len(encoding.get("series") or [])
    if chart_type == "histogram":
        bins = encoding.get("bins") or []
        return sum(
            int(item.get("count") or 0) for item in bins if isinstance(item, dict)
        ), 1
    if chart_type == "scatter":
        points = encoding.get("points") or []
        groups = {
            item.get("group")
            for item in points
            if isinstance(item, dict) and item.get("group") is not None
        }
        return len(points), max(1, len(groups))
    if chart_type == "heatmap":
        cells = [
            item
            for item in encoding.get("cells") or []
            if isinstance(item, dict) and item.get("value") is not None
        ]
        return len(cells), 1
    if chart_type == "boxplot":
        return None, len(encoding.get("boxes") or [])
    if chart_type == "waterfall":
        return len(encoding.get("steps") or []), 1
    if chart_type == "slope":
        return 2, len(encoding.get("series") or [])
    return None, None


def _chart_has_data(chart: dict) -> bool:
    chart_type = chart.get("type")
    encoding = chart.get("encoding") or {}
    if chart_type in {"line", "area", "bar", "stacked_bar", "slope"}:
        return any(
            any(value is not None for value in (series.get("values") or []))
            for series in encoding.get("series") or []
            if isinstance(series, dict)
        )
    if chart_type == "histogram":
        return any(
            int(item.get("count") or 0) > 0
            for item in encoding.get("bins") or []
            if isinstance(item, dict)
        )
    if chart_type == "scatter":
        return any(
            item.get("x") is not None and item.get("y") is not None
            for item in encoding.get("points") or []
            if isinstance(item, dict)
        )
    if chart_type == "heatmap":
        return any(
            item.get("value") is not None
            for item in encoding.get("cells") or []
            if isinstance(item, dict)
        )
    if chart_type == "boxplot":
        return bool(encoding.get("boxes"))
    if chart_type == "waterfall":
        return bool(encoding.get("steps"))
    return False


def _chart_numeric_values(chart: dict) -> list[float]:
    chart_type = chart.get("type")
    encoding = chart.get("encoding") or {}
    values: list[Any] = []
    if chart_type in {"line", "area", "bar", "stacked_bar"}:
        values = [
            value
            for series in encoding.get("series") or []
            if isinstance(series, dict)
            for value in series.get("values") or []
        ]
    elif chart_type == "histogram":
        values = [item.get("count") for item in encoding.get("bins") or []]
    elif chart_type == "scatter":
        values = [
            item.get("y") for item in encoding.get("points") or [] if isinstance(item, dict)
        ]
    elif chart_type == "heatmap":
        values = [
            item.get("value") for item in encoding.get("cells") or [] if isinstance(item, dict)
        ]
    elif chart_type == "boxplot":
        values = [
            item.get(key)
            for item in encoding.get("boxes") or []
            if isinstance(item, dict)
            for key in ("min", "q1", "median", "q3", "max")
        ]
    elif chart_type == "waterfall":
        values = [item.get("value") for item in encoding.get("steps") or []]
    elif chart_type == "slope":
        values = [
            item.get(key)
            for item in encoding.get("series") or []
            if isinstance(item, dict)
            for key in ("start", "end")
        ]
    return [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]


def _chart_units(chart: dict) -> set[str]:
    chart_type = chart.get("type")
    encoding = chart.get("encoding") or {}
    units: set[str] = set()
    if chart_type in {"line", "area", "bar", "stacked_bar"}:
        units.update(
            str(series.get("unit"))
            for series in encoding.get("series") or []
            if isinstance(series, dict) and series.get("unit")
        )
    elif chart_type == "histogram":
        unit = (encoding.get("x") or {}).get("unit")
        if unit:
            units.add(str(unit))
    elif chart_type == "scatter":
        for axis in ("x", "y"):
            unit = (encoding.get(axis) or {}).get("unit")
            if unit:
                units.add(str(unit))
    elif chart_type == "heatmap":
        unit = (encoding.get("value") or {}).get("unit")
        if unit:
            units.add(str(unit))
    elif chart_type in {"boxplot", "waterfall", "slope"}:
        unit = (encoding.get("y") or {}).get("unit")
        if unit:
            units.add(str(unit))
    return units


def _measurement_units(data: dict) -> set[str]:
    units: set[str] = set()
    for kpi in data.get("kpis") or []:
        if isinstance(kpi, dict) and kpi.get("unit"):
            units.add(str(kpi["unit"]))
    for panel in data.get("panels") or []:
        if not isinstance(panel, dict):
            continue
        for chart in panel.get("charts") or []:
            if isinstance(chart, dict):
                units.update(_chart_units(chart))
        for column in (panel.get("table") or {}).get("columns") or []:
            if isinstance(column, dict) and column.get("unit"):
                units.add(str(column["unit"]))
    return {unit for unit in units if unit not in {"년", "월", "일"}}


def _reader_facing_copy(data: dict) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []

    def add(path: str, value: Any) -> None:
        if isinstance(value, str) and value.strip():
            values.append((path, value))

    meta = data.get("meta") or {}
    for key in ("title", "domain", "period"):
        add(f"meta.{key}", meta.get(key))
    for kpi_index, kpi in enumerate(data.get("kpis") or []):
        if not isinstance(kpi, dict):
            continue
        for key in ("label", "denominator", "note"):
            add(f"kpis[{kpi_index}].{key}", kpi.get(key))
        add(
            f"kpis[{kpi_index}].comparison.basis",
            (kpi.get("comparison") or {}).get("basis"),
        )
    for panel_index, panel in enumerate(data.get("panels") or []):
        if not isinstance(panel, dict):
            continue
        for key in ("title", "method"):
            add(f"panels[{panel_index}].{key}", panel.get(key))
        for story_key, cell in (panel.get("story") or {}).items():
            if not isinstance(cell, dict):
                continue
            for key in ("value", "desc"):
                add(f"panels[{panel_index}].story.{story_key}.{key}", cell.get(key))
        for action_index, action in enumerate(panel.get("actions") or []):
            if not isinstance(action, dict):
                continue
            for key in ("title", "why"):
                add(
                    f"panels[{panel_index}].actions[{action_index}].{key}",
                    action.get(key),
                )
        for chart_index, chart in enumerate(panel.get("charts") or []):
            if not isinstance(chart, dict):
                continue
            for key in ("title", "desc"):
                add(
                    f"panels[{panel_index}].charts[{chart_index}].{key}",
                    chart.get(key),
                )
    return values


def _ungrouped_large_quantity_issues(data: dict) -> list[str]:
    units = sorted(_measurement_units(data), key=len, reverse=True)
    if not units:
        return []
    unit_pattern = "|".join(re.escape(unit) for unit in units)
    pattern = re.compile(
        rf"(?<![\d,])[-+]?\d{{4,}}(?:\.\d+)?\s*(?:{unit_pattern})"
    )
    issues: list[str] = []
    for path, text in _reader_facing_copy(data):
        for match in pattern.finditer(text):
            issues.append(
                f"reader-facing copy uses an ungrouped quantity {match.group(0)!r} "
                f"at {path}"
            )
    return issues


def _layout_component_by_chart(layout: dict, chart_id: str) -> dict | None:
    for component in layout.get("components") or []:
        if (
            isinstance(component, dict)
            and component.get("kind") == "chart"
            and chart_id in (component.get("data_refs") or [])
        ):
            return component
    return None


def _chart_execution_issues(chart_spec: dict, layout: dict, data: dict) -> list[str]:
    issues: list[str] = []
    actual_charts = _dashboard_charts(data)
    for plan in chart_spec.get("charts") or []:
        if not isinstance(plan, dict):
            continue
        chart_id = str(plan.get("id") or "<unknown>")
        chart = actual_charts.get(chart_id)
        if chart is None:
            continue
        visual = plan.get("visual_contract") or {}
        sufficiency = visual.get("data_sufficiency") or {}
        actual_points, actual_series = _chart_shape(chart)
        declared_points = sufficiency.get("observed_points")
        declared_series = sufficiency.get("observed_series")
        if actual_points is not None and declared_points != actual_points:
            issues.append(
                f"chart {chart_id} declares {declared_points!r} observed points "
                f"but data has {actual_points}"
            )
        if actual_series is not None and declared_series != actual_series:
            issues.append(
                f"chart {chart_id} declares {declared_series!r} observed series "
                f"but data has {actual_series}"
            )

        copy_context = visual.get("copy_context") or {}
        visible_copy = " ".join(
            str(value or "") for value in (chart.get("title"), chart.get("desc"))
        ).casefold()
        for field in (
            "scope_label",
            "metric_label",
            "comparison_period",
        ):
            expected = str(copy_context.get(field) or "").strip().casefold()
            if expected and expected not in visible_copy:
                issues.append(
                    f"chart {chart_id} visible copy misses {field} {expected!r}"
                )
        unit_context = str(copy_context.get("unit_label") or "").strip().casefold()
        if unit_context and ("단위" not in visible_copy or unit_context not in visible_copy):
            issues.append(
                f"chart {chart_id} visible copy misses unit_label {unit_context!r}"
            )
        if copy_context.get("title_mode") == "conclusion":
            period_numbers = _numeric_tokens(copy_context.get("comparison_period"))
            evidence_numbers = _numeric_tokens(
                (plan.get("insight") or {}).get("evidence")
            ) - period_numbers
            visible_numbers = _numeric_tokens(visible_copy) - period_numbers
            if not evidence_numbers.intersection(visible_numbers):
                issues.append(
                    f"chart {chart_id} conclusion copy lacks grounded numeric evidence"
                )
        unit_label = str(copy_context.get("unit_label") or "")
        units = _chart_units(chart)
        missing_units = sorted(unit for unit in units if unit not in unit_label)
        if missing_units:
            issues.append(
                f"chart {chart_id} copy_context.unit_label misses units {missing_units}"
            )

        variant = visual.get("variant")
        if variant == "bar":
            if visual.get("scale_policy") != "zero_baseline" or (
                (chart.get("encoding") or {}).get("zero_baseline") is False
            ):
                issues.append(f"chart {chart_id} bar must use a zero baseline")

        palette = visual.get("palette_policy") or {}
        if palette.get("mode") == "diverging":
            midpoint = palette.get("midpoint")
            values = _chart_numeric_values(chart)
            if not isinstance(midpoint, (int, float)) or isinstance(midpoint, bool):
                issues.append(
                    f"chart {chart_id} diverging palette requires a meaningful midpoint"
                )
            elif values and not min(values) <= float(midpoint) <= max(values):
                issues.append(
                    f"chart {chart_id} diverging midpoint {midpoint} is outside "
                    f"observed range {min(values):g}..{max(values):g}"
                )
        if isinstance(palette.get("max_color_roots"), int) and palette.get(
            "max_color_roots"
        ) > 5:
            issues.append(f"chart {chart_id} palette exceeds 5 color roots")
        if (
            isinstance(declared_series, int)
            and declared_series > 1
            and not visual.get("non_color_channels")
        ):
            issues.append(f"chart {chart_id} multi-series chart cannot rely on color alone")

        component = _layout_component_by_chart(layout, chart_id) or {}
        series_layout = (component.get("render_options") or {}).get(
            "series_layout", "overlay"
        )
        if variant in {"line", "area"} and len(units) > 1 and series_layout == "overlay":
            issues.append(
                f"chart {chart_id} different units cannot use overlay: {sorted(units)}"
            )
    return issues


def _empty_component_issues(layout: dict, data: dict) -> list[str]:
    issues: list[str] = []
    kpis = {
        str(item.get("id")): item
        for item in data.get("kpis") or []
        if isinstance(item, dict) and item.get("id")
    }
    panels = {
        str(item.get("id")): item
        for item in data.get("panels") or []
        if isinstance(item, dict) and item.get("id")
    }
    charts = _dashboard_charts(data)
    stateful = {"legend_toggle", "data_zoom", "local_filter"}
    signatures: dict[tuple[str, str, tuple[str, ...]], str] = {}

    for component in layout.get("components") or []:
        if not isinstance(component, dict):
            continue
        component_id = str(component.get("id") or "<unknown>")
        kind = str(component.get("kind") or "")
        purpose = str(component.get("purpose") or "")
        refs = [str(value) for value in component.get("data_refs") or []]
        evidence_refs = tuple(
            sorted(str(value) for value in component.get("evidence_refs") or [])
        )
        signature = (kind, purpose, evidence_refs)
        if kind not in {"header", "source_note", "control_bar"}:
            previous = signatures.get(signature)
            if previous is not None:
                issues.append(
                    "duplicate component purpose/evidence: "
                    f"{previous} and {component_id}"
                )
            else:
                signatures[signature] = component_id

        if kind == "kpi_group" and component.get("empty_behavior") == "block":
            for ref in refs:
                kpi = kpis.get(ref) or {}
                value = kpi.get("value")
                if value is None or (isinstance(value, str) and not value.strip()):
                    issues.append(f"KPI {ref} is empty in component {component_id}")
        if kind == "chart" and component.get("empty_behavior") == "block":
            for ref in refs:
                chart = charts.get(ref)
                if chart is None or not _chart_has_data(chart):
                    issues.append(f"chart {ref} is empty in component {component_id}")
        if kind == "insight" and component.get("empty_behavior") == "block":
            for ref in refs:
                story = (panels.get(ref) or {}).get("story") or {}
                values = [
                    cell.get(key)
                    for cell in story.values()
                    if isinstance(cell, dict)
                    for key in ("value", "desc")
                ]
                if not any(str(value or "").strip() for value in values):
                    issues.append(
                        f"insight component {component_id} has no reader-facing content"
                    )
        if kind == "control_bar" and not (
            set(component.get("interactions") or []) & stateful
        ):
            issues.append(
                f"control {component_id} has no state-changing interaction"
            )
    return issues


def validate_v51_execution_quality(
    chart_spec: dict, layout: dict, data: dict
) -> list[str]:
    """Return v5.1 plan-to-data and minimal-composition issues."""

    if (chart_spec.get("quality_contract") or {}).get("version") != "v5.1":
        return []
    issues = _chart_execution_issues(chart_spec, layout, data)
    issues.extend(_empty_component_issues(layout, data))
    issues.extend(_ungrouped_large_quantity_issues(data))
    return issues
