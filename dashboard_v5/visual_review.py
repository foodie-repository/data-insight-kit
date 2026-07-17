"""Run-local eyes-on review record for v5.1 dashboard screenshots."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "data-insight-kit.visual-review.v1"
OBSERVATION_CATEGORIES = (
    "copy_clarity",
    "information_hierarchy",
    "color_meaning",
    "scale_integrity",
    "labels_legends",
    "spacing_density",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review_path(output_dir: Path) -> Path:
    return Path(output_dir) / "visual_review.json"


def _screenshot_state(
    output_dir: Path, viewports: Mapping[str, Mapping[str, int]]
) -> dict[str, dict[str, Any]]:
    output_dir = Path(output_dir)
    result: dict[str, dict[str, Any]] = {}
    for name in viewports:
        filename = f"qa_render_{name}.png"
        path = output_dir / filename
        result[name] = {
            "path": filename,
            "sha256": _sha256(path) if path.is_file() else None,
            "inspected": False,
        }
    return result


def _write_record(output_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    _review_path(output_dir).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return record


def _hashes_match(
    record: dict[str, Any],
    output_dir: Path,
    viewports: Mapping[str, Mapping[str, int]],
) -> bool:
    screenshots = record.get("screenshots") or {}
    current = _screenshot_state(output_dir, viewports)
    return all(
        isinstance(screenshots.get(name), dict)
        and screenshots[name].get("path") == current[name]["path"]
        and screenshots[name].get("sha256") is not None
        and screenshots[name].get("sha256") == current[name]["sha256"]
        for name in viewports
    )


def ensure_visual_review_draft(
    output_dir: Path,
    viewports: Mapping[str, Mapping[str, int]],
) -> dict[str, Any]:
    """Create a fail-closed draft unless a reviewed record still matches the renders."""

    output_dir = Path(output_dir)
    path = _review_path(output_dir)
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = None
        if (
            isinstance(existing, dict)
            and existing.get("reviewed_at")
            and _hashes_match(existing, output_dir, viewports)
        ):
            return existing

    draft = {
        "schema_version": SCHEMA_VERSION,
        "reviewer_role": "orchestrator",
        "status": "revise",
        "reviewed_at": None,
        "screenshots": _screenshot_state(output_dir, viewports),
        "observations": {category: [] for category in OBSERVATION_CATEGORIES},
    }
    return _write_record(output_dir, draft)


def record_visual_review(
    output_dir: Path,
    *,
    status: str,
    observations: Mapping[str, list[str]],
    reviewer_role: str,
    reviewed_at: str,
) -> dict[str, Any]:
    """Record an actual orchestrator inspection against the current screenshot hashes."""

    if status not in {"pass", "revise"}:
        raise ValueError("visual review status must be pass or revise")
    if reviewer_role != "orchestrator":
        raise ValueError("visual review reviewer_role must be orchestrator")
    try:
        datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("visual review reviewed_at must be ISO-8601") from exc

    output_dir = Path(output_dir)
    draft_path = _review_path(output_dir)
    if not draft_path.is_file():
        raise ValueError("visual_review.json draft is missing")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    screenshots = draft.get("screenshots") or {}
    for name, screenshot in screenshots.items():
        path = output_dir / str(screenshot.get("path") or "")
        if not path.is_file():
            raise ValueError(f"visual review screenshot missing: {path.name or name}")
        screenshot["sha256"] = _sha256(path)
        screenshot["inspected"] = True

    normalized_observations: dict[str, list[str]] = {}
    for category in OBSERVATION_CATEGORIES:
        values = observations.get(category)
        if not isinstance(values, list) or not values or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise ValueError(
                f"visual review observation is required for {category}"
            )
        normalized_observations[category] = [value.strip() for value in values]

    record = {
        "schema_version": SCHEMA_VERSION,
        "reviewer_role": reviewer_role,
        "status": status,
        "reviewed_at": reviewed_at,
        "screenshots": screenshots,
        "observations": normalized_observations,
    }
    return _write_record(output_dir, record)


def validate_visual_review(
    record: dict[str, Any],
    output_dir: Path,
    viewports: Mapping[str, Mapping[str, int]],
) -> list[str]:
    """Return fail-closed record, inspection, and screenshot-integrity issues."""

    issues: list[str] = []
    output_dir = Path(output_dir)
    if record.get("schema_version") != SCHEMA_VERSION:
        issues.append("visual review schema_version mismatch")
    if record.get("reviewer_role") != "orchestrator":
        issues.append("visual review reviewer_role must be orchestrator")
    if record.get("status") != "pass":
        issues.append("visual review is not complete or requests revision")
    reviewed_at = record.get("reviewed_at")
    if not isinstance(reviewed_at, str) or not reviewed_at:
        issues.append("visual review is not complete: reviewed_at missing")
    else:
        try:
            datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        except ValueError:
            issues.append("visual review reviewed_at is not ISO-8601")

    screenshots = record.get("screenshots") or {}
    for name in viewports:
        filename = f"qa_render_{name}.png"
        item = screenshots.get(name)
        if not isinstance(item, dict):
            issues.append(f"visual review screenshot entry missing: {filename}")
            continue
        if item.get("path") != filename:
            issues.append(f"visual review screenshot path mismatch: {filename}")
        path = output_dir / filename
        if not path.is_file():
            issues.append(f"visual review screenshot missing: {filename}")
        elif item.get("sha256") != _sha256(path):
            issues.append(f"visual review screenshot hash mismatch: {filename}")
        if item.get("inspected") is not True:
            issues.append(f"visual review screenshot not inspected: {filename}")

    observations = record.get("observations") or {}
    for category in OBSERVATION_CATEGORIES:
        values = observations.get(category)
        if not isinstance(values, list) or not values or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            issues.append(f"visual review observation missing: {category}")
    return issues
