#!/usr/bin/env python3
"""Record the orchestrator's eyes-on review of all v5.1 QA screenshots."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys


KIT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT_ROOT))

from dashboard_v5.visual_review import (
    OBSERVATION_CATEGORIES,
    record_visual_review,
)  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--status", choices=("pass", "revise"), required=True)
    parser.add_argument("--reviewed-at", default=None)
    for category in OBSERVATION_CATEGORIES:
        parser.add_argument(
            f"--{category.replace('_', '-')}",
            dest=category,
            action="append",
            required=True,
        )
    args = parser.parse_args()

    reviewed_at = args.reviewed_at or datetime.now(timezone.utc).isoformat()
    observations = {
        category: getattr(args, category) for category in OBSERVATION_CATEGORIES
    }
    record = record_visual_review(
        args.output_dir,
        status=args.status,
        observations=observations,
        reviewer_role="orchestrator",
        reviewed_at=reviewed_at,
    )
    print(
        f"visual review recorded: {args.output_dir / 'visual_review.json'} "
        f"({record['status']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
