#!/usr/bin/env python3
"""
Prepare a primary API source plan from the user's request.

This helper does not call the API. It turns an API URL mentioned in the request
into a manifest that connect can use to smoke-test, paginate, and snapshot the
API into runs/<run-id>/input/ before analysis.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "data-insight-kit.source_api_manifest.v1"
API_TERMS = (
    "api",
    "openapi",
    "servicekey",
    "공공데이터",
    "열린데이터",
    "데이터.go.kr",
    "data.go.kr",
)
URL_RE = re.compile(r"https?://[^\s'\"<>]+")
DEFAULT_KEY_ENV_CANDIDATES = [
    "PUBLIC_DATA_API_KEY",
    "DATA_GO_KR_SERVICE_KEY",
    "SEOUL_OPEN_API_KEY",
    "SERVICE_KEY",
]


def find_urls(text: str) -> list[str]:
    urls = []
    for match in URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,)]}")
        if url not in urls:
            urls.append(url)
    return urls


def request_has_api(text: str) -> bool:
    lowered = (text or "").lower()
    return bool(find_urls(text)) and any(term.lower() in lowered for term in API_TERMS)


def provider_for(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if "data.go.kr" in host:
        return "data.go.kr"
    if "seoul.go.kr" in host:
        return "seoul_open_data"
    return host or None


def build_manifest(run_id: str, user_request: str) -> dict[str, Any] | None:
    urls = find_urls(user_request)
    if not urls or not request_has_api(user_request):
        return None
    request_url = urls[0]
    provider = provider_for(request_url)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": "planned",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "adapter": "primary_api",
            "request_url": request_url,
            "provider": provider,
            "dataset_name": None,
            "endpoint_url": None,
            "method": "GET",
        },
        "auth": {
            "required": "unknown",
            "key_env_candidates": DEFAULT_KEY_ENV_CANDIDATES,
            "secret_material_stored": False,
        },
        "acquisition": {
            "method": "api_snapshot",
            "smoke_test_required": True,
            "pagination_checked": False,
            "pagination": "unknown",
            "page_count": None,
            "collected_row_count": None,
            "snapshot_required": True,
            "preferred_snapshot_format": "parquet",
            "output_dir": f"runs/{run_id}/input",
        },
        "snapshot": {
            "path": None,
            "format": None,
            "row_count": None,
            "columns": [],
            "fetched_at": None,
        },
        "lineage": {
            "source_ref": "primary_api_snapshot",
            "manifest_paths": [
                f"runs/{run_id}/input/source_api_manifest.json",
                f"runs/{run_id}/source_api_manifest.json",
            ],
        },
        "limitations": [
            "This manifest is a collection plan, not collected data.",
            "connect must verify the endpoint, authentication, pagination, row count, and columns before analysis.",
            "API keys or service keys must be read from environment/.env only and must not be written to outputs.",
        ],
        "next_actions": [
            "Open the source page or endpoint documentation.",
            "Identify the actual data endpoint and serviceKey parameter name.",
            "Run a one-page smoke test without printing the key.",
            "Confirm pagination and collect the bounded snapshot into runs/<run-id>/input/.",
            "Update this manifest with snapshot.path, row_count, columns, fetched_at, and pagination metadata.",
        ],
    }


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def write_manifest(run: Path, manifest: dict[str, Any]) -> tuple[Path, Path]:
    input_path = run / "input" / "source_api_manifest.json"
    root_path = run / "source_api_manifest.json"
    for path in (input_path, root_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return input_path, root_path


def print_prompt_block(run_id: str, run: Path) -> int:
    manifest = load_json(run / "input" / "source_api_manifest.json") or load_json(run / "source_api_manifest.json")
    if not manifest:
        return 0
    source = manifest.get("source") or {}
    acquisition = manifest.get("acquisition") or {}
    snapshot = manifest.get("snapshot") or {}
    print("[primary API source]")
    print(f"- manifest: runs/{run_id}/input/source_api_manifest.json")
    print(f"- request_url: {source.get('request_url')}")
    print(f"- provider: {source.get('provider')}")
    print(f"- status: {manifest.get('status')}")
    print(f"- snapshot_path: {snapshot.get('path')}")
    print(f"- pagination_checked: {acquisition.get('pagination_checked')}")
    print("- connect must use this API as the primary source unless the user explicitly chose another source.")
    print("- Do not silently fall back to connectors/.env DuckDB only because it exists.")
    print("- Before explore, collect or materialize a bounded snapshot under runs/<run-id>/input/ and update this manifest.")
    print("- If endpoint/auth/quota/pagination is blocked, stop as a source blocker instead of fabricating data.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare primary API source manifest.")
    parser.add_argument("run_id")
    parser.add_argument("--user-request", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--print-prompt-block", action="store_true")
    args = parser.parse_args()

    run = Path("runs") / args.run_id
    if args.print_prompt_block:
        return print_prompt_block(args.run_id, run)

    manifest = build_manifest(args.run_id, args.user_request)
    if args.check_only:
        print("1" if manifest else "0")
        return 0
    if manifest is None:
        return 0

    existing = load_json(run / "input" / "source_api_manifest.json")
    if existing and existing.get("status") in {"collected", "available"}:
        print(f"primary API source already collected: runs/{args.run_id}/input/source_api_manifest.json")
        return 0

    if args.dry_run:
        print("primary-api preflight: would write runs/%s/input/source_api_manifest.json" % args.run_id)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    input_path, root_path = write_manifest(run, manifest)
    print(f"primary API source planned: {input_path}")
    print(f"mirrored: {root_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
