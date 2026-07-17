#!/usr/bin/env python3
"""Compile an approved dashboard freeform v5 layout."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


KIT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT_ROOT))

from dashboard_v5.compiler import compile_dashboard  # noqa: E402
from dashboard_v5.contract import ContractError  # noqa: E402


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chart-spec", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        compile_dashboard(
            args.chart_spec,
            args.layout,
            args.data,
            output_path=args.output,
            kit_root=KIT_ROOT,
        )
    except (ContractError, OSError, ValueError) as exc:
        print(f"v5 compile blocked: {exc}", file=sys.stderr)
        return 2

    print(f"dashboard: {_display_path(args.output)}")
    print(
        "manifest: "
        f"{_display_path(args.output.parent / 'dashboard_build_manifest.json')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
