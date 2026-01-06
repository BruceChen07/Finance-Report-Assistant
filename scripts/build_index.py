from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.indexing.index_service import (
    build_or_update_index_for_job,
    default_index_config,
    query_index,
)


def _print_dict(d: dict[str, Any]) -> None:
    for k, v in d.items():
        print(f"{k}: {v}")


def cmd_build(args: argparse.Namespace) -> int:
    s = get_settings()
    job_dir = Path(args.job_dir) if args.job_dir else (
        s.output_root / args.job_id)

    if not job_dir.exists():
        print(f"[ERROR] job_dir not found: {job_dir}")
        return 2

    cfg = default_index_config()
    info = build_or_update_index_for_job(
        job_id=args.job_id,
        job_dir=job_dir,
        company_id=args.company_id,
        report_year=args.report_year,
        report_type=args.report_type,
        cfg=cfg,
    )

    print("[OK] index built/updated:")
    _print_dict(info)
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    cfg = default_index_config()

    results = query_index(
        question=args.question,
        top_k=args.top_k,
        company_id=args.company_id,
        report_year=args.report_year,
        report_type=args.report_type,
        cfg=cfg,
    )

    if not results:
        print("[INFO] no results.")
        return 0

    for i, r in enumerate(results, 1):
        print("=" * 80)
        print(f"[{i}] score={r['score']:.4f}")
        meta = r.get("metadata") or {}
        for k in ("company_id", "report_year", "report_type", "job_id", "markdown_path"):
            if k in meta:
                print(f"{k}: {meta[k]}")
        print("--- snippet ---")
        print(r.get("snippet", "").strip())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build/query financial report index.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_build = sub.add_parser(
        "build", help="Build or update index for a job_id.")
    ap_build.add_argument(
        "job_id", help="Job ID, e.g. 20260104_131936_2531fc5b")
    ap_build.add_argument("--job-dir", default=None,
                          help="Override job dir if not under FRA_OUTPUT_ROOT.")
    ap_build.add_argument("--company-id", default=None)
    ap_build.add_argument("--report-year", type=int, default=None)
    ap_build.add_argument("--report-type", default=None)

    ap_query = sub.add_parser("query", help="Query the index.")
    ap_query.add_argument("question", help="Question text")
    ap_query.add_argument("--top-k", type=int, default=8)
    ap_query.add_argument("--company-id", default=None)
    ap_query.add_argument("--report-year", type=int, default=None)
    ap_query.add_argument("--report-type", default=None)

    args = ap.parse_args()

    if args.cmd == "build":
        return cmd_build(args)
    if args.cmd == "query":
        return cmd_query(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
