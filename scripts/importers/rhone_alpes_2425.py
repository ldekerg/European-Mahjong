"""
Import Championship Rhône-Alpes MCR 2024-2025.
6 tournois : Cityfranche(1), Valence(2), Lyon(3), Valence(4), Cityfranche(5), Lyon(6)
Formule : moyenne des 3 meilleurs rankings EMA.
"""

import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import date as _date
from app.database import SessionLocal
from app.models import (
    ChampionshipTournament, Player, Result, AnonymousResult,
    ChampionshipSeries, Championship, Tournament,
)
from app.ranking import ema_points

db = SessionLocal()

# ---------------------------------------------------------------------------
# 1. Series (existing) + new 2025 edition
# ---------------------------------------------------------------------------

serie = db.query(ChampionshipSeries).filter_by(slug="rhone-alpes-mcr").first()
if not serie:
    serie = ChampionshipSeries(
        slug="rhone-alpes-mcr",
        name="Championship Rhône-Alpes MCR",
        rules="MCR",
        country="FR",
        description="Championship régional Rhône-Alpes MCR",
    )
    db.add(serie)
    db.flush()
print(f"Série : {serie.name}")

edition = db.query(Championship).filter_by(series_id=serie.id, year=2025).first()
if not edition:
    edition = Championship(
        series_id=serie.id,
        year=2025,
        name="Championship Rhône-Alpes MCR 2024-2025",
        formula="moyenne_n_meilleurs",
        params=json.dumps({"n": 3}),
    )
    db.add(edition)
    db.flush()
    print(f"Édition créée : {edition.name}")
else:
    print(f"Édition existante : {edition.name}")

# ---------------------------------------------------------------------------
# 2. Name → player_id mapping (extends the existing mapping)
# ---------------------------------------------------------------------------

MAPPING: dict[str, str | None] = {
    "Frédéric PETIT":          "04040189",
    "Gerald VLAMYNCK":         "04040243",
    "Loïc DE KERGOMMEAUX":     "04290031",
    "Damien CHAREYRE":         "04410015",
    "Olivier BOIVIN":          "04040010",
    "Thibaut ARNOLD":          "16000035",
    "Olivier DEPRAZ":          "04290052",
    "Emilie GODFRIN":          "04290038",
    "Lina PICH":               "04290021",
    "Pascal BALANDRAS":        "04460017",
    "Claude VACHER":           None,
    "Jean-François PARRIAUD":  "04290008",
    "Séphora MABANDELA":       "04260038",
    "Marion HOARAU":           "04090055",
    "Thierry CHARVIN":         "04460016",
    "Fabienne RENEAUD":        None,
    "Pascale MARTINET":        "04290029",
    "Gabriel BALAVOINE":       None,
    "Emmanuelle HUGOT":        "04290006",
    "Isabelle SANTOS":         "04290026",
    "Manuel SANTOS":           "04290023",
    "Erwan DE KERGOMMEAUX":    "04290030",
    "Laurence CAHAGNE":        None,
    "Élise TAPONIER":          "04040122",
    "Eric DESBENOIT":          None,
    "Nathalie DUCROUX":        "04460003",
    "Pierre-Alain LEROY":      None,
    "Catherine CHAPUY":        "04460018",
    "Cyrille RAK":             "04090026",
    "Agnès RAK":               "04090016",
    "Wilson JANAC":            "04030091",
    "Sylvie CHHOR":            None,
    "Catherine EBLE":          "04010055",
    "Christian GORKA":         "04430029",
    "Nicolas BAPTISTE":        "04410014",
    "Nacera GUEBLI":           "04430030",
    "Annie-Claude BONNOT":     None,
    "Théophile PETIT":         None,
    "Monika LESUEUR":          "04420004",
    "Yvette NOUVEL":           "04420002",
    "Célia LICIN":             None,
    "Catherine GOYARD":        None,
    "Morgane DE KERGOMMEAUX":  "04290056",
    "Philippe EBLE":           "04010054",
    "Francoise MIOULANE":      None,
    "Kim Mai LUU DUC":         None,
    "Sandra BERTHOMMIER":      "04290001",
    "Pierre CLOAREC":          None,
    "Antoine MEUNIER":         None,
    "Didier CAVALLI":          None,
    "Wilson JANAC":            "04030091",
}

# ---------------------------------------------------------------------------
# 3. Tournaments
# ---------------------------------------------------------------------------

TOURNOIS = [
    {
        "name": "Cityfranche - Championship Rhône-Alpes 2024-2025 (1)",
        "city": "Cityfranche",
        "start_date": "2024-10-26",
        "end_date":   "2024-10-26",
        "results": [
            (1,  "Frédéric PETIT",           16,  859),
            (2,  "Gerald VLAMYNCK",          16,  526),
            (3,  "Loïc DE KERGOMMEAUX",      14,  408),
            (4,  "Damien CHAREYRE",          10,  196),
            (5,  "Olivier BOIVIN",            9,  289),
            (6,  "Thibaut ARNOLD",            9,  152),
            (7,  "Olivier DEPRAZ",            9,  108),
            (8,  "Emilie GODFRIN",            9,   56),
            (9,  "Lina PICH",                 8,  272),
            (10, "Pascal BALANDRAS",          8,  141),
            (11, "Claude VACHER",             8,   55),
            (12, "Jean-François PARRIAUD",    8, -156),
            (13, "Séphora MABANDELA",         7, -270),
            (14, "Marion HOARAU",             6,  -31),
            (15, "Thierry CHARVIN",           6,  -50),
            (16, "Fabienne RENEAUD",          6, -206),
            (17, "Pascale MARTINET",          5,   28),
            (18, "Gabriel BALAVOINE",         5,  -65),
            (19, "Emmanuelle HUGOT",          5,  -69),
            (20, "Isabelle SANTOS",           5, -240),
            (21, "Manuel SANTOS",             4, -103),
            (22, "Erwan DE KERGOMMEAUX",      4, -129),
            (23, "Laurence CAHAGNE",          4, -161),
            (24, "Élise TAPONIER",            4, -222),
            (25, "Eric DESBENOIT",            3, -222),
            (26, "Nathalie DUCROUX",          3, -354),
            (27, "Pierre-Alain LEROY",        3, -385),
            (28, "Catherine CHAPUY",          2, -427),
        ],
    },
    {
        "name": "Valence - Championship Rhône-Alpes 2024-2025 (2)",
        "city": "Valence",
        "start_date": "2024-12-14",
        "end_date":   "2024-12-14",
        "results": [
            (1,  "Cyrille RAK",              12,  393),
            (2,  "Manuel SANTOS",            12,  383),
            (3,  "Agnès RAK",                12,  370),
            (4,  "Wilson JANAC",             10,  365),
            (5,  "Erwan DE KERGOMMEAUX",     10,  349),
            (6,  "Sylvie CHHOR",             10,  138),
            (7,  "Isabelle SANTOS",          10,   36),
            (8,  "Catherine EBLE",            8,   -2),
            (9,  "Eric DESBENOIT",            7,  162),
            (10, "Marion HOARAU",             7,   69),
            (11, "Sandra BERTHOMMIER",        7,   51),
            (12, "Christian GORKA",           7,   37),
            (13, "Fabienne RENEAUD",          7,   23),
            (14, "Élise TAPONIER",            7,   -8),
            (15, "Jean-François PARRIAUD",    7, -157),
            (16, "Nicolas BAPTISTE",          6,   62),
            (17, "Emilie GODFRIN",            6,  -12),
            (18, "Laurence CAHAGNE",          5, -359),
            (19, "Lina PICH",                 4, -202),
            (20, "Loïc DE KERGOMMEAUX",       4, -221),
            (21, "Damien CHAREYRE",           3, -106),
            (22, "Théophile PETIT",           3, -329),
            (23, "Séphora MABANDELA",         2, -468),
            (24, "Annie-Claude BONNOT",       0, -555),
        ],
    },
    {
        "name": "Lyon - Championship Rhône-Alpes 2024-2025 (3)",
        "city": "Lyon",
        "start_date": "2025-02-08",
        "end_date":   "2025-02-08",
        "results": [
            (1,  "Élise TAPONIER",           16,  678),
            (2,  "Emmanuelle HUGOT",         11,  481),
            (3,  "Frédéric PETIT",           10,  216),
            (4,  "Jean-François PARRIAUD",   10,  162),
            (5,  "Olivier DEPRAZ",           10,   93),
            (6,  "Wilson JANAC",              9,  316),
            (7,  "Loïc DE KERGOMMEAUX",       9,  239),
            (8,  "Isabelle SANTOS",           9,  192),
            (9,  "Olivier BOIVIN",            9,  118),
            (10, "Nathalie DUCROUX",          9,  100),
            (11, "Pascal BALANDRAS",          7,   65),
            (12, "Monika LESUEUR",            7,   60),
            (13, "Lina PICH",                 7,   12),
            (14, "Yvette NOUVEL",             7, -140),
            (15, "Emilie GODFRIN",            6,   -6),
            (16, "Christian GORKA",           6, -132),
            (17, "Eric DESBENOIT",            6, -142),
            (18, "Claude VACHER",             5,   32),
            (19, "Célia LICIN",               5, -216),
            (20, "Fabienne RENEAUD",          3, -417),
            (21, "Sandra BERTHOMMIER",        2, -355),
            (22, "Laurence CAHAGNE",          2, -362),
            (23, "Catherine GOYARD",          2, -572),
            (24, "Morgane DE KERGOMMEAUX",    1, -422),
        ],
    },
    {
        "name": "Valence - Championship Rhône-Alpes 2024-2025 (4)",
        "city": "Valence",
        "start_date": "2025-04-26",
        "end_date":   "2025-04-26",
        "results": [
            (1,  "Isabelle SANTOS",           12,  306),
            (2,  "Olivier DEPRAZ",            11,  719),
            (3,  "Catherine CHAPUY",          11,  344),
            (4,  "Pascal BALANDRAS",          11,  227),
            (5,  "Nacera GUEBLI",             11,  179),
            (6,  "Sandra BERTHOMMIER",        10,  483),
            (7,  "Damien CHAREYRE",           10,  391),
            (8,  "Sylvie CHHOR",              10,  117),
            (9,  "Élise TAPONIER",             9,  185),
            (10, "Célia LICIN",                8,  -36),
            (11, "Lina PICH",                  8,  -46),
            (12, "Philippe EBLE",              8,  -69),
            (13, "Christian GORKA",            8,  -75),
            (14, "Wilson JANAC",               7,   64),
            (15, "Loïc DE KERGOMMEAUX",        7,   61),
            (16, "Erwan DE KERGOMMEAUX",       7,   43),
            (17, "Eric DESBENOIT",             7,   40),
            (18, "Manuel SANTOS",              6,  -84),
            (19, "Francoise MIOULANE",         5, -217),
            (20, "Alvin Et Luc KUNG-CALARESU", 5, -312),  # anonyme
            (21, "Claude VACHER",              5, -361),
            (22, "Kim Mai LUU DUC",            4, -142),
            (23, "Thierry CHARVIN",            4, -320),
            (24, "Pascale MARTINET",           3, -197),
            (25, "Nathalie DUCROUX",           3, -285),
            (26, "Laurence CAHAGNE",           3, -332),
            (27, "Annie-Claude BONNOT",        2, -325),
            (28, "Catherine EBLE",             1, -358),
        ],
    },
    {
        "name": "Cityfranche - Championship Rhône-Alpes 2024-2025 (5)",
        "city": "Cityfranche",
        "start_date": "2025-05-24",
        "end_date":   "2025-05-24",
        "results": [
            (1,  "Nacera GUEBLI",            16,  330),
            (2,  "Loïc DE KERGOMMEAUX",      14,  523),
            (3,  "Jean-François PARRIAUD",   11,  303),
            (4,  "Wilson JANAC",              9,  340),
            (5,  "Catherine CHAPUY",          9,  139),
            (6,  "Frédéric PETIT",            8,  176),
            (7,  "Manuel SANTOS",             8,  108),
            (8,  "Sandra BERTHOMMIER",        8,   70),
            (9,  "Lina PICH",                 8,   54),
            (10, "Nathalie DUCROUX",          8,   15),
            (11, "Emmanuelle HUGOT",          8,   14),
            (12, "Séphora MABANDELA",         7,   94),
            (13, "Emilie GODFRIN",            7,   31),
            (14, "Erwan DE KERGOMMEAUX",      7,   -1),
            (15, "Isabelle SANTOS",           6,   40),
            (16, "Olivier DEPRAZ",            6,  -31),
            (17, "Pierre CLOAREC",            6, -142),
            (18, "Pascal BALANDRAS",          5,   22),
            (19, "Antoine MEUNIER",           5,  -71),
            (20, "Pascale MARTINET",          4, -395),
            (21, "Didier CAVALLI",            3, -390),
            (22, "Claude VACHER",             3, -484),
            (23, "Christian GORKA",           1, -283),
            (24, "Annie-Claude BONNOT",       1, -472),
        ],
    },
    {
        "name": "Lyon - Championship Rhône-Alpes 2024-2025 (6)",
        "city": "Lyon",
        "start_date": "2025-06-28",
        "end_date":   "2025-06-28",
        "results": [
            (1,  "Loïc DE KERGOMMEAUX",      13,  495),
            (2,  "Emmanuelle HUGOT",         12,  192),
            (3,  "Olivier DEPRAZ",           11,  338),
            (4,  "Jean-François PARRIAUD",   10,  140),
            (5,  "Lina PICH",                 8,  171),
            (6,  "Gabriel BALAVOINE",         8,  -43),
            (7,  "Sandra BERTHOMMIER",        7,  239),
            (8,  "Nicolas BAPTISTE",          7,  216),
            (9,  "Emilie GODFRIN",            7,  -89),
            (10, "Antoine MEUNIER",           7, -133),
            (11, "Élise TAPONIER",            6,   45),
            (12, "Frédéric PETIT",            5,  -85),
            (13, "Pascale MARTINET",          4, -270),
            (14, "Eric DESBENOIT",            4, -277),
            (15, "Catherine CHAPUY",          3, -323),
            (16, "Annie-Claude BONNOT",       0, -636),
        ],
    },
]

# ---------------------------------------------------------------------------
# 4. Import
# ---------------------------------------------------------------------------

for t_data in TOURNOIS:
    nb = len(t_data["results"])
    tournoi = db.query(Tournament).filter_by(name=t_data["name"], country="FR").first()
    if not tournoi:
        tournoi = Tournament(
            ema_id=None, rules="MCR",
            name=t_data["name"], city=t_data["city"], country="FR",
            start_date=_date.fromisoformat(t_data["start_date"]),
            end_date=_date.fromisoformat(t_data["end_date"]),
            nb_players=nb, coefficient=0.0,
            tournament_type="normal", status="actif", approval=None,
        )
        db.add(tournoi)
        db.flush()
        print(f"\nTournament créé : [{tournoi.id}] {tournoi.name}")
    else:
        print(f"\nTournament existant : [{tournoi.id}] {tournoi.name}")
        db.query(Result).filter_by(tournament_id=tournoi.id).delete()
        db.query(AnonymousResult).filter_by(tournament_id=tournoi.id).delete()

    # Lier city
    from app.models import City
    v = db.query(City).filter_by(name=tournoi.city, country="FR").first()
    if not v:
        v = db.query(City).filter(City.name.like(f"%{tournoi.city}%")).first()
    if v:
        tournoi.city_id = v.id

    lien = db.query(ChampionshipTournament).filter_by(
        championship_id=edition.id, tournament_id=tournoi.id
    ).first()
    if not lien:
        db.add(ChampionshipTournament(championship_id=edition.id, tournament_id=tournoi.id))

    nb_id = nb_anon = 0
    for pos, nom_site, points, mahjong in t_data["results"]:
        ranking = ema_points(pos, nb)
        player_id = MAPPING.get(nom_site)

        if player_id:
            joueur = db.query(Player).filter_by(id=player_id).first()
            if joueur:
                db.add(Result(
                    tournament_id=tournoi.id, player_id=player_id,
                    position=pos, points=points, mahjong=mahjong,
                    ranking=ranking, nationality=joueur.nationality,
                ))
                nb_id += 1
                continue
            print(f"  WARN: {player_id} introuvable pour {nom_site}")

        parts = nom_site.split(" ", 1)
        db.add(AnonymousResult(
            tournament_id=tournoi.id, position=pos, nationality="FR",
            last_name=parts[0], first_name=parts[1] if len(parts) > 1 else "",
        ))
        nb_anon += 1

    print(f"  {nb_id} identifiés, {nb_anon} anonymes")

db.commit()
db.close()
print("\nImport Rhône-Alpes 2024-2025 terminé.")
