"""Renderer selection and cross-document contracts for dashboard v5."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Literal

from jsonschema import Draft202012Validator, FormatChecker

from dashboard_v5.quality import (
    validate_v51_execution_quality,
    validate_v51_plan_quality,
)

RendererMode = Literal["legacy", "v4", "v5"]


class ContractError(ValueError):
    """Raised when renderer contracts cannot select one safe path."""


_KIT_ROOT = Path(__file__).resolve().parents[1]
_LAYOUT_SCHEMA_PATH = _KIT_ROOT / "schemas" / "dashboard_layout.schema.json"


def _duplicate_values(values: list[object]) -> list[object]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _stateful_control_issues(components: list[object]) -> list[str]:
    issues: list[str] = []
    stateful_interactions = {"legend_toggle", "data_zoom", "local_filter"}
    controls = [
        component
        for component in components
        if isinstance(component, dict) and component.get("kind") == "control_bar"
    ]
    for component in components:
        if not isinstance(component, dict) or component.get("kind") != "chart":
            continue
        requested = set(component.get("interactions") or []) & stateful_interactions
        if not requested:
            continue
        chart_ref = (component.get("data_refs") or [None])[0]
        linked = [
            control
            for control in controls
            if chart_ref in (control.get("data_refs") or [])
        ]
        control_interactions = {
            interaction
            for control in linked
            for interaction in (control.get("interactions") or [])
        }
        if (
            not linked
            or not requested.issubset(control_interactions)
            or "reset" not in control_interactions
        ):
            issues.append(
                f"chart component {component.get('id', '<unknown>')} requests "
                f"{sorted(requested)} but has no linked visible state/reset control"
            )
    return issues


def validate_layout(layout: dict) -> list[str]:
    """Return deterministic schema and layout hierarchy issues."""

    schema = json.loads(_LAYOUT_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues = []
    for error in sorted(validator.iter_errors(layout), key=lambda item: list(item.path)):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        issues.append(f"{path}: {error.message}")

    components = layout.get("components")
    if not isinstance(components, list):
        return issues
    issues.extend(_stateful_control_issues(components))

    ids = [item.get("id") for item in components if isinstance(item, dict)]
    duplicate_ids = _duplicate_values(ids)
    if duplicate_ids:
        issues.append(f"duplicate component id: {duplicate_ids}")

    for viewport in ("desktop", "mobile"):
        orders = []
        for component in components:
            placement = component.get("placement") if isinstance(component, dict) else None
            viewport_placement = (
                placement.get(viewport) if isinstance(placement, dict) else None
            )
            if isinstance(viewport_placement, dict) and "order" in viewport_placement:
                orders.append(viewport_placement["order"])
        duplicates = _duplicate_values(orders)
        if duplicates:
            issues.append(f"duplicate {viewport} order: {duplicates}")

    heroes = [
        component
        for component in components
        if isinstance(component, dict) and component.get("role") == "hero"
    ]
    if len(heroes) > 1:
        issues.append(f"hero role allows at most one component, got {len(heroes)}")
    hero_span = None
    if len(heroes) == 1:
        hero_span = (
            ((heroes[0].get("placement") or {}).get("desktop") or {}).get("span")
        )

    for component in components:
        if not isinstance(component, dict):
            continue
        component_id = component.get("id", "<unknown>")
        kind = component.get("kind")
        renderer = component.get("renderer")
        expected_renderer = "echarts" if kind == "chart" else "svg_css"
        if kind and renderer and renderer != expected_renderer:
            issues.append(
                f"component {component_id} kind/renderer mismatch: "
                f"{kind} requires {expected_renderer}"
            )

        placement = component.get("placement") or {}
        desktop = placement.get("desktop") or {}
        mobile = placement.get("mobile") or {}
        start = desktop.get("column_start", 1)
        span = desktop.get("span")
        if isinstance(start, int) and isinstance(span, int) and start + span - 1 > 12:
            issues.append(
                f"component {component_id} exceeds 12-column grid: "
                f"column_start={start}, span={span}"
            )
        if mobile.get("span") != 12:
            issues.append(
                f"component {component_id} mobile span must be 12, "
                f"got {mobile.get('span')!r}"
            )
        if (
            component.get("role") == "support"
            and isinstance(hero_span, int)
            and isinstance(span, int)
            and span > hero_span
        ):
            issues.append(
                f"support component {component_id} span {span} exceeds hero span {hero_span}"
            )
    return issues


def validate_v5_cross_contract(
    chart_spec: dict,
    layout: dict,
    data: dict,
) -> list[str]:
    """Check stable ids and v5 metadata across plan, layout, and data."""

    issues = []
    chart_meta = chart_spec.get("meta") or {}
    chart_design = chart_spec.get("dashboard_design") or {}
    data_meta = data.get("meta") or {}

    if layout.get("run_id") != chart_meta.get("run_id"):
        issues.append(
            "layout run_id does not match chart_spec.meta.run_id: "
            f"{layout.get('run_id')!r} != {chart_meta.get('run_id')!r}"
        )
    profiles = (
        chart_design.get("selected_profile"),
        layout.get("profile_purpose"),
        data_meta.get("dashboard_profile"),
    )
    if len(set(profiles)) != 1:
        issues.append(
            "dashboard profile mismatch across chart/layout/data: "
            f"{profiles!r}"
        )
    if chart_design.get("contract_version") != "v5":
        issues.append("chart_spec does not declare v5 contract")
    if data_meta.get("dashboard_profile_contract") != "v5":
        issues.append("dashboard_data does not declare v5 contract")
    if layout.get("layout_version") != 5:
        issues.append("dashboard_layout does not declare layout_version 5")

    chart_quality = (chart_spec.get("quality_contract") or {}).get("version")
    layout_quality = layout.get("quality_contract_version")
    if chart_quality != layout_quality:
        issues.append(
            "v5.1 quality contract mismatch across chart/layout: "
            f"{chart_quality!r} != {layout_quality!r}"
        )
    if chart_quality == "v5.1" and layout_quality == "v5.1":
        for plan in chart_spec.get("charts") or []:
            if not isinstance(plan, dict):
                continue
            variant = (plan.get("visual_contract") or {}).get("variant")
            chart_type = (plan.get("chart") or {}).get("type")
            if variant != chart_type:
                issues.append(
                    f"chart {plan.get('id', '<unknown>')} visual variant "
                    f"{variant!r} does not match chart.type {chart_type!r}"
                )
        issues.extend(validate_v51_plan_quality(chart_spec, layout))
        issues.extend(validate_v51_execution_quality(chart_spec, layout, data))

    kpi_ids = {
        item.get("id")
        for item in data.get("kpis") or []
        if isinstance(item, dict) and item.get("id")
    }
    source_ids = {
        item.get("id")
        for item in data.get("sources") or []
        if isinstance(item, dict) and item.get("id")
    }
    panels = {
        panel.get("id"): panel
        for panel in data.get("panels") or []
        if isinstance(panel, dict) and panel.get("id")
    }
    charts = {
        chart.get("id"): chart
        for panel in panels.values()
        for chart in panel.get("charts") or []
        if isinstance(chart, dict) and chart.get("id")
    }
    planned_chart_ids = set()
    primary_chart_ids = set()
    for plan in chart_spec.get("charts") or []:
        mapping = plan.get("dashboard_mapping") or {}
        chart_id = mapping.get("chart_id")
        if not chart_id:
            continue
        planned_chart_ids.add(chart_id)
        if mapping.get("surface", "primary") == "primary":
            primary_chart_ids.add(chart_id)

    kpi_ref_counts = Counter()
    chart_ref_counts = Counter()
    components = layout.get("components") or []
    for component in components:
        if not isinstance(component, dict):
            continue
        component_id = component.get("id", "<unknown>")
        kind = component.get("kind")
        refs = component.get("data_refs") or []
        if kind == "header":
            if refs != ["dashboard_data.meta"]:
                issues.append(
                    f"header component {component_id} must reference only dashboard_data.meta"
                )
        elif kind == "kpi_group":
            for ref in refs:
                kpi_ref_counts[ref] += 1
                if ref not in kpi_ids:
                    issues.append(
                        f"component {component_id} KPI data_ref {ref!r} does not exist"
                    )
        elif kind in {"chart", "control_bar"}:
            if kind == "chart" and len(refs) != 1:
                issues.append(
                    f"chart component {component_id} must reference exactly one chart"
                )
            for ref in refs:
                if kind == "chart":
                    chart_ref_counts[ref] += 1
                if ref not in charts:
                    issues.append(
                        f"component {component_id} chart data_ref {ref!r} does not exist"
                    )
                elif ref not in planned_chart_ids:
                    issues.append(
                        f"component {component_id} chart data_ref {ref!r} is not in chart_spec"
                    )
        elif kind == "insight":
            for ref in refs:
                panel = panels.get(ref)
                if panel is None:
                    issues.append(
                        f"component {component_id} panel data_ref {ref!r} does not exist"
                    )
                elif not panel.get("story"):
                    issues.append(
                        f"component {component_id} panel {ref!r} has no story"
                    )
        elif kind == "table":
            for ref in refs:
                panel = panels.get(ref)
                if panel is None:
                    issues.append(
                        f"component {component_id} panel data_ref {ref!r} does not exist"
                    )
                elif not panel.get("table"):
                    issues.append(
                        f"component {component_id} panel {ref!r} has no table"
                    )
        elif kind == "source_note":
            for ref in refs:
                if ref not in source_ids:
                    issues.append(
                        f"component {component_id} source data_ref {ref!r} does not exist"
                    )

    for kpi_id in sorted(kpi_ids):
        if kpi_ref_counts[kpi_id] != 1:
            issues.append(
                f"KPI {kpi_id} must be referenced exactly once, "
                f"got {kpi_ref_counts[kpi_id]}"
            )
    for chart_id in sorted(primary_chart_ids):
        if chart_ref_counts[chart_id] != 1:
            issues.append(
                f"primary chart {chart_id} must be referenced exactly once, "
                f"got {chart_ref_counts[chart_id]}"
            )

    issues.extend(_stateful_control_issues(components))
    return issues


def select_renderer(
    chart_spec: dict,
    data: dict,
    layout: dict | None,
) -> RendererMode:
    chart_contract = (chart_spec.get("dashboard_design") or {}).get("contract_version")
    data_contract = (data.get("meta") or {}).get("dashboard_profile_contract")

    if chart_contract != data_contract:
        raise ContractError(
            "chart/data renderer contract mismatch: "
            f"{chart_contract!r} != {data_contract!r}"
        )
    if chart_contract == "v5":
        if layout is None:
            raise ContractError("v5 contract requires dashboard_layout.json")
        if layout.get("layout_version") != 5:
            raise ContractError("v5 contract requires layout_version=5")
        return "v5"
    if layout is not None:
        raise ContractError("legacy/v4 contract cannot include dashboard_layout.json")
    return "v4" if chart_contract == "v4" else "legacy"
