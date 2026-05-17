"""
Business logic for calculating and storing weekly ranking history.
Can be called from a CLI script or from the FastAPI application.
"""

import os
import threading
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models import Base, RankingHistory
from app.ranking import ranking, week_monday, FREEZE_START, FREEZE_END

if os.getenv("DATABASE_URL"):
    Base.metadata.create_all(bind=engine)

if os.getenv("DATABASE_URL"):
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))

FIRST_WEEK = date(2005, 6, 27)  # Monday before the first known MCR tournament

_write_lock = threading.Lock()

# Alias for backward compatibility
PREMIERE_SEMAINE = FIRST_WEEK


def weeks_between(start: date, end: date):
    """Yield each Monday from start's week to end (inclusive)."""
    w = week_monday(start)
    while w <= end:
        yield w
        w += timedelta(weeks=1)


def filter_active_weeks(weeks: list[date]) -> list[date]:
    """Filter out weeks that fall within the COVID freeze period."""
    return [w for w in weeks if not (FREEZE_START <= w < FREEZE_END)]


def missing_weeks(db: Session, rules: str) -> list[date]:
    """Return all active weeks not yet stored in RankingHistory for the given rules."""
    existing = {row[0] for row in db.query(RankingHistory.week)
                .filter(RankingHistory.rules == rules).distinct().all()}
    end = week_monday(date.today())
    all_weeks = list(weeks_between(FIRST_WEEK, end))
    return [w for w in filter_active_weeks(all_weeks) if w not in existing]


def compute_week(week: date, rules: str) -> int:
    """Calculate and store ranking for one week. Returns number of ranked players."""
    db = SessionLocal()
    try:
        results = ranking(db, week, rules)
        if not results:
            return 0

        rows = [
            {
                "week":           week,
                "rules":          rules,
                "player_id":      r["player_id"],
                "position":       r["position"],
                "score":          r["score"],
                "nb_tournaments": r["nb_tournaments"],
                "nb_gold":        r["nb_gold"],
                "nb_silver":      r["nb_silver"],
                "nb_bronze":      r["nb_bronze"],
            }
            for r in results
        ]

        with _write_lock:
            for row in rows:
                stmt = insert(RankingHistory).values(**row).on_conflict_do_update(
                    index_elements=["week", "rules", "player_id"],
                    set_={
                        "position":       row["position"],
                        "score":          row["score"],
                        "nb_tournaments": row["nb_tournaments"],
                        "nb_gold":        row["nb_gold"],
                        "nb_silver":      row["nb_silver"],
                        "nb_bronze":      row["nb_bronze"],
                    },
                )
                db.execute(stmt)
            db.commit()

        return len(results)
    finally:
        db.close()


def compute_weeks(weeks: list[date], rules: str, workers: int = 4,
                  on_progress=None) -> None:
    """
    Calculate and store ranking for a list of weeks in parallel.
    on_progress(week, nb_players, done, total) — optional callback every 50 steps.
    """
    total = len(weeks)
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(compute_week, w, rules): w for w in weeks}
        for future in as_completed(futures):
            done += 1
            if on_progress and (done % 50 == 0 or done == total):
                on_progress(futures[future], future.result(), done, total)


# Aliases for backward compatibility
semaines_entre      = weeks_between
semaines_manquantes = missing_weeks
calculer_semaine    = compute_week
calculer_semaines   = compute_weeks
