"""
Script to import EMA tournaments from mahjong-europe.org
Usage : python3 import_ema.py [--start 0] [--end 453] [--delay 0.3] [--prefix TR]
        python3 import_ema.py --prefix TR_RCR --end 411        # Riichi
        python3 import_ema.py --prefix TR_RCR --ids 1000004    # WRC 2025

Players without an EMA number are stored in resultats_anonymes.
Mappings in PRENOM_TO_ID_OVERRIDES automatically convert
identifiable anonymous entries into results linked to their EMA player.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import time
import argparse
import urllib.request
import ssl
from datetime import date, datetime

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.database import engine, SessionLocal
from app.models import Base, Player, Tournament, Result, AnonymousResult

Base.metadata.create_all(bind=engine)

BASE_URL = "http://mahjong-europe.org/ranking/Tournament/{}_{}.html"

# Mappings full_first_name -> player_id for tournaments without EMA number in results.
# Key: (ema_id, regles), value: dict {displayed_first_name: player_id}
PRENOM_TO_ID_OVERRIDES: dict[tuple, dict[str, str]] = {
    (1000004, "RCR"): {
        "Mikko Aarnos":     "14990053",
        "Manuel Tertre":    "04160092",
        "Valentin Courtois":"04310012",
    },
}

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


def fetch_page(tournament_id, prefix: str = "TR") -> str | None:
    url = BASE_URL.format(prefix, tournament_id)
    try:
        with urllib.request.urlopen(url, context=ssl_ctx, timeout=10) as r:
            raw = r.read()
        for encoding in ("utf-8", "windows-1252", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("latin-1", errors="replace")
    except Exception as e:
        print(f"  [ERROR] {url} : {e}")
        return None


def parse_date(raw: str) -> tuple[date, date]:
    """
    Parses various EMA date formats. Returns (start_date, end_date).
    Known formats:
      '11-12 Mar.2023', '5 Oct.2019', '28 Sep.-1 Oct.2022'
      '06/10/2024', '31 May - 1 June 2008'
      '15-mars-15' (French month, 2-digit year)
      '9 Feb. 25'  (2-digit year)
      '2-3 February' (no year)
    """
    import re
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        # French months
        "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
    }
    raw = raw.strip()
    try:
        # Format DD/MM/YYYY
        if re.match(r'^\d{2}/\d{2}/\d{4}$', raw):
            d, m, y = int(raw[:2]), int(raw[3:5]), int(raw[6:])
            return date(y, m, d), date(y, m, d)

        # Find the year: 4 digits or 2 digits at the end
        year_m4 = re.search(r'\b(20\d{2}|19\d{2})\b', raw)
        year_m2 = re.search(r'\b(\d{2})$', raw.strip())

        if year_m4:
            year = int(year_m4.group(1))
            raw_body = raw[:year_m4.start()].strip().rstrip(".-/ ")
        elif year_m2:
            year = 2000 + int(year_m2.group(1))
            raw_body = raw[:year_m2.start()].strip().rstrip(".-/ ")
        else:
            return date(1900, 1, 1), date(1900, 1, 1)

        # Find the month (last alphabetic token)
        tokens = re.split(r"[\s.\-/]+", raw_body)
        month = None
        for t in reversed(tokens):
            key = t.lower().rstrip(".")
            if key in months:
                month = months[key]
                break
            if len(key) >= 3 and key[:3] in months:
                month = months[key[:3]]
                break

        if not month:
            return date(1900, 1, 1), date(1900, 1, 1)

        days = [int(d) for d in re.findall(r'\b\d{1,2}\b', raw_body)]
        if not days:
            return date(1900, 1, 1), date(1900, 1, 1)
        day_start = days[0]
        # If multiple months detected (e.g. "31 May - 1 June"), use the first month/day
        all_months = []
        for t in tokens:
            key = t.lower().rstrip(".")
            if key in months:
                all_months.append(months[key])
            elif len(key) >= 3 and key[:3] in months:
                all_months.append(months[key[:3]])
        if len(all_months) >= 2:
            # Multi-month: start = first month/day, end = last month/last day
            month_start = all_months[0]
            month_end = all_months[-1]
            day_end = days[-1] if len(days) > 1 else days[0]
            return date(year, month_start, day_start), date(year, month_end, day_end)
        day_end = days[-1] if len(days) > 1 else days[0]
        return date(year, month, day_start), date(year, month, day_end)
    except Exception:
        return date(1900, 1, 1), date(1900, 1, 1)


def inferer_annee(ema_id: int, regles: str) -> int | None:
    """Infers the year of a tournament from neighboring tournaments in the database."""
    import sqlite3, os
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "ema_ranking.db")
    con = sqlite3.connect(db_path)
    row = con.execute("""
        SELECT date_debut FROM tournaments
        WHERE rules=? AND date_debut != '1900-01-01'
          AND ema_id BETWEEN ? AND ?
        ORDER BY ABS(ema_id - ?) LIMIT 1
    """, (regles, ema_id - 10, ema_id + 10, ema_id)).fetchone()
    con.close()
    return int(row[0][:4]) if row else None


def parse_tournament(html: str, tournament_id: int) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    # Check that the page actually contains a tournament
    cells = soup.find_all("td", class_="PlayerBloc_2")
    if not cells:
        return None

    data = {}
    for i in range(0, len(cells) - 1, 2):
        label = cells[i].get_text(strip=True).rstrip(": ").strip()
        value = cells[i + 1].get_text(strip=True)
        data[label] = value

    if "Number" not in data:
        return None

    # Tournament info (some special tournaments have "-" as number)
    raw_number = data.get("Number", str(tournament_id))
    try:
        t_id = int(raw_number)
    except ValueError:
        t_id = tournament_id
    nom = data.get("Name", "")
    date_raw = data.get("Date", "")
    nb_joueurs_raw = data.get("Players", "0")
    mers_raw = data.get("MERS", "0")
    regles_raw = data.get("Rules", "").strip().upper()
    regles = "RCR" if ("RCR" in regles_raw or "RIICHI" in regles_raw) else "MCR"

    # City + country from the Place line
    lieu = ""
    pays = ""
    for td in soup.find_all("td"):
        font = td.find("font", color="#0000fc")
        if font and "Place" in font.get_text():
            sibling = td.find_next_sibling("td")
            if sibling:
                text = sibling.get_text(separator=" ", strip=True)
                parts = text.split("(")[0].strip()
                if "," in parts:
                    lieu, pays_full = parts.split(",", 1)
                    lieu = lieu.strip()
                    pays = pays_full.strip()
                else:
                    lieu = parts
            break

    # Coefficient (first number in MERS)
    import re
    coeff_match = re.search(r"[\d.,]+", mers_raw)
    coefficient = float(coeff_match.group().replace(",", ".")) if coeff_match else 0.0

    try:
        nb_players = int(nb_joueurs_raw)
    except ValueError:
        nb_players = 0

    date_debut, date_fin = parse_date(date_raw)

    # If date unknown, try to infer the year from neighboring tournaments
    if date_debut.year == 1900:
        annee = inferer_annee(t_id, regles)
        if annee:
            d2, d3 = parse_date(f"{date_raw} {str(annee)[-2:]}")
            if d2.year != 1900:
                date_debut, date_fin = d2, d3

    # Normalize rules (already done, but keep for the rest)
    if "RCR" in regles or "RIICHI" in regles:
        regles = "RCR"
    else:
        regles = "MCR"  # MCR, CHINESE OFFICIAL and variants

    # Results
    results = []
    lignes = soup.find_all("div", class_=["TCTT_ligne", "TCTT_ligneG"])
    for ligne in lignes:
        cellules = ligne.find_all("p")
        if len(cellules) < 7:
            continue
        # Skip the header
        if "TCTT_contenuEntete" in (cellules[0].get("class") or [""])[0]:
            continue

        pos_text = re.search(r"\d+", cellules[0].get_text())
        if not pos_text:
            continue
        position = int(pos_text.group())

        ema_link = cellules[1].find("a")
        player_id = ema_link.get_text(strip=True) if ema_link else None

        nom_joueur    = cellules[2].get_text(strip=True)
        prenom_joueur = cellules[3].get_text(strip=True)
        if nom_joueur == "-":
            nom_joueur = ""
        if prenom_joueur == "-":
            prenom_joueur = ""

        # Nationality from the flag image
        flag_img = cellules[4].find("img")
        nationality = ""
        if flag_img:
            src = flag_img.get("src", "")
            import os
            nat = os.path.basename(src).replace(".png", "").upper()
            nationality = nat

        def to_int(s: str) -> int:
            s = s.strip().replace(",", ".")
            try:
                return round(float(s))
            except ValueError:
                return 0

        try:
            points  = to_int(cellules[5].get_text(strip=True))
            mahjong = to_int(cellules[6].get_text(strip=True))
            ranking = to_int(cellules[7].get_text(strip=True)) if len(cellules) > 7 else 0
        except IndexError:
            continue

        # Pagination row or HTML artifact: empty nationality and name/first_name are digits
        if not nationality and not player_id and (nom_joueur + prenom_joueur).isdigit():
            continue

        if player_id:
            results.append({
                "player_id":  player_id,
                "name":        nom_joueur,
                "first_name":     prenom_joueur,
                "nationality": nationality,
                "position":   position,
                "points":     points,
                "mahjong":    mahjong,
                "ranking":    ranking,
            })
        else:
            results.append({
                "player_id":  None,
                "name":        nom_joueur,
                "first_name":     prenom_joueur,
                "nationality": nationality,
                "position":   position,
                "points":     points,
                "mahjong":    mahjong,
                "ranking":    ranking,
            })

    return {
        "ema_id": t_id,
        "name": nom,
        "city": lieu,
        "country": pays,
        "start_date": date_debut,
        "end_date": date_fin,
        "nb_players": nb_players,
        "coefficient": coefficient,
        "rules": regles,
        "results": results,
    }


def reset_tournament(db: Session, tournament_id: int):
    """Deletes all results (identified + anonymous) for a tournament."""
    db.query(Result).filter(Result.tournament_id == tournament_id).delete()
    db.query(AnonymousResult).filter(AnonymousResult.tournament_id == tournament_id).delete()
    db.commit()


def import_tournament(db: Session, data: dict, reset: bool = False):
    # Upsert tournament via (ema_id, regles)
    tournoi = db.query(Tournament).filter(
        Tournament.ema_id == data["ema_id"],
        Tournament.rules == data["rules"],
    ).first()
    if tournoi and reset:
        reset_tournament(db, tournoi.id)
    if not tournoi:
        tournoi = Tournament(
            ema_id=data["ema_id"], name=data["name"], city=data["city"], country=data["country"],
            start_date=data["start_date"], end_date=data["end_date"],
            nb_players=data["nb_players"], coefficient=data["coefficient"],
            rules=data["rules"],
        )
        db.add(tournoi)
        db.flush()  # to get tournoi.id
        # Delete calendar duplicate if it exists (same name+rules+date)
        doublon_cal = db.query(Tournament).filter(
            Tournament.status == "calendrier",
            Tournament.rules == data["rules"],
            Tournament.name == data["name"],
            Tournament.start_date == data["start_date"],
            Tournament.id != tournoi.id,
        ).first()
        if doublon_cal:
            db.delete(doublon_cal)
    else:
        tournoi.name = data["name"]
        tournoi.city = data["city"]
        tournoi.country = data["country"]
        tournoi.start_date = data["start_date"]
        tournoi.end_date = data["end_date"]
        tournoi.nb_players = data["nb_players"]
        tournoi.coefficient = data["coefficient"]

    # Upsert players + results
    for r in data["results"]:
        if r["player_id"] is None:
            # Player without EMA number → resultats_anonymes
            existing_anon = db.query(AnonymousResult).filter(
                AnonymousResult.tournament_id == tournoi.id,
                AnonymousResult.position   == r["position"],
            ).first()
            if not existing_anon:
                db.add(AnonymousResult(
                    tournament_id  = tournoi.id,
                    position    = r["position"],
                    nationality = r["nationality"] or None,
                    last_name   = r["name"] or None,
                    first_name  = r["first_name"] or None,
                ))
            else:
                if not existing_anon.nationality and r["nationality"]:
                    existing_anon.nationality = r["nationality"]
                if not existing_anon.last_name and r["name"]:
                    existing_anon.last_name = r["name"]
                if not existing_anon.first_name and r["first_name"]:
                    existing_anon.first_name = r["first_name"]
            continue

        joueur = db.query(Player).filter(Player.id == r["player_id"]).first()
        if not joueur:
            joueur = Player(
                id=r["player_id"],
                last_name=r["name"],
                first_name=r["first_name"],
                nationality=r["nationality"],
            )
            db.add(joueur)

        # Avoid duplicate results
        existing = db.query(Result).filter(
            Result.tournament_id == tournoi.id,
            Result.player_id  == r["player_id"],
        ).first()
        if not existing:
            db.add(Result(
                tournament_id  = tournoi.id,
                player_id   = r["player_id"],
                position    = r["position"],
                points      = r["points"],
                mahjong     = r["mahjong"],
                ranking     = r["ranking"],
                nationality = r["nationality"],
            ))
        else:
            if not existing.nationality and r["nationality"]:
                existing.nationality = r["nationality"]

    # Convert identifiable anonymous entries by first name (known overrides)
    db.flush()
    override_map = PRENOM_TO_ID_OVERRIDES.get((data["ema_id"], data["rules"]), {})
    for prenom_complet, player_id in override_map.items():
        anon = db.query(AnonymousResult).filter(
            AnonymousResult.tournament_id == tournoi.id,
            AnonymousResult.first_name     == prenom_complet,
        ).first()
        if not anon:
            continue
        joueur = db.query(Player).filter(Player.id == player_id).first()
        if not joueur:
            continue
        existing = db.query(Result).filter(
            Result.tournament_id == tournoi.id,
            Result.player_id  == player_id,
        ).first()
        if not existing:
            db.add(Result(
                tournament_id  = tournoi.id,
                player_id   = player_id,
                position    = anon.position,
                points      = 1,
                mahjong     = 1,
                ranking     = 0,
                nationality = anon.nationality,
            ))
        db.delete(anon)

    db.commit()


def _fetch_one(args_tuple):
    """Called in a thread: fetch + parse, without DB access."""
    tid, prefix = args_tuple
    html = fetch_page(tid, prefix)
    if not html:
        return tid, None, "error"
    numeric_tid = int(tid) if str(tid).lstrip("0").isdigit() else tid
    data = parse_tournament(html, numeric_tid)
    if not data:
        return tid, None, "empty"
    return tid, data, "ok"


def main():
    parser = argparse.ArgumentParser(description="Import EMA tournaments")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=453)
    parser.add_argument("--ids", nargs="+", help="Explicit IDs (e.g.: 01 02 1000001)")
    parser.add_argument("--prefix", type=str, default="TR", help="URL prefix (TR or TR_RCR)")
    parser.add_argument("--reset", action="store_true", help="Clear existing results before reimport")
    parser.add_argument("--threads", type=int, default=8, help="Number of fetch threads (default: 8)")
    args = parser.parse_args()

    if args.ids:
        id_list = args.ids
    else:
        # Format IDs < 10 with leading zero (EMA format: 01, 02, ...)
        id_list = [f"{i:02d}" if i < 10 else str(i) for i in range(args.start, args.end + 1)]

    from concurrent.futures import ThreadPoolExecutor, as_completed

    db = SessionLocal()
    ok = skip = errors = 0
    total = len(id_list)

    tasks = [(tid, args.prefix) for tid in id_list]

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {executor.submit(_fetch_one, t): t[0] for t in tasks}
        # Collect results ordered by completion, import sequentially in main thread
        results = {}
        for future in as_completed(futures):
            tid, data, status = future.result()
            results[str(tid)] = (data, status)

    # Import in original order for readable output
    for tid in id_list:
        data, status = results[str(tid)]
        print(f"[{str(tid):>8}] ", end="", flush=True)
        if status == "error":
            errors += 1
        elif status == "empty":
            print("(empty)")
            skip += 1
        else:
            import_tournament(db, data, reset=args.reset)
            nb_id  = sum(1 for r in data["results"] if r["player_id"])
            nb_ano = sum(1 for r in data["results"] if not r["player_id"])
            suffix = f"  ({nb_id} id, {nb_ano} anon)" if nb_ano else ""
            print(f"{data['rules']:3}  {data['start_date']}  {len(data['results']):3} players  {data['name']}{suffix}")
            ok += 1

    db.close()
    print(f"\nDone: {ok} imported, {skip} empty, {errors} errors.")


if __name__ == "__main__":
    main()
