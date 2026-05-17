import math
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.models import Tournament, Result

# COVID freeze: weeks excluded from the 104-week active count
FREEZE_START = date(2020, 2, 24)  # actual start of freeze (tournaments cancelled)
FREEZE_END   = date(2022, 3, 28)  # resumption of tournaments
FREEZE_WEEKS = (FREEZE_END - FREEZE_START).days // 7

# Aliases for backward compatibility
FREEZE_DEBUT = FREEZE_START
FREEZE_FIN   = FREEZE_END


def week_monday(d: date) -> date:
    """Return the Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def tournament_first_week(start_date: date) -> date:
    """Monday of week X+1: first week the tournament counts toward ranking."""
    return week_monday(start_date) + timedelta(weeks=1)


def active_weeks(start: date, target: date) -> int:
    """Count non-freeze weeks between start (inclusive) and target (inclusive)."""
    if target < start:
        return 0
    total = (target - start).days // 7 + 1

    # Freeze weeks overlapping [start, target]
    overlap_start = max(start, FREEZE_START)
    overlap_end   = min(target, FREEZE_END - timedelta(weeks=1))
    freeze = (overlap_end - overlap_start).days // 7 + 1 if overlap_end >= overlap_start else 0

    return total - freeze


def contribution(tournament_start: date, target_week: date) -> float:
    """
    Weight of a tournament for a given target week (a Monday).
    Based on the number of active (non-freeze) weeks since the tournament's first week.
    The freeze extends tournament lifetime (freeze weeks don't count).
    - Active weeks 1-52  : 1.0
    - Active weeks 53-104: 0.5
    - Beyond 104         : 0.0
    """
    first_week = tournament_first_week(tournament_start)

    if target_week < first_week:
        return 0.0

    n = active_weeks(first_week, target_week)
    if n <= 52:
        return 1.0
    if n <= 104:
        return 0.5
    return 0.0


def active_tournaments(db: Session, target_week: date, rules: str):
    """Return [(tournament, contribution)] for all tournaments active at target_week."""
    # Wide lower bound: 104 active weeks + max freeze weeks
    lower_bound = target_week - timedelta(weeks=104 + FREEZE_WEEKS)

    tournaments = (
        db.query(Tournament)
        .filter(
            Tournament.rules == rules,
            Tournament.tournament_type.notin_(["wmc", "wrc"]),
            Tournament.ema_id.isnot(None),
            Tournament.start_date >= lower_bound,
            Tournament.start_date != date(1900, 1, 1),
        )
        .all()
    )

    return [
        (t, c) for t in tournaments
        if (c := contribution(t.start_date, target_week)) > 0
    ]


def _part_a_count(n: int) -> int:
    """Number of tournaments retained for Part A: 5 + ceil(80% of the remainder)."""
    return 5 + math.ceil(0.8 * max(0, n - 5))


def _weighted_average(entries: list, missing: int) -> float:
    """
    Weighted average over entries = [(ranking, weight)] with `missing`
    virtual tournaments (ranking=0, weight=1) added to the denominator.
    """
    numerator   = sum(r * w for r, w in entries)
    denominator = sum(w for _, w in entries) + missing
    return numerator / denominator if denominator > 0 else 0.0


def _player_results(db, player_id: str, actives: dict):
    """Return results for a player in the active tournaments."""
    return (
        db.query(Result)
        .filter(
            Result.player_id == player_id,
            Result.tournament_id.in_(actives.keys()),
        )
        .all()
    )


def _player_score(results: list, actives: dict) -> float:
    """Compute player score from results and pre-loaded active tournaments dict."""
    n    = len(results)
    keep = _part_a_count(n)

    def weight(r): return actives[r.tournament_id][0].coefficient * actives[r.tournament_id][1]
    def date_of(r): return actives[r.tournament_id][0].start_date

    # Part A: on equal ranking, prefer most recent (date DESC)
    top_a = sorted(results, key=lambda r: (-r.ranking, -date_of(r).toordinal()))
    # Part B: on equal ranking, prefer highest weight (weight DESC)
    top_b = sorted(results, key=lambda r: (-r.ranking, -weight(r)))

    def entries(subset):
        return [(r.ranking, actives[r.tournament_id][0].coefficient * actives[r.tournament_id][1])
                for r in subset]

    part_a = _weighted_average(entries(top_a[:keep]), max(0, keep - n))
    part_b = _weighted_average(entries(top_b[:4]),    max(0, 4 - n))
    return 0.5 * part_a + 0.5 * part_b


def compute_score(db: Session, player_id: str, target_week: date, rules: str) -> float | None:
    """
    Final score = 0.5 * Part A + 0.5 * Part B.
    Returns None if the player has fewer than 2 active tournaments.
    """
    actives = {t.id: (t, c) for t, c in active_tournaments(db, target_week, rules)}
    results = _player_results(db, player_id, actives)
    if len(results) < 2:
        return None
    return _player_score(results, actives)


def ranking(db: Session, target_week: date, rules: str) -> list[dict]:
    """
    Return the full ranking for a given week and discipline.
    Only players with ≥2 active tournaments appear.
    Active tournaments are computed once.
    """
    from sqlalchemy import func

    actives = {t.id: (t, c) for t, c in active_tournaments(db, target_week, rules)}
    if not actives:
        return []

    # Eligible players in a single SQL query
    eligible = (
        db.query(Result.player_id)
        .filter(Result.tournament_id.in_(actives.keys()))
        .group_by(Result.player_id)
        .having(func.count(Result.tournament_id) >= 2)
        .all()
    )
    player_ids = [row[0] for row in eligible]

    # Load all active results in a single query
    all_results = (
        db.query(Result)
        .filter(
            Result.player_id.in_(player_ids),
            Result.tournament_id.in_(actives.keys()),
        )
        .all()
    )

    # Group by player
    by_player: dict[str, list] = {pid: [] for pid in player_ids}
    for r in all_results:
        by_player[r.player_id].append(r)

    # Compute scores and podiums
    scores = []
    for player_id, results in by_player.items():
        score = _player_score(results, actives)
        scores.append({
            "player_id":      player_id,
            "score":          score,
            "nb_tournaments": len(results),
            "nb_gold":        sum(1 for r in results if r.position == 1),
            "nb_silver":      sum(1 for r in results if r.position == 2),
            "nb_bronze":      sum(1 for r in results if r.position == 3),
        })

    # Sort: score DESC, then EMA ID ASC for exact ties
    scores.sort(key=lambda x: (-x["score"], x["player_id"]))
    for i, s in enumerate(scores):
        s["position"] = i + 1

    return scores


def ema_points(position: int, nb_players: int) -> int:
    """
    EMA points for a player given their position in a tournament.
    Formula: EMA = (NB - POS) / (NB - 1) * 1000, rounded to integer.
    1st → 1000, last → 0. Returns 0 if nb_players <= 1.
    """
    if nb_players <= 1:
        return 0
    return round((nb_players - position) / (nb_players - 1) * 1000)


# Aliases for backward compatibility
lundi_semaine         = week_monday
semaine_debut_tournoi = tournament_first_week
semaines_actives      = active_weeks
tournois_actifs       = active_tournaments
calcul_score          = compute_score
classement            = ranking
points_ema_tournoi    = ema_points
_nb_tournois_part_a   = _part_a_count
_moyenne_ponderee     = _weighted_average
_resultats_actifs     = _player_results
_score_pour_joueur    = _player_score
