"""
Import of the EMA calendar (upcoming tournaments) from Calendar.html.
Creates tournaments with status='calendrier' and ema_id=NULL.
Updates existing tournaments if name+rules+date already match.
Run with: python3 scripts/import_calendar.py
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import urllib.request, ssl
from datetime import date, timedelta
from bs4 import BeautifulSoup
from app.database import SessionLocal
from app.models import Tournament, City

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

# Tournament type based on name
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
    """Converts '9-10', '31-01', '2-3-4-5', '31oct-01nov' into (start_date, end_date)."""
    dates_txt = dates_txt.strip()

    # Case "31oct-01nov": days with literal month suffixes
    m = re.match(r'(\d+)[a-zA-Z]+-(\d+)[a-zA-Z]+', dates_txt)
    if m:
        j1, j2 = int(m.group(1)), int(m.group(2))
        mois2, annee2 = _mois_suivant(mois, annee)
        return date(annee, mois, j1), date(annee2, mois2, j2)

    # Extract all integers
    nums = [int(x) for x in re.findall(r'\d+', dates_txt)]
    if not nums:
        return date(annee, mois, 1), date(annee, mois, 1)

    j1, j2 = nums[0], nums[-1]

    # Month overlap: e.g. "31-01" (j1 > j2 and exactly 2 numbers)
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


def parse_whats_new(html: str) -> dict[str, date]:
    """Parse the 'What's new' section. Returns {tournament_name: date_added}."""
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    h4 = soup.find("h4", string=lambda t: t and "what" in t.lower())
    if not h4:
        return result
    ul = h4.find_next("ul")
    if not ul:
        return result
    for li in ul.find_all("li"):
        txt = li.get_text(" ", strip=True)
        # Format: "18/05/2026 : -- Vienna Riichi Open 2026 -- : ..."
        m = re.match(r'(\d{2}/\d{2}/\d{4})\s*:\s*--\s*(.+?)\s*--', txt)
        if m:
            try:
                d = date(int(m.group(1)[6:]), int(m.group(1)[3:5]), int(m.group(1)[:2]))
                result[m.group(2).strip()] = d
            except ValueError:
                pass
    return result


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

        # Month header: "May 2026"
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

        # Name + flag
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
        url_site = lien.get("href", "").strip() if lien else None
        if url_site and not url_site.startswith("http"):
            url_site = None

        regles_txt = cellules[1].get_text(strip=True)
        regles = "RCR" if "Riichi" in regles_txt or "RCR" in regles_txt else "MCR"

        dates_txt = cellules[2].get_text(strip=True)
        lieu = cellules[3].get_text(strip=True)

        reg_txt = cellules[5].get_text(strip=True) if len(cellules) > 5 else ""
        registration_open = None
        m_reg = re.match(r'(\w+)\s+(\d+),?\s+(\d{4})', reg_txt)
        if m_reg and m_reg.group(1) in MOIS:
            try:
                registration_open = date(int(m_reg.group(3)), MOIS[m_reg.group(1)], int(m_reg.group(2)))
            except ValueError:
                pass

        approbation_txt = cellules[4].get_text(strip=True) if len(cellules) > 4 else ""
        if "No MERS" in approbation_txt or "No Mers" in approbation_txt or "No Europe" in approbation_txt:
            approbation = "no_mers"
        elif "pending" in approbation_txt.lower() or "Approval" in approbation_txt:
            approbation = "pending"
        else:
            approbation = "ok"

        pays = nat_iso.upper()  # store as ISO 2-letter code

        # ema_id from results link
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
            "name":          nom,
            "rules":       regles,
            "city":         lieu,
            "country":         pays,
            "nat_iso":      nat_iso.upper(),
            "start_date":   date_debut,
            "end_date":     date_fin,
            "ema_id":       ema_id,
            "tournament_type": type_from_nom(nom),
            "approval":          approbation,
            "website":           url_site or None,
            "registration_open": registration_open,
        })

    return entries


def run():
    html = fetch_html()
    whats_new = parse_whats_new(html)
    print(f"What's new: {len(whats_new)} entries")
    entries = parse_calendar(html)
    print(f"Parsed: {len(entries)} tournaments")

    db = SessionLocal()
    inseres = updated = skipped = 0

    for e in entries:
        # If ema_id is known, first search by ema_id+rules
        tournoi = None
        if e["ema_id"]:
            tournoi = db.query(Tournament).filter(
                Tournament.ema_id == e["ema_id"],
                Tournament.rules == e["rules"],
            ).first()

        # Otherwise search by name+rules+start_date
        if not tournoi:
            tournoi = db.query(Tournament).filter(
                Tournament.name      == e["name"],
                Tournament.rules   == e["rules"],
                Tournament.start_date == e["start_date"],
            ).first()

        if tournoi:
            # Update if already in database
            changed = False
            if tournoi.status == "calendrier" or tournoi.ema_id is None:
                if e["ema_id"] and tournoi.ema_id != e["ema_id"]:
                    tournoi.ema_id = e["ema_id"]
                    changed = True
                if tournoi.end_date != e["end_date"]:
                    tournoi.end_date = e["end_date"]
                    changed = True
            if tournoi.approval != e["approval"]:
                tournoi.approval = e["approval"]
                changed = True
            if e["website"] and tournoi.website != e["website"]:
                tournoi.website = e["website"]
                changed = True
            if e["registration_open"] and tournoi.registration_open != e["registration_open"]:
                tournoi.registration_open = e["registration_open"]
                changed = True
            # Backfill created_at from what's new if not yet set
            if tournoi.created_at is None:
                from datetime import datetime as _dt
                added_date = whats_new.get(e["name"])
                if added_date:
                    tournoi.created_at = _dt.combine(added_date, _dt.min.time())
                    changed = True
            if changed:
                updated += 1
                print(f"  ~ {e['rules']} {e['start_date']} {e['name']}")
            else:
                skipped += 1
            continue

        # New calendar tournament
        from datetime import datetime as _dt
        added_date = whats_new.get(e["name"])
        created_at = _dt.combine(added_date, _dt.min.time()) if added_date else None
        city_obj = db.query(City).filter_by(name=e["city"], country=e["country"]).first()
        db.add(Tournament(
            ema_id          = e["ema_id"],
            rules           = e["rules"],
            name            = e["name"],
            city_id         = city_obj.id if city_obj else None,
            country         = e["country"],
            start_date      = e["start_date"],
            end_date        = e["end_date"],
            nb_players      = 0,
            coefficient     = 0.0,
            tournament_type = e["tournament_type"],
            status          = "calendrier",
            approval          = e["approval"],
            website           = e["website"],
            registration_open = e["registration_open"],
            created_at        = created_at,
        ))
        print(f"  + {e['rules']} {e['start_date']} {e['name']} (added {added_date or 'now'})")
        inseres += 1

    db.commit()
    db.close()
    print(f"\nDone: {inseres} inserted, {updated} updated, {skipped} skipped.")


if __name__ == "__main__":
    run()
