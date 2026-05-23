"""
Import EMA certified referees from mahjong-europe.org.
Run with: python3 scripts/importers/import_referees.py
"""
import sys, os, re, urllib.request, ssl, unicodedata
from difflib import SequenceMatcher
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from bs4 import BeautifulSoup
from app.database import SessionLocal
from app.models import Referee, City, Player

URLS = {
    "MCR": "http://mahjong-europe.org/portal/index.php?option=com_content&view=article&id=34&Itemid=169",
    "RCR": "http://mahjong-europe.org/portal/index.php?option=com_content&view=article&id=35&catid=11&Itemid=101",
}

COUNTRY_MAP = {
    "Austria":"AT","Belgium":"BE","China":"CN","Denmark":"DK","France":"FR",
    "Germany":"DE","Hungary":"HU","Italy":"IT","Japan":"JP","Portugal":"PT",
    "Russia":"RU","Spain":"ES","Sweden":"SE","Switzerland":"CH",
    "The Netherlands":"NL","UK":"GB","Ukraine":"UA",
    "Finland":"FI","Poland":"PL","Slovakia":"SK","Czech Republic":"CZ",
    "Czech Repu":"CZ","USA":"US","SWEDEN":"SE","CHINA":"CN",
}

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
        raw = r.read()
    # Page is latin-1 but content is actually utf-8 mis-served
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1").encode("latin-1").decode("utf-8", errors="replace")


def parse_referees_mcr(text: str, rules: str) -> list[dict]:
    countries = "|".join(re.escape(c) for c in COUNTRY_MAP)
    pattern = re.compile(
        r'([A-ZÁÀÂÄÉÈÊËÍÎÏÓÔÖÚÛÜÇÑ][^\n]+?)\s+(' + countries + r')\s+([^,]+),\s*(\d{4})'
    )
    entries = []
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        country_iso = COUNTRY_MAP.get(m.group(2).strip(), "")
        if not country_iso:
            continue
        entries.append({
            "name":             name,
            "country":          country_iso,
            "rules":            rules,
            "seminar_year":     int(m.group(4)),
            "seminar_location": m.group(3).strip(),
        })
    return entries


def parse_referees_rcr(text: str, rules: str) -> list[dict]:
    # Format: "Name Country Location, Country, DD Month YYYY"
    countries = "|".join(re.escape(c) for c in COUNTRY_MAP)
    pattern = re.compile(
        r'([A-ZÁÀÂÄÉÈÊËÍÎÏÓÔÖÚÛÜÇÑ][a-záàâäéèêëíîïóôöúûüçñ\-\' ]+(?:\s+[A-ZÁÀÂÄÉÈÊËÍÎÏÓÔÖÚÛÜÇÑ][A-Za-záàâäéèêëíîïóôöúûüçñ\-\']+)+)\s+(' + countries + r')\s+(.+?),\s*\d{1,2}\s+\w+\s+(\d{4})'
    )
    entries = []
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        country_iso = COUNTRY_MAP.get(m.group(2).strip(), "")
        if not country_iso:
            continue
        # Location = first part before first comma
        full_location = m.group(3).strip()
        location = full_location.split(",")[0].strip()
        entries.append({
            "name":             name,
            "country":          country_iso,
            "rules":            rules,
            "seminar_year":     int(m.group(4)),
            "seminar_location": location,
        })
    return entries


def parse_referees(html: str, rules: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    el = soup.find(class_="item-page")
    if not el:
        return []
    text = el.get_text(" ", strip=True)
    # Strip page header
    for marker in ["MCR Referee", "RCR Referee", "Riichi Referee", "Player Country Referee Seminar"]:
        idx = text.find(marker)
        if idx != -1:
            text = text[idx + len(marker):]
            break

    if rules == "RCR":
        return parse_referees_rcr(text, rules)
    return parse_referees_mcr(text, rules)


CITY_ALIASES = {
    "Copenhague":        "Copenhagen",
    "Saint-Pétersbourg": "Saint Petersburg",
    "Réunion Island":    "Reunion Island",
    "Dutch seminar":     None,
    "Farnham":           "Farnham",
    "Bad Vöslau":        "Bad Vöslau",
    "Marseilles":        "Marseille",
    "Poznań":            "Poznan",
    "Riichi":            "IJsselstein",
    "Uppsala, Sweden, April 2024":                 "Uppsala",
    "Uppsala, Sweden, February 2025":              "Uppsala",
    "IJsselstein, The Netherlands, February 2025": "IJsselstein",
}

def find_city(db, location: str, country: str) -> int | None:
    """Try to match location string to a city in DB."""
    search = CITY_ALIASES.get(location, location)
    if search is None:
        return None
    search = search.split(",")[0].strip()

    city = db.query(City).filter(
        City.name.ilike(f"%{search}%"),
        City.country == country,
    ).first()
    if not city:
        city = db.query(City).filter(City.name.ilike(f"%{search}%")).first()
    return city.id if city else None


# Manual overrides: (referee_name_as_parsed, country) -> player_id
NAME_OVERRIDES: dict[tuple[str, str], str] = {
    ("Nobert TSCHINKEL",           "AT"): "01000009",
    ("Michael Dusleag",            "AT"): "01000125",
    ("Frank ROSTVED",              "DK"): "03000148",
    ("Jeppe S. NIELSEN",           "DK"): "03000005",
    ("Manuel Kameda-Schlich",      "DE"): "05100166",
    ("David AURE",                 "FR"): "04030005",
    ("Jean-Michel MORISSE",        "FR"): "04030022",
    ("Pierre YEUNG-LET-CHEONG",    "FR"): "04030051",
    ("Anneke KEIJL",               "NL"): "08010173",
    ("Dimphy VAN GRINSVEN",        "NL"): "08010168",
    ("Eric VAN BALKUM",            "NL"): "08010101",
    ("Gerda VAN OORSCHOT",         "NL"): "08010003",
    ("Gert VAN DER VEGT",          "NL"): "08010049",
    ("Marjan VAN DEN NIEUWENDIJK", "NL"): "08010599",
    ("Menno van Lienden",          "NL"): "08010495",
    ("Twan VAN DEN NIEUWENDIJK",   "NL"): "08010667",
    ("Marta BINKOWSKA",            "PL"): "19000007",
}


def _normalize(s: str) -> str:
    """Lowercase, strip accents, collapse spaces."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


def _full_name(p) -> str:
    return _normalize(f"{p.first_name} {p.last_name}")


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# Cache all players once per run
_ALL_PLAYERS: list | None = None

def _get_all_players(db) -> list:
    global _ALL_PLAYERS
    if _ALL_PLAYERS is None:
        _ALL_PLAYERS = db.query(Player).all()
    return _ALL_PLAYERS


MATCH_THRESHOLD = 0.82  # minimum similarity score to accept a fuzzy match


def find_player(db, name: str, country: str) -> str | None:
    """Try to match referee name to a player in DB, with accent/case normalization and fuzzy fallback."""
    if (name, country) in NAME_OVERRIDES:
        return NAME_OVERRIDES[(name, country)]

    parts = name.strip().split()
    if len(parts) < 2:
        return None

    all_players = _get_all_players(db)
    country_players = [p for p in all_players if p.nationality == country]

    def exact_match(candidates, last, first):
        nl, nf = _normalize(last), _normalize(first)
        for p in candidates:
            if _normalize(p.last_name) == nl and _normalize(p.first_name) == nf:
                return p.id
        return None

    # 1. Exact match with country
    for i in range(1, len(parts)):
        last, first = " ".join(parts[:i]), " ".join(parts[i:])
        pid = exact_match(country_players, last, first) or exact_match(country_players, first, last)
        if pid:
            return pid

    # 2. Exact match without country
    for i in range(1, len(parts)):
        last, first = " ".join(parts[:i]), " ".join(parts[i:])
        pid = exact_match(all_players, last, first) or exact_match(all_players, first, last)
        if pid:
            return pid

    # 3. Fuzzy match: compare normalized full name against all permutations
    ref_full = _normalize(name)
    # also try "first last" and "last first" permutations
    ref_variants = {ref_full}
    for i in range(1, len(parts)):
        ref_variants.add(_normalize(" ".join(parts[i:]) + " " + " ".join(parts[:i])))

    best_id, best_score = None, 0.0
    pool = country_players if country_players else all_players
    for p in pool:
        pfull = _full_name(p)
        score = max(_similarity(v, pfull) for v in ref_variants)
        if score > best_score:
            best_score, best_id = score, p.id

    if best_score >= MATCH_THRESHOLD:
        return best_id

    # 4. Fuzzy without country if no match found
    if pool is not all_players:
        for p in all_players:
            pfull = _full_name(p)
            score = max(_similarity(v, pfull) for v in ref_variants)
            if score > best_score:
                best_score, best_id = score, p.id
        if best_score >= MATCH_THRESHOLD:
            return best_id

    return None


def run():
    db = SessionLocal()
    inserted = skipped = matched_city = matched_player = 0

    for rules, url in URLS.items():
        print(f"\nFetching {rules}...")
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  Error: {e}")
            continue

        entries = parse_referees(html, rules)
        print(f"  Parsed {len(entries)} referees")

        for e in entries:
            # Skip if already exists
            existing = db.query(Referee).filter(
                Referee.name == e["name"],
                Referee.rules == rules,
                Referee.seminar_year == e["seminar_year"],
            ).first()
            if existing:
                skipped += 1
                continue

            city_id = find_city(db, e["seminar_location"], e["country"])
            if city_id:
                matched_city += 1

            player_id = find_player(db, e["name"], e["country"])
            if player_id:
                matched_player += 1

            db.add(Referee(
                name             = e["name"],
                country          = e["country"],
                rules            = rules,
                seminar_year     = e["seminar_year"],
                seminar_location = e["seminar_location"],
                seminar_city_id  = city_id,
                player_id        = player_id,
            ))
            inserted += 1

    db.commit()
    db.close()
    print(f"\nDone: {inserted} inserted, {skipped} skipped")
    print(f"  Cities matched: {matched_city}/{inserted}")
    print(f"  Players matched: {matched_player}/{inserted}")


if __name__ == "__main__":
    run()
