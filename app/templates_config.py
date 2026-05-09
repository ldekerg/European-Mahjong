import os, json
from markupsafe import Markup
from fastapi.templating import Jinja2Templates
from fastapi import Request

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_LOCALES_DIR   = os.path.join(os.path.dirname(__file__), "..", "locales")

# Chargement des catalogues de traduction
_LOCALES: dict[str, dict] = {}
for _fname in sorted(os.listdir(_LOCALES_DIR)):
    if _fname.endswith(".json"):
        _lang = _fname[:-5]
        with open(os.path.join(_LOCALES_DIR, _fname), encoding="utf-8") as _f:
            _LOCALES[_lang] = json.load(_f)

SUPPORTED_LANGS = list(_LOCALES.keys())
DEFAULT_LANG = "fr"


def _detect_lang(request: Request) -> str:
    """Priorité : cookie lang → Accept-Language → défaut."""
    # 1. Cookie
    lang = request.cookies.get("lang", "").lower()[:2]
    if lang in _LOCALES:
        return lang
    # 2. Accept-Language header
    accept = request.headers.get("accept-language", "")
    for part in accept.replace(" ", "").split(","):
        code = part.split(";")[0].split("-")[0].lower()
        if code in _LOCALES:
            return code
    return DEFAULT_LANG


def trad(key: str, lang: str, **kwargs) -> str:
    """Résout 'section.clé' dans le catalogue de la langue donnée."""
    catalogue = _LOCALES.get(lang, _LOCALES.get(DEFAULT_LANG, {}))
    parts = key.split(".")
    val = catalogue
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p, key)
        else:
            return key
    if not isinstance(val, str):
        return key
    # Interpolation simple {n}, {x}, etc.
    if kwargs:
        try:
            val = val.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return val


templates = Jinja2Templates(directory=_TEMPLATES_DIR)

# Injecter la fonction t() et la langue dans tous les contextes Jinja2
_orig_response = templates.TemplateResponse

def _patched_response(request_or_name, *args, **kwargs):
    # Compatibilité avec les deux signatures (request, name, context) et (name, context, request)
    if isinstance(request_or_name, Request):
        request = request_or_name
        name = args[0]
        context = args[1] if len(args) > 1 else kwargs.get("context", {})
    else:
        name = request_or_name
        context = args[0] if args else {}
        request = context.get("request") or kwargs.get("request")

    lang = _detect_lang(request) if request else DEFAULT_LANG
    context["lang"] = lang
    context["trad"] = lambda key, **kw: trad(key, lang, **kw)

    if isinstance(request_or_name, Request):
        return _orig_response(request, name, context, **{k: v for k, v in kwargs.items() if k not in ("context",)})
    return _orig_response(request_or_name, context, **kwargs)

templates.TemplateResponse = _patched_response


def _to_iso(value: str) -> str | None:
    """Résout un code ISO ou un nom de pays → code ISO 2 lettres, ou None."""
    if not value:
        return None
    v = value.strip()
    if len(v) == 2:
        return v.upper()
    return _PAYS_ISO.get(v.lower())


def flag_emoji(value: str) -> str:
    """Code ISO 2 lettres OU nom de pays → emoji drapeau. Guest → 🌍"""
    if not value:
        return ""
    if value.upper() in ("GUEST", "OTHER", "XX"):
        return "🌍"
    iso = _to_iso(value) or (value.upper()[:2] if len(value) >= 2 else "")
    if not iso or len(iso) < 2:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso[:2])


PAYS_EMA = {
    'FR','DE','NL','BE','LU','GB','IE','ES','PT','IT','AT','CH','DK','SE','NO','FI',
    'PL','CZ','SK','HU','RO','UA','EE','LV','LT','HR','SI','RS','BG','GR','TR',
    'RU','BY','IL','MK','MD','AL','ME','BA',
}


def flag_link(value: str, onglet: str = "joueurs") -> Markup:
    """Code ISO OU nom de pays → drapeau cliquable (EMA uniquement) vers /pays/{ISO}?onglet=X."""
    if not value or value.upper() in ("GUEST", "OTHER", "XX"):
        return Markup(flag_emoji(value))
    iso = _to_iso(value)
    if not iso:
        return Markup(flag_emoji(value))
    emoji = flag_emoji(iso)
    if iso not in PAYS_EMA:
        return Markup(emoji)
    url = f"/pays/{iso}?onglet={onglet}"
    return Markup(f'<a href="{url}" title="{value}" onclick="event.stopPropagation()">{emoji}</a>')


templates.env.filters["flag"]      = flag_emoji
templates.env.filters["flag_link"] = flag_link

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

# Alias rétrocompatibles — même comportement que flag / flag_link
templates.env.filters["pays_flag"]      = flag_emoji
templates.env.filters["pays_flag_link"] = flag_link


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
