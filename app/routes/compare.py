from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.i18n import templates
from app.models import Player, RankingHistory, Result, Tournament

router = APIRouter()

COLORS = ["#4e9af1", "#e8715a", "#4cb87e", "#f0b429", "#a78bfa"]


def _search_players(db: Session, q: str, limit: int = 10) -> list[dict]:
    q = q.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    rows = db.execute(text("""
        SELECT p.id, p.first_name, p.last_name, p.nationality
        FROM players p
        WHERE (p.first_name || ' ' || p.last_name LIKE :p)
           OR (p.last_name || ' ' || p.first_name LIKE :p)
           OR p.last_name LIKE :p
        ORDER BY p.last_name, p.first_name
        LIMIT :lim
    """), {"p": pattern, "lim": limit}).fetchall()
    return [{"id": r[0], "first_name": r[1], "last_name": r[2], "nationality": r[3]} for r in rows]


def _player_history(db: Session, player_id: str, rules: str) -> list[dict]:
    rows = db.execute(text("""
        SELECT rh.week, rh.score, rh.position
        FROM ranking_history rh
        WHERE rh.player_id = :pid AND rh.rules = :r
        ORDER BY rh.week
    """), {"pid": player_id, "r": rules}).fetchall()
    return [{"week": r[0], "score": round(r[1], 2), "position": r[2]} for r in rows]


def _player_current(db: Session, player_id: str, rules: str) -> dict | None:
    row = db.execute(text("""
        SELECT rh.score, rh.position, rh.week
        FROM ranking_history rh
        WHERE rh.player_id = :pid AND rh.rules = :r
        ORDER BY rh.week DESC LIMIT 1
    """), {"pid": player_id, "r": rules}).fetchone()
    if not row:
        return None
    nb = db.execute(text("""
        SELECT COUNT(DISTINCT r.tournament_id)
        FROM results r JOIN tournaments t ON r.tournament_id = t.id
        WHERE r.player_id = :pid AND t.rules = :r AND t.ema_id IS NOT NULL
    """), {"pid": player_id, "r": rules}).scalar() or 0
    best = db.execute(text("""
        SELECT MAX(rh2.score) FROM ranking_history rh2
        WHERE rh2.player_id = :pid AND rh2.rules = :r
    """), {"pid": player_id, "r": rules}).scalar()
    best_rank = db.execute(text("""
        SELECT MIN(rh2.position) FROM ranking_history rh2
        WHERE rh2.player_id = :pid AND rh2.rules = :r
    """), {"pid": player_id, "r": rules}).scalar()
    return {
        "score": round(row[0], 2),
        "position": row[1],
        "week": row[2],
        "nb_tournaments": nb,
        "best_score": round(best, 2) if best else None,
        "best_rank": best_rank,
    }


def _common_tournaments(db: Session, player_ids: list[str], rules: str) -> list[dict]:
    if len(player_ids) < 2:
        return []
    # Find tournaments where ALL selected players have a result
    placeholders = ",".join(f":p{i}" for i in range(len(player_ids)))
    params = {"r": rules, "n": len(player_ids)}
    params.update({f"p{i}": pid for i, pid in enumerate(player_ids)})
    rows = db.execute(text(f"""
        SELECT t.id, t.name, t.start_date, c.name, t.country, t.nb_players
        FROM tournaments t
        LEFT JOIN cities c ON t.city_id = c.id
        WHERE t.rules = :r AND t.ema_id IS NOT NULL
          AND (
            SELECT COUNT(DISTINCT r.player_id) FROM results r
            WHERE r.tournament_id = t.id AND r.player_id IN ({placeholders})
          ) = :n
        ORDER BY t.start_date DESC
    """), params).fetchall()

    tournaments = []
    for tid, name, start_date, city, country, nb_players in rows:
        # Get position for each player
        positions = {}
        for i, pid in enumerate(player_ids):
            r = db.execute(text("""
                SELECT position FROM results WHERE tournament_id = :tid AND player_id = :pid
            """), {"tid": tid, "pid": pid}).fetchone()
            positions[pid] = r[0] if r else None
        tournaments.append({
            "id": tid,
            "name": name,
            "start_date": start_date,
            "city": city,
            "country": country,
            "nb_players": nb_players,
            "positions": positions,
        })
    return tournaments


def _head_to_head(common: list[dict], player_ids: list[str]) -> dict:
    """For each pair of players, count who finished ahead."""
    wins = {pid: 0 for pid in player_ids}
    for t in common:
        pos = t["positions"]
        valid = [pid for pid in player_ids if pos.get(pid) is not None]
        if not valid:
            continue
        best_pos = min(pos[pid] for pid in valid)
        # Award win to player(s) with best position
        for pid in valid:
            if pos[pid] == best_pos:
                wins[pid] += 1
    return wins


@router.get("/api/players/search")
def api_player_search(q: str = "", db: Session = Depends(get_db)):
    results = _search_players(db, q)
    return JSONResponse(content=results)


@router.get("/compare")
def compare_page(
    request: Request,
    ids: str = "",
    rules: str = "MCR",
    db: Session = Depends(get_db),
):
    player_ids = [x.strip() for x in ids.split(",") if x.strip()][:5]
    rules = rules.upper() if rules.upper() in ("MCR", "RCR") else "MCR"

    players_data = []
    for i, pid in enumerate(player_ids):
        p = db.query(Player).filter(Player.id == pid).first()
        if not p:
            continue
        history = _player_history(db, pid, rules)
        current = _player_current(db, pid, rules)
        players_data.append({
            "id": pid,
            "first_name": p.first_name,
            "last_name": p.last_name,
            "nationality": p.nationality,
            "color": COLORS[i % len(COLORS)],
            "history": history,
            "current": current,
        })

    common = _common_tournaments(db, [p["id"] for p in players_data], rules) if len(players_data) >= 2 else []
    h2h = _head_to_head(common, [p["id"] for p in players_data]) if common else {}

    return templates.TemplateResponse(request, "compare.html", {
        "players": players_data,
        "rules": rules,
        "ids_str": ",".join(p["id"] for p in players_data),
        "common": common,
        "h2h": h2h,
        "colors": COLORS,
    })
