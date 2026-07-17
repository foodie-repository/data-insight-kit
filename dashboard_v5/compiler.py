"""Deterministic compiler for approved dashboard freeform v5 contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dashboard_v5.contract import (
    ContractError,
    select_renderer,
    validate_layout,
    validate_v5_cross_contract,
)
from dashboard_v5.echarts_options import IDENTITY_COLORS, build_echarts_option


COMPILER_VERSION = "dashboard-v5.1"
PINNED_ECHARTS_VERSION = "6.1.0"
PINNED_ECHARTS_SHA256 = (
    "b66b25aeb4df84e33199dc21694014d336d222cbd9deb0e5a7c14bd6aa0d0fd0"
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_vendor_bundle(kit_root: Path) -> dict[str, Any]:
    vendor_root = Path(kit_root) / "templates" / "vendor"
    manifest = read_json(vendor_root / "manifest.json")
    bundle_path = vendor_root / "echarts.min.js"
    actual = sha256_file(bundle_path)
    if (
        manifest.get("version") != PINNED_ECHARTS_VERSION
        or manifest.get("sha256") != PINNED_ECHARTS_SHA256
        or actual != PINNED_ECHARTS_SHA256
    ):
        raise ContractError(
            "vendor checksum mismatch for pinned ECharts "
            f"{PINNED_ECHARTS_VERSION}: {actual}"
        )
    return manifest


def _visual_contracts_by_chart(chart_spec: dict[str, Any] | None) -> dict[str, dict]:
    if not chart_spec:
        return {}
    result: dict[str, dict] = {}
    for plan in chart_spec.get("charts") or []:
        if not isinstance(plan, dict) or not isinstance(
            plan.get("visual_contract"), dict
        ):
            continue
        mapping = plan.get("dashboard_mapping") or {}
        chart_id = mapping.get("chart_id") or plan.get("id")
        if chart_id:
            result[str(chart_id)] = plan["visual_contract"]
    return result


def _stable_identity_colors(
    data: dict[str, Any], visual_contracts: dict[str, dict]
) -> dict[str, str]:
    labels = sorted(
        {
            str(series.get("label") or "")
            for panel in data.get("panels") or []
            for chart in panel.get("charts") or []
            if (
                visual_contracts.get(str(chart.get("id")), {})
                .get("palette_policy", {})
                .get("mode")
                == "categorical_identity"
            )
            for series in (chart.get("encoding") or {}).get("series") or []
            if isinstance(series, dict) and series.get("label")
        }
    )
    return {
        label: IDENTITY_COLORS[index % len(IDENTITY_COLORS)]
        for index, label in enumerate(labels)
    }


def _derived_render_options(component: dict, visual: dict) -> dict[str, Any]:
    options = dict(component.get("render_options") or {})
    if visual.get("scale_policy") == "independent_panels" or (
        visual.get("variant") in {"line", "area"}
        and "panel" in (visual.get("non_color_channels") or [])
        and (visual.get("data_sufficiency") or {}).get("observed_series", 0) > 1
    ):
        options["series_layout"] = "stacked_panels"
    legend_strategy = visual.get("legend_strategy")
    if legend_strategy in {"none", "direct_labels"}:
        options["legend"] = "none"
    elif legend_strategy in {"top", "right", "bottom"}:
        options["legend"] = legend_strategy
    elif legend_strategy == "paginated":
        options["legend"] = "right"
    return options


def build_options_by_component(
    layout: dict[str, Any],
    data: dict[str, Any],
    chart_spec: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    charts = {
        chart["id"]: chart
        for panel in data["panels"]
        for chart in panel["charts"]
    }
    visual_contracts = _visual_contracts_by_chart(chart_spec)
    identity_colors = _stable_identity_colors(data, visual_contracts)
    result: dict[str, dict[str, Any]] = {}
    for component in layout["components"]:
        if component["kind"] != "chart":
            continue
        chart_id = str(component["data_refs"][0])
        chart = charts[chart_id]
        visual = visual_contracts.get(chart_id) or {}
        result[component["id"]] = build_echarts_option(
            chart,
            _derived_render_options(component, visual),
            component.get("interactions") or [],
            visual_contract=visual,
            identity_colors=identity_colors,
        )
    return result


def build_presentation_by_component(
    layout: dict[str, Any], chart_spec: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    visual_contracts = _visual_contracts_by_chart(chart_spec)
    result: dict[str, dict[str, Any]] = {}
    for component in layout.get("components") or []:
        presentation: dict[str, Any] = {
            "empty_behavior": component.get("empty_behavior"),
        }
        if component.get("kind") == "chart" and component.get("data_refs"):
            visual = visual_contracts.get(str(component["data_refs"][0])) or {}
            presentation.update(
                {
                    "mobile_strategy": visual.get("mobile_strategy"),
                    "label_strategy": visual.get("label_strategy"),
                    "legend_strategy": visual.get("legend_strategy"),
                    "scale_policy": visual.get("scale_policy"),
                }
            )
        result[str(component.get("id"))] = presentation
    return result


def _file_record(path: Path, display_path: str) -> dict[str, str]:
    return {"path": display_path, "sha256": sha256_file(path)}


def build_manifest(
    chart_spec_path: Path,
    layout_path: Path,
    data_path: Path,
    kit_root: Path,
    layout: dict[str, Any],
) -> dict[str, Any]:
    verify_vendor_bundle(kit_root)
    return {
        "compiler_version": COMPILER_VERSION,
        "layout_revision": layout["revision"],
        "inputs": {
            "chart_spec": _file_record(chart_spec_path, chart_spec_path.name),
            "dashboard_layout": _file_record(layout_path, layout_path.name),
            "dashboard_data": _file_record(data_path, data_path.name),
        },
        "template": _file_record(
            kit_root / "templates" / "dashboard_v5.html",
            "templates/dashboard_v5.html",
        ),
        "echarts_bundle": _file_record(
            kit_root / "templates" / "vendor" / "echarts.min.js",
            "templates/vendor/echarts.min.js",
        ),
    }


def _json_for_script(value: object) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def compile_dashboard(
    chart_spec_path: Path,
    layout_path: Path,
    data_path: Path,
    output_path: Path,
    kit_root: Path,
) -> dict[str, Any]:
    chart_spec_path = Path(chart_spec_path)
    layout_path = Path(layout_path)
    data_path = Path(data_path)
    output_path = Path(output_path)
    kit_root = Path(kit_root)

    chart_spec = read_json(chart_spec_path)
    layout = read_json(layout_path)
    data = read_json(data_path)
    if select_renderer(chart_spec, data, layout) != "v5":
        raise ContractError("render_dashboard_v5 only accepts the v5 contract")
    issues = validate_layout(layout) + validate_v5_cross_contract(
        chart_spec, layout, data
    )
    if issues:
        raise ContractError("; ".join(issues))

    verify_vendor_bundle(kit_root)
    options = build_options_by_component(layout, data, chart_spec)
    presentation = build_presentation_by_component(layout, chart_spec)
    template_path = kit_root / "templates" / "dashboard_v5.html"
    bundle_path = kit_root / "templates" / "vendor" / "echarts.min.js"
    template = template_path.read_text(encoding="utf-8")
    bundle = bundle_path.read_text(encoding="utf-8")
    rendered = (
        template.replace("{PLACE_ECHARTS_BUNDLE_HERE}", bundle)
        .replace("{PLACE_LAYOUT_HERE}", _json_for_script(layout))
        .replace("{PLACE_DATA_HERE}", _json_for_script(data))
        .replace("{PLACE_OPTIONS_HERE}", _json_for_script(options))
        .replace("{PLACE_PRESENTATION_HERE}", _json_for_script(presentation))
    )
    if "{PLACE_" in rendered:
        raise ContractError("v5 template placeholder remains")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    manifest = build_manifest(
        chart_spec_path, layout_path, data_path, kit_root, layout
    )
    manifest_path = output_path.parent / "dashboard_build_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
