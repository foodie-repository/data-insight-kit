#!/usr/bin/env python3
"""
Materialize a bounded remote Parquet projection into runs/<run-id>/input/.

This keeps remote or very large datasets out of the main pipeline contract:
the pipeline reads a local snapshot, while this script records the remote URI
and projection lineage in runs/<run-id>/source_snapshot.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import sys

import polars as pl


RANK_COL = "__vk_sample_rank"
STRATUM_N_COL = "__vk_stratum_n"
SAMPLE_N_COL = "__vk_sample_n"


def parse_columns(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def resolve_output(input_dir: pathlib.Path, output: str) -> pathlib.Path:
    out = (input_dir / output).resolve()
    root = input_dir.resolve()
    try:
        out.relative_to(root)
    except ValueError as exc:
        raise SystemExit("output must stay inside runs/<run-id>/input/") from exc
    if out.suffix.lower() != ".parquet":
        raise SystemExit("output must be a .parquet file")
    return out


def load_snapshot_manifest(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"snapshots": []}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("snapshots"), list):
        raise SystemExit(f"invalid snapshot manifest: {path}")
    return data


def is_rate_limit_error(exc: BaseException) -> bool:
    message = str(exc)
    return "429" in message or "Too Many Requests" in message


def remote_rate_limit_message() -> str:
    return (
        "remote source returned HTTP 429 Too Many Requests. "
        "For Hugging Face sources, wait before retrying or set HF_TOKEN/HUGGINGFACE_HUB_TOKEN "
        "in the local environment. For public rate-limited sources, use --candidate-limit "
        "with --stratify-by to avoid full-source stratification scans."
    )


def allocate_balanced_samples(counts_df: pl.DataFrame, limit: int) -> pl.DataFrame:
    if counts_df.is_empty():
        raise SystemExit("source is empty; cannot create a stratified snapshot")
    if limit < counts_df.height:
        raise SystemExit(
            f"--limit ({limit}) must be at least the number of strata ({counts_df.height})"
        )

    caps = [int(value) for value in counts_df[STRATUM_N_COL].to_list()]
    allocations = [1 for _ in caps]
    remaining = limit - len(allocations)
    remaining_caps = [cap - 1 for cap in caps]
    active = [idx for idx, cap in enumerate(remaining_caps) if cap > 0]

    while active and remaining > 0:
        per_active = max(1, math.ceil(remaining / len(active)))
        next_active: list[int] = []
        for idx in active:
            take = min(per_active, remaining_caps[idx], remaining)
            allocations[idx] += take
            remaining_caps[idx] -= take
            remaining -= take
            if remaining_caps[idx] > 0:
                next_active.append(idx)
            if remaining == 0:
                next_active.extend(active[active.index(idx) + 1 :])
                break
        active = [idx for idx in next_active if remaining_caps[idx] > 0]

    return counts_df.with_columns(pl.Series(SAMPLE_N_COL, allocations))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a bounded local Parquet snapshot from a remote Parquet URI."
    )
    parser.add_argument("run_id", help="data-insight-kit run id")
    parser.add_argument("uri", help="remote parquet URI, e.g. hf://.../*.parquet")
    parser.add_argument(
        "--columns",
        help="comma-separated projection. Required unless --all-columns is set.",
    )
    parser.add_argument(
        "--all-columns",
        action="store_true",
        help="explicitly snapshot all columns. Use only for known-small sources.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50_000,
        help="maximum rows to materialize, or target rows when --stratify-by is set. Must be positive. Default: 50000.",
    )
    parser.add_argument(
        "--stratify-by",
        help="comma-separated columns for balanced stratified sampling. Uses --limit as the target sample size.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        help=(
            "with --stratify-by, first limit the source to this many candidate rows "
            "and stratify within that bounded candidate pool. Useful for rate-limited remote sources."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="random seed used with --stratify-by. Default: 42.",
    )
    parser.add_argument(
        "--output",
        default="remote_snapshot.parquet",
        help="output file name under runs/<run-id>/input/. Default: remote_snapshot.parquet.",
    )
    parser.add_argument(
        "--source-id",
        help="lineage id in source_snapshot.json. Default: output file stem.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the output file and replace an existing snapshot entry with the same source id.",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit must be positive")
    columns = parse_columns(args.columns)
    if not columns and not args.all_columns:
        raise SystemExit("--columns is required unless --all-columns is set")
    if columns and args.all_columns:
        raise SystemExit("use either --columns or --all-columns, not both")
    strata = parse_columns(args.stratify_by)
    if args.candidate_limit is not None:
        if not strata:
            raise SystemExit("--candidate-limit requires --stratify-by")
        if args.candidate_limit <= 0:
            raise SystemExit("--candidate-limit must be positive")
        if args.candidate_limit < args.limit:
            raise SystemExit("--candidate-limit must be greater than or equal to --limit")

    root = pathlib.Path(__file__).resolve().parents[1]
    run_dir = root / "runs" / args.run_id
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    out = resolve_output(input_dir, args.output)
    if out.exists() and not args.force:
        raise SystemExit(f"output already exists: {out} (use --force to overwrite)")

    lf = pl.scan_parquet(args.uri)
    try:
        schema = lf.collect_schema()
    except Exception as exc:
        if is_rate_limit_error(exc):
            raise SystemExit(remote_rate_limit_message()) from exc
        raise
    available = list(schema.names())
    missing_strata = [col for col in strata if col not in available]
    if missing_strata:
        raise SystemExit(f"missing stratify columns in remote source: {', '.join(missing_strata)}")
    if columns:
        missing = [col for col in columns if col not in available]
        if missing:
            raise SystemExit(f"missing columns in remote source: {', '.join(missing)}")
        columns = columns + [col for col in strata if col not in columns]
        lf = lf.select(columns)
    else:
        columns = available

    if strata:
        sampling_frame = lf
        if args.candidate_limit is not None:
            sampling_frame = sampling_frame.limit(args.candidate_limit)
        try:
            counts_df = sampling_frame.group_by(strata).len(name=STRATUM_N_COL).collect()
        except Exception as exc:
            if is_rate_limit_error(exc):
                raise SystemExit(remote_rate_limit_message()) from exc
            raise
        allocation_df = allocate_balanced_samples(counts_df, args.limit)
        try:
            df = (
                sampling_frame.with_columns(
                    pl.int_range(pl.len()).shuffle(seed=args.seed).over(strata).alias(RANK_COL)
                )
                .join(allocation_df.drop(STRATUM_N_COL).lazy(), on=strata, how="inner")
                .filter(pl.col(RANK_COL) < pl.col(SAMPLE_N_COL))
                .drop(RANK_COL, SAMPLE_N_COL)
                .collect()
            )
        except Exception as exc:
            if is_rate_limit_error(exc):
                raise SystemExit(remote_rate_limit_message()) from exc
            raise
        strategy = "stratified_balanced_candidate" if args.candidate_limit else "stratified_balanced"
        sampling = {
            "strategy": strategy,
            "target_n": args.limit,
            "actual_n": df.height,
            "stratify_by": strata,
            "strata": counts_df.height,
            "seed": args.seed,
            "candidate_limit": args.candidate_limit,
            "sampling_frame": "candidate_prefix" if args.candidate_limit else "full_source",
            "min_sample_per_stratum": int(allocation_df[SAMPLE_N_COL].min()),
            "max_sample_per_stratum": int(allocation_df[SAMPLE_N_COL].max()),
        }
    else:
        try:
            df = lf.limit(args.limit).collect()
        except Exception as exc:
            if is_rate_limit_error(exc):
                raise SystemExit(remote_rate_limit_message()) from exc
            raise
        sampling = {
            "strategy": "prefix_limit",
            "limit": args.limit,
        }
    df.write_parquet(out)

    source_id = args.source_id or out.stem
    snapshot = {
        "id": source_id,
        "adapter": "remote_parquet",
        "ref": args.uri,
        "snapshot_at": dt.datetime.now().astimezone().isoformat(),
        "output": str(out.relative_to(run_dir)),
        "n": df.height,
        "columns": columns,
        "schema": {name: str(dtype) for name, dtype in df.schema.items()},
        "limit": args.limit,
        "sampling": sampling,
    }

    manifest_path = run_dir / "source_snapshot.json"
    manifest = load_snapshot_manifest(manifest_path)
    existing_ids = {item.get("id") for item in manifest["snapshots"]}
    if source_id in existing_ids and not args.force:
        raise SystemExit(f"snapshot id already exists: {source_id} (use --force to replace)")
    manifest["snapshots"] = [item for item in manifest["snapshots"] if item.get("id") != source_id]
    manifest["snapshots"].append(snapshot)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
