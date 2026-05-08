import os
from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def flag_emoji(code: str) -> str:
    """Code ISO 2 lettres → emoji drapeau. Ex: 'FR' → '🇫🇷'. Guest → 🌍"""
    if not code:
        return ""
    if code.upper() in ("GUEST", "OTHER", "XX"):
        return "🌍"
    if len(code) < 2:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper()[:2])


templates.env.filters["flag"] = flag_emoji

ISO_NOM_PAYS = {
    "FR": "France",       "DE": "Germany",       "NL": "Netherlands",   "BE": "Belgium",
    "ES": "Spain",        "IT": "Italy",          "AT": "Austria",       "CH": "Switzerland",
    "DK": "Denmark",      "SE": "Sweden",         "FI": "Finland",       "NO": "Norway",
    "PL": "Poland",       "CZ": "Czech Republic", "HU": "Hungary",       "SK": "Slovakia",
    "PT": "Portugal",     "GB": "Great Britain",  "UK": "United Kingdom","IE": "Ireland",
    "RU": "Russia",       "UA": "Ukraine",        "BY": "Belarus",       "LV": "Latvia",
    "LT": "Lithuania",    "EE": "Estonia",        "RO": "Romania",       "BG": "Bulgaria",
    "HR": "Croatia",      "SI": "Slovenia",       "RS": "Serbia",        "GR": "Greece",
    "TR": "Turkey",       "IL": "Israel",         "LU": "Luxembourg",    "BA": "Bosnia and H.",
    "JP": "Japan",        "CN": "China",          "KR": "South Korea",   "TW": "Taiwan",
    "HK": "Hong Kong",    "US": "United States",  "CA": "Canada",        "AU": "Australia",
    "MK": "North Macedonia", "MD": "Moldova",     "AL": "Albania",       "ME": "Montenegro",
}

_PAYS_ISO = {
    "france": "FR", "germany": "DE", "netherlands": "NL", "belgium": "BE",
    "spain": "ES", "italy": "IT", "austria": "AT", "switzerland": "CH",
    "denmark": "DK", "sweden": "SE", "finland": "FI", "norway": "NO",
    "poland": "PL", "czech republic": "CZ", "hungary": "HU", "slovakia": "SK",
    "portugal": "PT", "great britain": "GB", "united kingdom": "GB",
    "russia": "RU", "ukraine": "UA", "belarus": "BY", "latvia": "LV",
    "lithuania": "LT", "estonia": "EE", "romania": "RO", "bulgaria": "BG",
    "croatia": "HR", "slovenia": "SI", "serbia": "RS", "greece": "GR",
    "turkey": "TR", "israel": "IL", "japan": "JP", "china": "CN",
    "south korea": "KR", "taiwan": "TW", "hong kong": "HK",
    "united states": "US", "canada": "CA", "australia": "AU",
    "bosnia and h.": "BA", "luxembourg": "LU", "ireland": "IE",
}

def pays_flag(pays: str) -> str:
    """Convertit un nom de pays en emoji drapeau."""
    if not pays:
        return ""
    iso = _PAYS_ISO.get(pays.lower().strip())
    if iso:
        return flag_emoji(iso)
    # Fallback : essayer les 2 premiers caractères si le pays ressemble à un code
    if len(pays) == 2:
        return flag_emoji(pays)
    return ""

templates.env.filters["pays_flag"] = pays_flag


def ema_color(value: int, max_val: int = 1000) -> str:
    """Retourne un style CSS background+color pour un dégradé rouge→vert."""
    ratio = max(0.0, min(1.0, value / max_val))
    hue = ratio * 120           # 0 = rouge, 120 = vert
    bg  = f"hsl({hue:.0f}, 75%, 88%)"
    fg  = f"hsl({hue:.0f}, 60%, 30%)"
    return f"background:{bg}; color:{fg}; font-weight:600"

templates.env.filters["ema_color"] = ema_color


def fmt_date(iso: str) -> str:
    """YYYY-MM-DD → DD/MM/YYYY"""
    if not iso or len(iso) < 10:
        return iso or ""
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"

templates.env.filters["fmt_date"] = fmt_date

# Corrections d'accents sur les prénoms courants
_ACCENTS = {
    "loic": "Loïc", "loïc": "Loïc",
    "noel": "Noël", "noël": "Noël",
    "helene": "Hélène", "hélène": "Hélène",
    "eugene": "Eugène", "eugène": "Eugène",
    "jerome": "Jérôme", "jérôme": "Jérôme",
    "remi": "Rémi", "rémi": "Rémi",
    "remy": "Rémy", "rémy": "Rémy",
    "cedric": "Cédric", "cédric": "Cédric",
    "valerie": "Valérie", "valérie": "Valérie",
    "emilie": "Émilie", "émilie": "Émilie",
    "emile": "Émile", "émile": "Émile",
    "elodie": "Élodie", "élodie": "Élodie",
    "eloise": "Éloïse", "éloïse": "Éloïse",
    "stephanie": "Stéphanie", "stéphanie": "Stéphanie",
    "stephane": "Stéphane", "stéphane": "Stéphane",
    "frederique": "Frédérique", "frédérique": "Frédérique",
    "frederic": "Frédéric", "frédéric": "Frédéric",
    "francois": "François", "françois": "François",
    "francoise": "Françoise", "françoise": "Françoise",
    "gael": "Gaël", "gaël": "Gaël",
    "gaelle": "Gaëlle", "gaëlle": "Gaëlle",
    "noemie": "Noémie", "noémie": "Noémie",
    "berenice": "Bérénice",
    "therese": "Thérèse",
    "veronique": "Véronique",
    "aurelie": "Aurélie",
    "amelie": "Amélie",
    "perrine": "Perrine",
    "matthieu": "Matthieu",
    "benoit": "Benoît",
    "herve": "Hervé",
    "andre": "André",
    "adele": "Adèle",
    "manoel": "Manoël",
}

def prenom_propre(s: str) -> str:
    """Titre-case + corrections d'accents pour les prénoms."""
    if not s:
        return s
    mots = s.strip().title().split()
    result = []
    for mot in mots:
        key = mot.lower()
        result.append(_ACCENTS.get(key, mot))
    return " ".join(result)

templates.env.filters["prenom"] = prenom_propre
