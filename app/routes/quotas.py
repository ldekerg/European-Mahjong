import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import templates

router = APIRouter()

EMA_MEMBERS = [
    "AT", "BE", "CH", "CZ", "DE", "DK", "ES", "FI", "FR", "HU",
    "IE", "IT", "LV", "NL", "NO", "PL", "PT", "RO", "SE", "SK", "UA", "UK",
]

CONFIG_PATH = Path("data/quotas_config.json")


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _latest_week(db, rules: str) -> str:
    row = db.execute(
        text("SELECT MAX(week) FROM ranking_history WHERE rules = :r"),
        {"r": rules},
    ).fetchone()
    return row[0] if row else None


def _best_invited_players(db, rules: str) -> list[dict]:
    """Return up to 2 invited players: best EMA player in last OEMC and last WMC."""
    # tournament_type mapping per rules
    if rules == "MCR":
        types = [("oemc", "OEMC"), ("wmc", "WMC")]
    else:
        types = [("oerc", "ERMC"), ("wrc", "WRC")]

    invited = []
    for ttype, label in types:
        # Find last completed championship of this type
        row = db.execute(text("""
            SELECT t.id, t.name, t.start_date
            FROM tournaments t
            WHERE t.tournament_type = :tt AND t.start_date < :today
            ORDER BY t.start_date DESC LIMIT 1
        """), {"tt": ttype, "today": str(date.today())}).fetchone()

        if not row:
            continue
        tid, tname, tdate = row

        # Best EMA player (nationality in EMA_MEMBERS) by position
        placeholders = ",".join(f":m{i}" for i in range(len(EMA_MEMBERS)))
        params = {"tid": tid}
        params.update({f"m{i}": nat for i, nat in enumerate(EMA_MEMBERS)})
        prow = db.execute(text(f"""
            SELECT r.player_id, p.first_name, p.last_name, p.nationality, r.position
            FROM results r
            JOIN players p ON r.player_id = p.id
            WHERE r.tournament_id = :tid
              AND p.nationality IN ({placeholders})
            ORDER BY r.position ASC LIMIT 1
        """), params).fetchone()

        if prow:
            invited.append({
                "player_id": prow[0],
                "name": f"{prow[1]} {prow[2]}".strip(),
                "nationality": prow[3],
                "position": prow[4],
                "championship": tname,
                "championship_label": label,
                "year": str(tdate)[:4],
            })

    # Deduplicate: if same player won both, only 1 extra seat
    seen = set()
    unique = []
    for p in invited:
        if p["player_id"] not in seen:
            seen.add(p["player_id"])
            unique.append(p)
    return unique


def _compute_quotas(db, rules: str, week: str, t_ema: int) -> list[dict]:
    """Compute EMA quota per country for given rules/week/total EMA seats."""
    rows = db.execute(text("""
        SELECT p.nationality, rh.score
        FROM ranking_history rh
        JOIN players p ON rh.player_id = p.id
        WHERE rh.rules = :r AND rh.week = :w
          AND p.nationality NOT IN ('GUEST', '')
        ORDER BY p.nationality, rh.score DESC
    """), {"r": rules, "w": week}).fetchall()

    avg_global = db.execute(text(
        "SELECT AVG(score) FROM ranking_history WHERE rules=:r AND week=:w"
    ), {"r": rules, "w": week}).scalar() or 0

    by_country = defaultdict(list)
    for nat, score in rows:
        by_country[nat].append(score)

    countries = {}
    for nat in EMA_MEMBERS:
        scores = by_country.get(nat, [])
        top3 = (scores[:3] + [0, 0, 0])[:3]
        nb = len(scores)
        nb700 = sum(1 for s in scores if s > 700)
        nb_above_avg = sum(1 for s in scores if s > avg_global)
        countries[nat] = {
            "nb": nb, "nb700": nb700, "nb_above_avg": nb_above_avg,
            "team_score": sum(top3) / 3,
            "max_seats": max(1, nb_above_avg),
        }

    total_nb = sum(d["nb"] for d in countries.values())
    total_700 = sum(d["nb700"] for d in countries.values())

    # Country ranking (top-3 average)
    ranked = sorted(countries, key=lambda n: -countries[n]["team_score"])
    for i, nat in enumerate(ranked, 1):
        countries[nat]["country_rank"] = i

    # Part A
    for nat, d in countries.items():
        r = d["country_rank"]
        d["a1"] = 1 if r <= 3 else 0
        d["a2"] = 1
        d["a3"] = 1 if d["nb700"] > 0 else 0
        d["partA"] = d["a1"] + d["a2"] + d["a3"]

    sum_partA = sum(d["partA"] for d in countries.values())
    t_b = t_ema - sum_partA

    # Part B + cap before rounding
    for nat, d in countries.items():
        b1 = d["nb"] / total_nb if total_nb else 0
        b2 = d["nb700"] / total_700 if total_700 else 0
        b3 = (b1 + b2) / 2
        raw = d["partA"] + b3 * t_b
        d["quota_raw"] = min(raw, d["max_seats"])

    # Round to nearest, min 1
    quota = {nat: max(1, round(d["quota_raw"])) for nat, d in countries.items()}

    # Redistribute remainder by country rank
    remainder = t_ema - sum(quota.values())
    by_rank = sorted(EMA_MEMBERS, key=lambda n: countries[n]["country_rank"])
    if remainder > 0:
        for nat in by_rank:
            if remainder <= 0:
                break
            if quota[nat] < countries[nat]["max_seats"]:
                quota[nat] += 1
                remainder -= 1
    elif remainder < 0:
        for nat in reversed(by_rank):
            if remainder >= 0:
                break
            if quota[nat] > 1:
                quota[nat] -= 1
                remainder += 1

    result = []
    for nat in by_rank:
        d = countries[nat]
        result.append({
            "nationality": nat,
            "country_rank": d["country_rank"],
            "nb_players": d["nb"],
            "nb_700": d["nb700"],
            "nb_above_avg": d["nb_above_avg"],
            "team_score": round(d["team_score"], 1),
            "quota": quota[nat],
        })
    return result


def _build_tab(db, rules: str, config: dict) -> dict:
    cfg = config.get(rules, {})
    event_cfg = cfg.get("next_event")
    sim_seats = cfg.get("simulation_seats", [40, 130])
    latest = _latest_week(db, rules)

    invited = _best_invited_players(db, rules)
    n_invited = len(invited)  # 1 or 2 seats

    tab = {"rules": rules, "invited": invited, "sim_seats": sim_seats}

    if event_cfg:
        week = event_cfg.get("ranking_week") or latest
        total = event_cfg["total_seats"]
        non_ema = event_cfg["non_ema_seats"]
        t_ema = total - non_ema - n_invited
        quotas = _compute_quotas(db, rules, week, t_ema)
        tab["event"] = {
            "name": event_cfg["name"],
            "total_seats": total,
            "non_ema_seats": non_ema,
            "invited_seats": n_invited,
            "ema_seats": t_ema,
            "ranking_week": week,
            "status": event_cfg.get("status", "simulation"),
            "quotas": quotas,
        }
    else:
        tab["event"] = None

    # Simulations
    tab["simulations"] = []
    for seats in sim_seats:
        t_ema_sim = seats - n_invited
        quotas = _compute_quotas(db, rules, latest, max(1, t_ema_sim))
        tab["simulations"].append({
            "ema_seats": seats,
            "invited_seats": n_invited,
            "ranking_week": latest,
            "quotas": quotas,
        })

    return tab


@router.get("/quotas")
def quotas_page(request: Request, db: Session = Depends(get_db)):
    config = _load_config()
    mcr = _build_tab(db, "MCR", config)
    rcr = _build_tab(db, "RCR", config)
    return templates.TemplateResponse(request, "quotas.html", {
        "mcr": mcr,
        "rcr": rcr,
    })
