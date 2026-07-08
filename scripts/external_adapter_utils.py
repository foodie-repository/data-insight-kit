#!/usr/bin/env python3
"""
Reusable helpers for data-insight-kit external context adapters.

The helpers stay intentionally small. They formalize patterns that repeated
across several adapter smoke tests without turning any one domain run into core
pipeline logic.
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any


ADAPTER_REGISTRY: dict[str, dict[str, Any]] = {
    "population": {
        "metric_layers": ("demand", "context", "coverage"),
        "meaning": "population, account, user, household, or organization count proxies",
        "allowed_uses": ("scale-normalized density", "size-context comparison"),
        "prohibited_interpretations": ("confirmed demand", "confirmed performance", "recommendation"),
    },
    "foot_traffic": {
        "metric_layers": ("demand", "context", "coverage"),
        "meaning": "visit, activity, usage, traffic, or dwell proxies",
        "allowed_uses": ("activity context", "time-of-day or channel comparison"),
        "prohibited_interpretations": ("purchase conversion", "profitability", "performance causality"),
    },
    "rent": {
        "metric_layers": ("cost", "context", "coverage"),
        "meaning": "cost, price, fee, rent, vacancy, or barrier proxies",
        "allowed_uses": ("cost pressure", "constraint context"),
        "prohibited_interpretations": ("good candidate because cost is low", "profitability"),
    },
    "sales": {
        "metric_layers": ("performance", "context", "coverage"),
        "meaning": "sales, spend, transaction, conversion, or outcome proxies",
        "allowed_uses": ("performance proxy", "outcome-per-unit comparison"),
        "prohibited_interpretations": ("profitability", "success probability", "causality"),
    },
    "business_dynamics": {
        "metric_layers": ("context", "coverage"),
        "meaning": "start, end, churn, survival, and status-change proxies",
        "allowed_uses": ("stability context", "exit-risk context", "turnover risk"),
        "prohibited_interpretations": ("recommendation", "success probability", "profitability"),
    },
    "area": {
        "metric_layers": ("spatial", "context", "coverage"),
        "meaning": "area, radius, grid, or spatial denominator proxies",
        "allowed_uses": ("density normalization", "spatial scale correction"),
        "prohibited_interpretations": ("true activity radius without validation",),
    },
    "competition": {
        "metric_layers": ("competition", "context", "coverage"),
        "meaning": "same-category entity, provider, brand, or supply competition proxies",
        "allowed_uses": ("competition intensity", "supply structure comparison"),
        "prohibited_interpretations": ("failure certainty",),
    },
    "mobility": {
        "metric_layers": ("spatial", "context", "coverage"),
        "meaning": "station, bus stop, travel-time, or accessibility proxies",
        "allowed_uses": ("accessibility context", "mobility-supported screening"),
        "prohibited_interpretations": ("performance causality",),
    },
    "custom": {
        "metric_layers": ("demand", "cost", "performance", "spatial", "competition", "context", "coverage"),
        "meaning": "one-off adapter category for new external context before category promotion",
        "allowed_uses": ("declared adapter-specific use only",),
        "prohibited_interpretations": ("undeclared category semantics",),
    },
}

CATEGORY_ALLOWED_METRIC_LAYERS: dict[str, set[str]] = {
    category: set(spec["metric_layers"]) for category, spec in ADAPTER_REGISTRY.items()
}


def metric(source_ref: str, transform: str, aggregation: str = "none") -> dict[str, str]:
    """Create the dashboard_data metric seed used by KPIs and chart series."""
    return {"source_ref": source_ref, "transform": transform, "aggregation": aggregation}


def coverage_audit(
    *,
    grain_count: int,
    matched_count: int,
    null_count: int | None = None,
    null_rate: float | None = None,
    precision: int = 6,
) -> dict[str, float | int]:
    """Return a manifest-compatible coverage object with defensive checks."""
    if grain_count < 0 or matched_count < 0:
        raise ValueError("grain_count and matched_count must be non-negative")
    if matched_count > grain_count:
        raise ValueError("matched_count cannot exceed grain_count")
    if null_count is not None and null_count < 0:
        raise ValueError("null_count must be non-negative")

    match_rate = matched_count / grain_count if grain_count else 0.0
    if null_rate is None:
        if null_count is None:
            null_count = grain_count - matched_count
        null_rate = null_count / grain_count if grain_count else 0.0
    if not 0 <= null_rate <= 1:
        raise ValueError("null_rate must be between 0 and 1")

    return {
        "grain_count": int(grain_count),
        "matched_count": int(matched_count),
        "match_rate": round(float(match_rate), precision),
        "null_rate": round(float(null_rate), precision),
    }


def expected_metric_layers(category: str) -> tuple[str, ...]:
    """Return allowed metric layers for an adapter category."""
    return tuple(sorted(CATEGORY_ALLOWED_METRIC_LAYERS.get(category, CATEGORY_ALLOWED_METRIC_LAYERS["custom"])))


def metric_layer_is_allowed(category: str, metric_layer: str) -> bool:
    """Check whether a field metric_layer matches the adapter category contract."""
    return metric_layer in CATEGORY_ALLOWED_METRIC_LAYERS.get(category, CATEGORY_ALLOWED_METRIC_LAYERS["custom"])


def validate_adapter_metric_layers(adapter: Mapping[str, Any]) -> list[str]:
    """Return human-readable layer contract errors for one adapter manifest item."""
    category = str(adapter.get("category") or "custom")
    errors: list[str] = []
    for field in adapter.get("fields") or []:
        if not isinstance(field, Mapping):
            continue
        metric_layer = str(field.get("metric_layer") or "")
        if metric_layer and not metric_layer_is_allowed(category, metric_layer):
            allowed = ", ".join(expected_metric_layers(category))
            errors.append(
                f"adapter '{adapter.get('id', '<unknown>')}' category={category} "
                f"does not allow metric_layer={metric_layer}; allowed: {allowed}"
            )
    return errors


def make_manifest(
    *,
    run_id: str,
    adapters: Sequence[Mapping[str, Any]],
    status: str = "available",
    objective: str | None = None,
) -> dict[str, Any]:
    """Create a top-level external_denominator_manifest object."""
    manifest: dict[str, Any] = {
        "schema_version": "data-insight-kit.external_denominator_manifest.v1",
        "run_id": run_id,
        "status": status,
        "adapters": [dict(adapter) for adapter in adapters],
    }
    if objective is not None:
        manifest["objective"] = objective
    return manifest


def write_json(path: pathlib.Path | str, payload: Mapping[str, Any]) -> pathlib.Path:
    """Write compact, deterministic UTF-8 JSON and return the written path."""
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return out


def write_external_manifest(run_dir: pathlib.Path | str, manifest: Mapping[str, Any]) -> tuple[pathlib.Path, pathlib.Path]:
    """
    Write the canonical manifest to both supported run locations.

    Returns (input_manifest_path, run_manifest_path).
    """
    run_path = pathlib.Path(run_dir)
    input_manifest = write_json(run_path / "input" / "external_denominator_manifest.json", manifest)
    run_manifest = write_json(run_path / "external_denominators.json", manifest)
    return input_manifest, run_manifest


def fetch_paged_json(
    *,
    url_builder: Callable[[int, int], str],
    rows_extractor: Callable[[Mapping[str, Any]], Iterable[Mapping[str, Any]]],
    total_extractor: Callable[[Mapping[str, Any]], int | None] | None = None,
    start_index: int = 1,
    page_size: int = 1000,
    max_pages: int | None = None,
    timeout: int = 30,
    headers: Mapping[str, str] | None = None,
    sleep_seconds: float = 0.0,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    """
    Collect a simple start/end-index JSON API with pagination metadata.

    The helper is source-agnostic: callers provide the URL builder and the JSON
    payload extractors. It does not know about Seoul Open Data or any other
    provider-specific schema.
    """
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if start_index <= 0:
        raise ValueError("start_index must be positive")
    if max_pages is not None and max_pages <= 0:
        raise ValueError("max_pages must be positive when provided")

    rows: list[Mapping[str, Any]] = []
    page_count = 0
    expected_total: int | None = None
    current_start = start_index

    while True:
        current_end = current_start + page_size - 1
        request = urllib.request.Request(url_builder(current_start, current_end), headers=dict(headers or {}))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        page_count += 1
        page_rows = list(rows_extractor(payload) or [])
        rows.extend(page_rows)

        if expected_total is None and total_extractor is not None:
            expected_total = total_extractor(payload)

        if not page_rows:
            break
        if expected_total is not None and len(rows) >= expected_total:
            break
        if len(page_rows) < page_size:
            break
        if max_pages is not None and page_count >= max_pages:
            break

        current_start += page_size
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    meta = {
        "method": "paged_api",
        "pagination_checked": True,
        "page_count": page_count,
        "collected_row_count": len(rows),
        "expected_total": expected_total,
        "page_size": page_size,
    }
    return rows, meta


def signed_rank_shift(baseline_rank: int | float | None, adjusted_rank: int | float | None) -> int | None:
    """Calculate rank shift as signed integer: baseline rank minus adjusted rank."""
    if baseline_rank is None or adjusted_rank is None:
        return None
    return int(baseline_rank) - int(adjusted_rank)


def signed_rank_shift_expr(baseline_rank_col: str, adjusted_rank_col: str, alias: str = "rank_shift"):
    """Return a Polars expression that prevents unsigned rank subtraction overflow."""
    import polars as pl

    return (pl.col(baseline_rank_col).cast(pl.Int64) - pl.col(adjusted_rank_col).cast(pl.Int64)).alias(alias)


def add_signed_rank_shift(frame, baseline_rank_col: str, adjusted_rank_col: str, alias: str = "rank_shift"):
    """Add a signed rank-shift column to a Polars DataFrame or LazyFrame."""
    return frame.with_columns(signed_rank_shift_expr(baseline_rank_col, adjusted_rank_col, alias))


__all__ = [
    "ADAPTER_REGISTRY",
    "CATEGORY_ALLOWED_METRIC_LAYERS",
    "add_signed_rank_shift",
    "coverage_audit",
    "expected_metric_layers",
    "fetch_paged_json",
    "make_manifest",
    "metric",
    "metric_layer_is_allowed",
    "signed_rank_shift",
    "signed_rank_shift_expr",
    "validate_adapter_metric_layers",
    "write_external_manifest",
    "write_json",
]
