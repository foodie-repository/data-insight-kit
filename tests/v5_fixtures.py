"""Small, schema-shaped fixtures shared by dashboard freeform v5 tests."""

from __future__ import annotations

from copy import deepcopy


def _placement(
    order: int,
    span: int = 12,
    height: str = "auto",
    column_start: int = 1,
) -> dict:
    return {
        "desktop": {
            "order": order,
            "column_start": column_start,
            "span": span,
            "height": height,
        },
        "mobile": {"order": order, "span": 12, "height": height},
    }


def minimal_layout_v5() -> dict:
    return {
        "schema_version": "data-insight-kit.dashboard_layout.v1",
        "run_id": "v5-fixture",
        "layout_version": 5,
        "revision": 1,
        "generated_at": "2026-07-14T00:00:00Z",
        "profile_purpose": "analyst_workspace",
        "design_rationale": {
            "primary_question": "어느 항목이 큰가",
            "hierarchy_reason": "비교 차트를 가장 크게 본다",
            "mobile_reading_order_reason": "요약 뒤에 근거를 읽는다",
        },
        "grid": {"columns": 12, "gap": "md", "max_width": "wide"},
        "components": [
            {
                "id": "header",
                "kind": "header",
                "role": "navigation",
                "renderer": "svg_css",
                "data_refs": ["dashboard_data.meta"],
                "placement": _placement(1),
                "interactions": [],
                "render_options": {},
            },
            {
                "id": "kpis",
                "kind": "kpi_group",
                "role": "summary",
                "renderer": "svg_css",
                "data_refs": ["k1"],
                "placement": _placement(2),
                "interactions": [],
                "render_options": {},
            },
            {
                "id": "hero-chart",
                "kind": "chart",
                "role": "hero",
                "renderer": "echarts",
                "data_refs": ["c1"],
                "placement": _placement(3, 8, "xl"),
                "interactions": ["tooltip"],
                "render_options": {
                    "orientation": "vertical",
                    "legend": "none",
                    "label_density": "standard",
                },
            },
            {
                "id": "insight",
                "kind": "insight",
                "role": "support",
                "renderer": "svg_css",
                "data_refs": ["p1"],
                "placement": _placement(4, 4, "xl", 9),
                "interactions": [],
                "render_options": {},
            },
            {
                "id": "source",
                "kind": "source_note",
                "role": "evidence",
                "renderer": "svg_css",
                "data_refs": ["src1"],
                "placement": _placement(5),
                "interactions": [],
                "render_options": {},
            },
        ],
    }


def minimal_layout_v51() -> dict:
    layout = deepcopy(minimal_layout_v5())
    layout["quality_contract_version"] = "v5.1"
    purposes = {
        "header": "context",
        "kpi_group": "summary",
        "chart": "primary_evidence",
        "insight": "diagnostic",
        "source_note": "provenance",
    }
    for component in layout["components"]:
        component["purpose"] = purposes[component["kind"]]
        component["decision_link"] = (
            None
            if component["kind"] in {"header", "source_note"}
            else "compare-items"
        )
        component["evidence_refs"] = {
            "header": ["dashboard_data.meta"],
            "kpi_group": ["count"],
            "chart": ["c1"],
            "insight": ["c1"],
            "source_note": ["src1"],
        }[component["kind"]]
        component["empty_behavior"] = "block"
    return layout


def minimal_chart_spec_v5() -> dict:
    return {
        "meta": {
            "run_id": "v5-fixture",
            "generated_at": "2026-07-14T00:00:00Z",
            "mode": "directed",
            "audience": "analyst",
            "domain": "test",
        },
        "semantic_profile_ref": "outputs/01_profile.md",
        "dashboard_design": {
            "selected_profile": "analyst_workspace",
            "density": "standard",
            "navigation": "none",
            "rationale": "비교 중심",
            "alternatives_considered": [],
            "contract_version": "v5",
        },
        "charts": [
            {
                "id": "c1",
                "question": "어느 항목이 큰가",
                "method": "ranking",
                "grain": {
                    "row_meaning": "항목별 집계",
                    "time_grain": None,
                    "entity_grain": "item",
                },
                "data_requirements": {
                    "measures": ["count"],
                    "dimensions": ["item"],
                    "time_columns": [],
                    "filters": [],
                    "sample_policy": None,
                },
                "calculation": {
                    "source_ref": "src1",
                    "sql": "SELECT item, count(*) AS count FROM source GROUP BY item",
                    "metric_definition": "항목별 건수",
                    "unit": "건",
                    "denominator": None,
                },
                "chart": {
                    "type": "bar",
                    "why_this_chart": "항목 크기 비교",
                    "encoding": {
                        "x": "item",
                        "y": "count",
                        "color": None,
                        "size": None,
                        "series": None,
                    },
                },
                "insight": {
                    "finding": "B가 크다",
                    "evidence": "20건",
                    "limit": "테스트 fixture",
                },
                "dashboard_mapping": {
                    "panel_id": "p1",
                    "chart_id": "c1",
                    "priority": 1,
                    "uses_kpi_ids": ["k1"],
                    "surface": "primary",
                },
            }
        ],
    }


def minimal_chart_spec_v51() -> dict:
    chart_spec = deepcopy(minimal_chart_spec_v5())
    chart_spec["quality_contract"] = {
        "version": "v5.1",
        "decision_brief": {
            "decision_id": "compare-items",
            "primary_audience": "analyst",
            "decision": "항목별 차이를 검토한다",
            "review_cadence": "one_off",
            "primary_question": "어느 항목이 큰가",
            "source_scope": "항목별 건수 집계",
            "freshness_anchor": "2026-07-14",
            "known_gaps": ["원인 자료는 포함하지 않음"],
        },
        "metrics": [
            {
                "metric_id": "count",
                "role": "hero",
                "decision_link": "compare-items",
                "definition": "항목별 행 수",
                "unit": "건",
                "denominator": None,
                "window": "2026-07-14 기준",
                "source_ref": "src1",
            }
        ],
    }
    chart_spec["charts"][0]["visual_contract"] = {
        "comparison_intent": "ranking",
        "family": "comparison",
        "variant": "bar",
        "data_sufficiency": {
            "status": "sufficient",
            "observed_points": 2,
            "observed_series": 1,
            "minimum_points": 2,
            "minimum_series": 1,
            "fallback_chart": None,
            "reason": "비교할 항목이 2개 있음",
        },
        "scale_policy": "zero_baseline",
        "label_strategy": "axis",
        "legend_strategy": "none",
        "palette_policy": {
            "mode": "single_measure",
            "max_color_roots": 1,
            "rationale": "동일한 측정값의 항목별 비교",
        },
        "non_color_channels": ["label", "order"],
        "mobile_strategy": "reflow",
        "copy_context": {
            "title_mode": "descriptive",
            "scope_label": "전체 항목",
            "metric_label": "건수",
            "comparison_period": "2026-07-14 기준",
            "unit_label": "건",
        },
    }
    return chart_spec


def minimal_dashboard_data_v5() -> dict:
    return {
        "meta": {
            "title": "v5 fixture",
            "domain": "test",
            "audience": "analyst",
            "mode": "directed",
            "generated_at": "2026-07-14T00:00:00Z",
            "language": "ko",
            "row_count": 30,
            "dashboard_profile": "analyst_workspace",
            "dashboard_profile_contract": "v5",
        },
        "sources": [
            {
                "id": "src1",
                "type": "file",
                "ref": "input/source.csv",
                "snapshot_at": "2026-07-14T00:00:00Z",
                "sample_policy": {"sampled": False, "n": 30},
            }
        ],
        "kpis": [
            {
                "id": "k1",
                "label": "전체 건수",
                "value": 30,
                "unit": "건",
                "kind": "absolute",
                "status": "neutral",
            }
        ],
        "panels": [
            {
                "id": "p1",
                "title": "항목 비교",
                "story": {
                    "now": {"value": "B 20건", "desc": "가장 크다"},
                    "why": {"value": "차이 10건", "desc": "A보다 크다"},
                    "so": {"value": "B 우선", "desc": "먼저 확인한다"},
                    "act": {"value": "원자료 확인", "desc": "상세 근거를 본다"},
                },
                "charts": [
                    {
                        "id": "c1",
                        "type": "bar",
                        "title": "어느 항목이 큰가",
                        "desc": "항목별 건수",
                        "encoding": {
                            "x": {
                                "type": "category",
                                "label": "항목",
                                "values": ["A", "B"],
                            },
                            "series": [
                                {"label": "건수", "unit": "건", "values": [10, 20]}
                            ],
                            "stack": "none",
                        },
                    }
                ],
                "surface": "primary",
            }
        ],
    }


def minimal_dashboard_data_v51() -> dict:
    data = deepcopy(minimal_dashboard_data_v5())
    chart = data["panels"][0]["charts"][0]
    chart["title"] = "전체 항목의 건수 비교"
    chart["desc"] = "2026-07-14 기준 (단위: 건)"
    return data
