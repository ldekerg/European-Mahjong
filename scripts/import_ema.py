"""
Script d'import des tournois EMA depuis mahjong-europe.org
Usage : python3 import_ema.py [--start 0] [--end 453] [--delay 0.3] [--prefix TR]
        python3 import_ema.py --prefix TR_RCR --end 411   # Riichi
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import argparse
import urllib.request
import ssl
from datetime import date, datetime

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from database import engine, SessionLocal
from models import Base, Joueur, Tournoi, Resultat

Base.metadata.create_all(bind=engine)

BASE_URL = "http://mahjong-europe.org/ranking/Tournament/{}_{}.html"

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
        print(f"  [ERREUR] {url} : {e}")
        return None


def parse_date(raw: str) -> tuple[date, date]:
    """
    Parse les formats de date EMA variés. Retourne (date_debut, date_fin).
    Formats connus :
      '11-12 Mar.2023', '5 Oct.2019', '28 Sep.-1 Oct.2022'
      '06/10/2024', '31 May - 1 June 2008'
      '15-mars-15' (mois français, année 2 chiffres)
      '9 Feb. 25'  (année 2 chiffres)
      '2-3 February' (sans année)
    """
    import re
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        # Mois français
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

        # Trouver l'année : 4 chiffres ou 2 chiffres en fin
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

        # Trouver le mois (dernier token alphabétique)
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
        # Si plusieurs mois détectés (ex: "31 May - 1 June"), utiliser le premier mois/jour
        all_months = []
        for t in tokens:
            key = t.lower().rstrip(".")
            if key in months:
                all_months.append(months[key])
            elif len(key) >= 3 and key[:3] in months:
                all_months.append(months[key[:3]])
        if len(all_months) >= 2:
            # Multi-mois : start = premier mois/jour, end = dernier mois/dernier jour
            month_start = all_months[0]
            month_end = all_months[-1]
            day_end = days[-1] if len(days) > 1 else days[0]
            return date(year, month_start, day_start), date(year, month_end, day_end)
        day_end = days[-1] if len(days) > 1 else days[0]
        return date(year, month, day_start), date(year, month, day_end)
    except Exception:
        return date(1900, 1, 1), date(1900, 1, 1)


def inferer_annee(ema_id: int, regles: str) -> int | None:
    """Infère l'année d'un tournoi depuis les tournois voisins en base."""
    import sqlite3, os
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "ema_ranking.db")
    con = sqlite3.connect(db_path)
    row = con.execute("""
        SELECT date_debut FROM tournois
        WHERE regles=? AND date_debut != '1900-01-01'
          AND ema_id BETWEEN ? AND ?
        ORDER BY ABS(ema_id - ?) LIMIT 1
    """, (regles, ema_id - 10, ema_id + 10, ema_id)).fetchone()
    con.close()
    return int(row[0][:4]) if row else None


def parse_tournament(html: str, tournament_id: int) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    # Vérifier que la page contient bien un tournoi
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

    # Infos tournoi (certains tournois spéciaux ont "-" comme numéro)
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

    # Lieu + pays depuis la ligne Place
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

    # Coefficient (premier nombre dans MERS)
    import re
    coeff_match = re.search(r"[\d.,]+", mers_raw)
    coefficient = float(coeff_match.group().replace(",", ".")) if coeff_match else 0.0

    try:
        nb_joueurs = int(nb_joueurs_raw)
    except ValueError:
        nb_joueurs = 0

    date_debut, date_fin = parse_date(date_raw)

    # Si date inconnue, tenter d'inférer l'année depuis les tournois voisins
    if date_debut.year == 1900:
        annee = inferer_annee(t_id, regles)
        if annee:
            d2, d3 = parse_date(f"{date_raw} {str(annee)[-2:]}")
            if d2.year != 1900:
                date_debut, date_fin = d2, d3

    # Normaliser les règles (déjà fait, mais conserver pour la suite)
    if "RCR" in regles or "RIICHI" in regles:
        regles = "RCR"
    else:
        regles = "MCR"  # MCR, CHINESE OFFICIAL et variantes

    # Résultats
    resultats = []
    lignes = soup.find_all("div", class_=["TCTT_ligne", "TCTT_ligneG"])
    for ligne in lignes:
        cellules = ligne.find_all("p")
        if len(cellules) < 7:
            continue
        # Ignorer l'en-tête
        if "TCTT_contenuEntete" in (cellules[0].get("class") or [""])[0]:
            continue

        pos_text = re.search(r"\d+", cellules[0].get_text())
        if not pos_text:
            continue
        position = int(pos_text.group())

        ema_link = cellules[1].find("a")
        if not ema_link:
            continue
        joueur_id = ema_link.get_text(strip=True)

        nom_joueur = cellules[2].get_text(strip=True)
        prenom_joueur = cellules[3].get_text(strip=True)

        # Nationalité depuis l'image du drapeau
        flag_img = cellules[4].find("img")
        nationalite = ""
        if flag_img:
            src = flag_img.get("src", "")
            import os
            nat = os.path.basename(src).replace(".png", "").upper()
            nationalite = nat

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

        resultats.append({
            "joueur_id": joueur_id,
            "nom": nom_joueur,
            "prenom": prenom_joueur,
            "nationalite": nationalite,
            "position": position,
            "points": points,
            "mahjong": mahjong,
            "ranking": ranking,
        })

    return {
        "ema_id": t_id,
        "nom": nom,
        "lieu": lieu,
        "pays": pays,
        "date_debut": date_debut,
        "date_fin": date_fin,
        "nb_joueurs": nb_joueurs,
        "coefficient": coefficient,
        "regles": regles,
        "resultats": resultats,
    }


def import_tournament(db: Session, data: dict):
    # Upsert tournoi via (ema_id, regles)
    tournoi = db.query(Tournoi).filter(
        Tournoi.ema_id == data["ema_id"],
        Tournoi.regles == data["regles"],
    ).first()
    if not tournoi:
        tournoi = Tournoi(
            ema_id=data["ema_id"], nom=data["nom"], lieu=data["lieu"], pays=data["pays"],
            date_debut=data["date_debut"], date_fin=data["date_fin"],
            nb_joueurs=data["nb_joueurs"], coefficient=data["coefficient"],
            regles=data["regles"],
        )
        db.add(tournoi)
        db.flush()  # pour obtenir tournoi.id
    else:
        tournoi.nom = data["nom"]
        tournoi.lieu = data["lieu"]
        tournoi.pays = data["pays"]
        tournoi.date_debut = data["date_debut"]
        tournoi.date_fin = data["date_fin"]
        tournoi.nb_joueurs = data["nb_joueurs"]
        tournoi.coefficient = data["coefficient"]

    # Upsert joueurs + résultats
    for r in data["resultats"]:
        joueur = db.query(Joueur).filter(Joueur.id == r["joueur_id"]).first()
        if not joueur:
            joueur = Joueur(
                id=r["joueur_id"],
                nom=r["nom"],
                prenom=r["prenom"],
                nationalite=r["nationalite"],
            )
            db.add(joueur)

        # Eviter les doublons de résultat
        existing = db.query(Resultat).filter(
            Resultat.tournoi_id == tournoi.id,
            Resultat.joueur_id == r["joueur_id"],
        ).first()
        if not existing:
            db.add(Resultat(
                tournoi_id=tournoi.id,
                joueur_id=r["joueur_id"],
                position=r["position"],
                points=r["points"],
                mahjong=r["mahjong"],
                ranking=r["ranking"],
                nationalite=r["nationalite"],
            ))
        else:
            # Mettre à jour la nationalité si elle n'est pas encore renseignée
            if not existing.nationalite and r["nationalite"]:
                existing.nationalite = r["nationalite"]

    db.commit()


def main():
    parser = argparse.ArgumentParser(description="Import EMA tournaments")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=453)
    parser.add_argument("--ids", nargs="+", help="IDs explicites (ex: 01 02 1000001)")
    parser.add_argument("--delay", type=float, default=0.3, help="Délai entre requêtes (secondes)")
    parser.add_argument("--prefix", type=str, default="TR", help="Préfixe URL (TR ou TR_RCR)")
    args = parser.parse_args()

    if args.ids:
        id_list = args.ids  # chaînes brutes, ex: ["01", "1000001"]
    else:
        id_list = list(range(args.start, args.end + 1))

    db = SessionLocal()
    ok = 0
    skip = 0
    errors = 0

    for tid in id_list:
        print(f"[{str(tid):>8}] ", end="", flush=True)
        html = fetch_page(tid, args.prefix)
        if not html:
            errors += 1
            continue

        numeric_tid = int(tid) if str(tid).lstrip("0").isdigit() else tid
        data = parse_tournament(html, numeric_tid)
        if not data:
            print("(vide)")
            skip += 1
        else:
            import_tournament(db, data)
            print(f"{data['regles']:3}  {data['date_debut']}  {len(data['resultats']):3} joueurs  {data['nom']}")
            ok += 1

        time.sleep(args.delay)

    db.close()
    print(f"\nTerminé : {ok} importés, {skip} vides, {errors} erreurs.")


if __name__ == "__main__":
    main()
