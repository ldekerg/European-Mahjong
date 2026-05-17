"""
CLI for ranking history calculation.

Usage:
  python3 run_ranking_history.py                      # all weeks
  python3 run_ranking_history.py --from 2022-01-03    # from a specific date (Monday)
  python3 run_ranking_history.py --week 2026-04-27    # a single week
  python3 run_ranking_history.py --update             # missing weeks only
  python3 run_ranking_history.py --workers 8          # parallelise on N threads
  python3 run_ranking_history.py --rules RCR          # MCR, RCR, or all (default)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
from datetime import date

from app.database import SessionLocal
from app.ranking import week_monday
from app.ranking_history import (
    FIRST_WEEK,
    weeks_between,
    filter_active_weeks,
    missing_weeks,
    compute_weeks,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from",    dest="from_date", type=date.fromisoformat)
    parser.add_argument("--week",    type=date.fromisoformat)
    parser.add_argument("--update",  action="store_true")
    parser.add_argument("--rules",   choices=["MCR", "RCR", "all"], default="all")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    rules_list = ["MCR", "RCR"] if args.rules == "all" else [args.rules]

    for rules in rules_list:
        print(f"\n=== {rules} ===")

        db = SessionLocal()
        if args.week:
            weeks = [week_monday(args.week)]
        elif args.update:
            weeks = missing_weeks(db, rules)
        elif args.from_date:
            end = week_monday(date.today())
            weeks = filter_active_weeks(list(weeks_between(args.from_date, end)))
        else:
            end = week_monday(date.today())
            weeks = filter_active_weeks(list(weeks_between(FIRST_WEEK, end)))
        db.close()

        print(f"{len(weeks)} weeks to compute (workers={args.workers})")

        def progress(week, n, done, total):
            print(f"  {week}  {n:4} players  ({done}/{total})", flush=True)

        compute_weeks(weeks, rules, workers=args.workers, on_progress=progress)

    print("\nDone.")


if __name__ == "__main__":
    main()
