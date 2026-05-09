"""
Import du calendrier EMA (tournois futurs) depuis Calendar.html.
Crée des tournois avec statut='calendrier' et ema_id=NULL.
Met à jour les tournois existants si le nom+regles+date correspondent déjà.
Lance avec : python3 scripts/import_calendar.py
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import urllib.request, ssl
from datetime import date, timedelta
from bs4 import BeautifulSoup
from database import SessionLocal
from models import Tournoi

URL = "http://mahjong-europe.org/ranking/Calendar.html"

MOIS = {
    'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,
    'July':7,'August':8,'September':9,'October':10,'November':11,'December':12
}

ISO_PAYS = {
    "fr":"France","de":"Germany","nl":"Netherlands","be":"Belgium","lu":"Luxembourg",
    "gb":"Great Britain","ie":"Ireland","es":"Spain","pt":"Portugal","it":"Italy",
    "at":"Austria","ch":"Switzerland","dk":"Denmark","se":"Sweden","no":"Norway",
    "fi":"Finland","pl":"Poland","cz":"Czech Republic","sk":"Slovakia","hu":"Hungary",
    "ro":"Romania","ua":"Ukraine","ee":"Estonia","lv":"Latvia","lt":"Lithuania",
    "hr":"Croatia","si":"Slovenia","rs":"Serbia","bg":"Bulgaria","gr":"Greece",
    "tr":"Turkey","il":"Israel","mk":"North Macedonia","ba":"Bosnia and H.",
    "ru":"Russia","by":"Belarus","jp":"Japan","cn":"China","kr":"South Korea",
}

# Type de tournoi selon le nom
TYPE_SPECIAL = {
    "oemc": ["oemc", "european mcr championship"],
    "wmc":  ["wmc", "world mcr championship"],
    "oerc": ["oerc", "european riichi championship"],
    "wrc":  ["wrc", "world riichi championship"],
}


def type_from_nom(nom: str) -> str:
    nom_l = nom.lower()
    for type_key, keywords in TYPE_SPECIAL.items():
        if any(k in nom_l for k in keywords):
            return type_key
    return "normal"


def _mois_suivant(mois: int, annee: int) -> tuple[int, int]:
    return (mois + 1, annee) if mois < 12 else (1, annee + 1)


def parse_dates(dates_txt: str, mois: int, annee: int) -> tuple[date, date]:
    """Convertit '9-10', '31-01', '2-3-4-5', '31oct-01nov' en (date_debut, date_fin)."""
    dates_txt = dates_txt.strip()

    # Cas "31oct-01nov" : jours avec suffixes de mois littéraux
    m = re.match(r'(\d+)[a-zA-Z]+-(\d+)[a-zA-Z]+', dates_txt)
    if m:
        j1, j2 = int(m.group(1)), int(m.group(2))
        mois2, annee2 = _mois_suivant(mois, annee)
        return date(annee, mois, j1), date(annee2, mois2, j2)

    # Extraire tous les entiers
    nums = [int(x) for x in re.findall(r'\d+', dates_txt)]
    if not nums:
        return date(annee, mois, 1), date(annee, mois, 1)

    j1, j2 = nums[0], nums[-1]

    # Chevauchement de mois : ex "31-01" (j1 > j2 et exactement 2 nombres)
    if len(nums) == 2 and j1 > j2:
        mois2, annee2 = _mois_suivant(mois, annee)
        try:
            return date(annee, mois, j1), date(annee2, mois2, j2)
        except ValueError:
            pass

    try:
        return date(annee, mois, j1), date(annee, mois, j2)
    except ValueError:
        return date(annee, mois, 1), date(annee, mois, 1)


def fetch_html() -> str:
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(URL, context=ssl_ctx, timeout=15) as r:
        raw = r.read()
    for enc in ("utf-8", "windows-1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_calendar(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    lignes = soup.find_all("div", class_=["TCTT_ligne", "TCTT_ligneG"])

    mois_courant = (1, 2026)
    entries = []

    for ligne in lignes:
        cellules = ligne.find_all("p")
        if not cellules:
            continue

        cls0 = (cellules[0].get("class") or [""])[0]

        # En-tête de mois : "May 2026"
        if "Entete" in cls0:
            txt = cellules[0].get_text(strip=True)
            for m_nom, m_num in MOIS.items():
                if m_nom in txt:
                    try:
                        annee = int(txt.split()[-1])
                        mois_courant = (m_num, annee)
                    except ValueError:
                        pass
            continue

        if len(cellules) < 4:
            continue

        # Nom + drapeau
        nom_cell = cellules[0]
        flag_img = nom_cell.find("img")
        nat_iso = ""
        if flag_img:
            src = flag_img.get("src", "")
            nat_iso = os.path.basename(src).replace(".png", "").lower()
        lien = nom_cell.find("a")
        nom = lien.get_text(strip=True) if lien else nom_cell.get_text(strip=True)
        nom = nom.strip()
        if not nom:
            continue

        regles_txt = cellules[1].get_text(strip=True)
        regles = "RCR" if "Riichi" in regles_txt or "RCR" in regles_txt else "MCR"

        dates_txt = cellules[2].get_text(strip=True)
        lieu = cellules[3].get_text(strip=True)

        approbation_txt = cellules[4].get_text(strip=True) if len(cellules) > 4 else ""
        if "No MERS" in approbation_txt or "No Mers" in approbation_txt or "No Europe" in approbation_txt:
            approbation = "no_mers"
        elif "pending" in approbation_txt.lower() or "Approval" in approbation_txt:
            approbation = "pending"
        else:
            approbation = "ok"

        pays = ISO_PAYS.get(nat_iso, lieu)

        # ema_id depuis lien résultats
        ema_id = None
        res_cell = cellules[6] if len(cellules) > 6 else None
        if res_cell:
            res_link = res_cell.find("a")
            if res_link:
                href = res_link.get("href", "")
                m = re.search(r'TR(?:_RCR)?_(\d+)\.html', href)
                if m:
                    ema_id = int(m.group(1))

        mois_num, annee = mois_courant
        date_debut, date_fin = parse_dates(dates_txt, mois_num, annee)

        entries.append({
            "nom":          nom,
            "regles":       regles,
            "lieu":         lieu,
            "pays":         pays,
            "nat_iso":      nat_iso.upper(),
            "date_debut":   date_debut,
            "date_fin":     date_fin,
            "ema_id":       ema_id,
            "type_tournoi": type_from_nom(nom),
            "approbation":  approbation,
        })

    return entries


def run():
    html = fetch_html()
    entries = parse_calendar(html)
    print(f"Parsés: {len(entries)} tournois")

    db = SessionLocal()
    inseres = updated = skipped = 0

    for e in entries:
        # Si ema_id connu, chercher d'abord par ema_id+regles
        tournoi = None
        if e["ema_id"]:
            tournoi = db.query(Tournoi).filter(
                Tournoi.ema_id == e["ema_id"],
                Tournoi.regles == e["regles"],
            ).first()

        # Sinon chercher par nom+regles+date_debut
        if not tournoi:
            tournoi = db.query(Tournoi).filter(
                Tournoi.nom      == e["nom"],
                Tournoi.regles   == e["regles"],
                Tournoi.date_debut == e["date_debut"],
            ).first()

        if tournoi:
            # Mettre à jour si déjà en base
            changed = False
            if tournoi.statut == "calendrier" or tournoi.ema_id is None:
                if e["ema_id"] and tournoi.ema_id != e["ema_id"]:
                    tournoi.ema_id = e["ema_id"]
                    changed = True
                if tournoi.date_fin != e["date_fin"]:
                    tournoi.date_fin = e["date_fin"]
                    changed = True
            if tournoi.approbation != e["approbation"]:
                tournoi.approbation = e["approbation"]
                changed = True
            if changed:
                updated += 1
                print(f"  ~ {e['regles']} {e['date_debut']} {e['nom']}")
            else:
                skipped += 1
            continue

        # Nouveau tournoi calendrier
        db.add(Tournoi(
            ema_id       = e["ema_id"],
            regles       = e["regles"],
            nom          = e["nom"],
            lieu         = e["lieu"],
            pays         = e["pays"],
            date_debut   = e["date_debut"],
            date_fin     = e["date_fin"],
            nb_joueurs   = 0,
            coefficient  = 0.0,
            type_tournoi = e["type_tournoi"],
            statut       = "calendrier",
            approbation  = e["approbation"],
        ))
        print(f"  + {e['regles']} {e['date_debut']} {e['nom']}")
        inseres += 1

    db.commit()
    db.close()
    print(f"\nDone: {inseres} insérés, {updated} mis à jour, {skipped} ignorés.")


if __name__ == "__main__":
    run()
