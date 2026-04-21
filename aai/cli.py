"""Command-line interface.

Usage:
  python -m aai.cli update [--queries N] [--min-confidence X]
  python -m aai.cli report
  python -m aai.cli list [--type divergence|hybridization]
  python -m aai.cli seed
  python -m aai.cli compute

The `update` command is what a cron job or GitHub Actions workflow should
invoke on a schedule.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .indices import compute_indices, interpret
from .report import render_dashboard
from .schema import CaseType
from .sources import ALL_QUERIES
from .storage import DEFAULT_DB_PATH, init_db, list_cases, upsert_case, write_snapshot


def cmd_update(args) -> int:
    # Lazy import so `list`, `seed`, `compute`, `report` work without anthropic installed.
    from .agent import run_discovery

    init_db()
    queries = ALL_QUERIES
    if args.queries and args.queries > 0:
        queries = queries[: args.queries]

    print(f"[update] running {len(queries)} discovery queries…", flush=True)
    new_cases = 0
    updated_cases = 0

    for sq in queries:
        print(f"[update]   query: {sq.label}  ({sq.target})", flush=True)
        try:
            found = run_discovery(sq)
        except Exception as e:
            print(f"[update]     ! error: {e}", file=sys.stderr)
            continue

        for case in found:
            if case.confidence < args.min_confidence:
                continue
            is_new = upsert_case(case)
            if is_new:
                new_cases += 1
            else:
                updated_cases += 1
            print(
                f"[update]     {'NEW' if is_new else 'upd'} "
                f"{case.case_type.value:<13s}  {case.artwork_title[:40]:<40s} "
                f"conf={case.confidence:.2f}",
                flush=True,
            )

    snap = compute_indices(window_days=args.window)
    write_snapshot(snap)
    print(f"[update] snapshot written: MWDRI={snap.money_weighted_dri} "
          f"HI={snap.hybridization_index} instability={snap.instability_share}")
    print(f"[update] new={new_cases} updated={updated_cases} total_div={snap.divergence_cases_total} "
          f"total_hyb={snap.hybridization_cases_total}")

    out = render_dashboard()
    print(f"[update] dashboard rendered: {out}")
    return 0


def cmd_compute(args) -> int:
    snap = compute_indices(window_days=args.window, min_confidence=args.min_confidence)
    write_snapshot(snap)
    print("=== Computed snapshot ===")
    print(snap.model_dump_json(indent=2))
    print()
    print("=== Triad reading ===")
    print(interpret(snap))
    return 0


def cmd_report(args) -> int:
    out = render_dashboard()
    print(f"Dashboard rendered: {out}")
    return 0


def cmd_list(args) -> int:
    ct = CaseType(args.type) if args.type else None
    cases = list_cases(case_type=ct, min_confidence=args.min_confidence)
    if not cases:
        print("(no cases)")
        return 0
    for c in cases:
        val = f"${c.estimated_value_usd:,.0f}" if c.estimated_value_usd else "—"
        kind = (c.resolution.value if c.resolution else
                c.hybridization_kind.value if c.hybridization_kind else "")
        print(
            f"{(c.event_date or c.discovered_at[:10]):<11s}  "
            f"{c.case_type.value:<13s}  {kind:<22s}  "
            f"{val:>14s}  {c.artwork_title[:40]:<40s}  conf={c.confidence:.2f}"
        )
    return 0


def cmd_seed(args) -> int:
    from .seed import seed_cases
    init_db()
    added = 0
    for case in seed_cases():
        if upsert_case(case):
            added += 1
    # Seed cases reference real historical events (Elimar 2023, Samson and
    # Delilah 2021). Use a wider window so the demo surfaces them.
    snap = compute_indices(window_days=2000)
    write_snapshot(snap)
    render_dashboard()
    print(f"Seeded {added} cases. Current (5yr window): "
          f"MWDRI={snap.money_weighted_dri} HI={snap.hybridization_index}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aai", description="Authentication Authority Index tracker.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pu = sub.add_parser("update", help="Run agentic discovery and refresh the indices.")
    pu.add_argument("--queries", type=int, default=0,
                    help="Limit to first N queries (0 = all). Useful for test runs.")
    pu.add_argument("--min-confidence", type=float, default=0.5,
                    help="Drop cases below this classifier confidence.")
    pu.add_argument("--window", type=int, default=365,
                    help="Window in days over which to compute the snapshot.")
    pu.set_defaults(func=cmd_update)

    pc = sub.add_parser("compute", help="Recompute indices from stored cases.")
    pc.add_argument("--window", type=int, default=365)
    pc.add_argument("--min-confidence", type=float, default=0.4)
    pc.set_defaults(func=cmd_compute)

    pr = sub.add_parser("report", help="Render the static HTML dashboard.")
    pr.set_defaults(func=cmd_report)

    pl = sub.add_parser("list", help="List stored cases.")
    pl.add_argument("--type", choices=["divergence", "hybridization"])
    pl.add_argument("--min-confidence", type=float, default=0.0)
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("seed", help="Populate with illustrative seed cases.")
    ps.set_defaults(func=cmd_seed)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
