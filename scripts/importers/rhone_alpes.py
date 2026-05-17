"""
Import du Championship Rhône-Alpes MCR 2025-2026.

Données : 5 tournois passés, scraped depuis mahjongclubdurhone.fr
Formule ranking : moyenne des 3 meilleurs rankings EMA (gradient 0-1000)

Mapping nom/prénom → player_id EMA (correspondance manuelle vérifiée).
Les joueurs sans EMA connu sont insérés en resultats_anonymes.
"""

import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import SessionLocal
from app.models import (
    ChampionshipTournament, Player, Result, AnonymousResult,
    ChampionshipSeries, Championship, Tournament,
)
from app.ranking import ema_points

db = SessionLocal()

# ---------------------------------------------------------------------------
# 1. Series and edition
# ---------------------------------------------------------------------------

serie = db.query(ChampionshipSeries).filter_by(slug="rhone-alpes-mcr").first()
if not serie:
    serie = ChampionshipSeries(
        slug="rhone-alpes-mcr",
        name="Championship Rhône-Alpes MCR",
        rules="MCR",
        country="FR",
        description="Circuit régional Rhône-Alpes, organisé par le Mahjong Club du Rhône.",
    )
    db.add(serie)
    db.flush()
    print(f"Série créée : {serie.name}")
else:
    print(f"Série existante : {serie.name}")

edition = db.query(Championship).filter_by(series_id=serie.id, year=2026).first()
if not edition:
    edition = Championship(
        series_id=serie.id,
        year=2026,
        name="Championship Rhône-Alpes MCR 2025-2026",
        formula="moyenne_n_meilleurs",
        params=json.dumps({"n": 3}),
    )
    db.add(edition)
    db.flush()
    print(f"Édition créée : {edition.name}")
else:
    print(f"Édition existante : {edition.name}")

# ---------------------------------------------------------------------------
# 2. Mapping nom → player_id EMA
#    Format : "PRENOM NOM" (site) → player_id (DB)
#    None = joueur sans EMA connu → resultats_anonymes
# ---------------------------------------------------------------------------

MAPPING: dict[str, str | None] = {
    # Players identified in database
    "Sandra BERTHOMMIER":           "04290001",
    "Lina PICH":                    "04290021",
    "Sarah CHANRION":               None,           # not found in database
    "Catherine EBLE":               "04010055",
    "Olivier BOIVIN":               "04040010",
    "Élise TAPONIER":               "04040122",
    "Elise TAPONIER":               "04040122",
    "Antoine MEUNIER":              None,           # not found (multiple Meunier?)
    "Olivier DEPRAZ":               "04290052",
    "Pascal BALANDRAS":             "04460017",
    "Kim Mai LUU DUC":              None,
    "Nathalie DUCROUX":             "04460003",
    "Sylvie CHHOR":                 None,
    "Annie-Claude BONNOT":          None,
    "Nacera GUEBLI":                "04430030",
    "Lise-Claire BERNAILLE":        None,
    "Alvin Eu Jin KUNG":            None,
    "Pascale MARTINET":             "04290029",
    "Jody LABEDAN":                 None,
    "Gabriel BALAVOINE":            None,
    "Fabienne RENEAUD":             None,
    "Gerald VLAMYNCK":              "04040243",
    "Loïc DE KERGOMMEAUX":          "04290031",
    "Thibaut ARNOLD":               "16000035",  # CH
    "Bruno DE AGUIAR":              "04280033",
    "Emilie GODFRIN":               "04290038",
    "Nicolas BAPTISTE":             "04410014",
    "Morgane DE KERGOMMEAUX":       "04290056",
    "Jean-François PARRIAUD":       "04290008",
    "Catherine CHAPUY":             "04460018",
    "Erwan DE KERGOMMEAUX":         "04290030",
    "Anne Sophie GROSSET":          None,
    "Emmanuelle HUGOT":             "04290006",
    "Frederic PETIT":               "04040189",
    "Frédéric PETIT":               "04040189",
    "Thierry CHARVIN":              "04460016",
    "Frédéric VERRIER":             None,
    "Nathalie ROBIN":               None,
    "Séphora MABANDELA":            "04260038",
    "Marie France LANDRIN MARAILLAC": None,
    "Zhishun XU":                   "04290037",
    "Jean François PARRIAUD":       "04290008",
    "Elisabeth REVOL":              None,
    "Thomas ROUSSEAU":              None,
    "Isabelle GATEAU":              None,
    "Laurence CAHAGNE":             None,
    "Marc-Antoine HOFMANN":         "16000021",  # CH
    "Marie-Claude ROLAND":          None,
    "Nathalie JACQUART":            "16000009",  # CH
    "Manuel SANTOS":                "04290023",
    "Kim Mai LUU DUC":              None,
    "Anne Sophie GROSSET":          None,
    "Jianmei TAO":                  "16000070",  # CH
    "Anna CANOVA PUTINIER":         "16000008",  # CH
    "Célia LICIN":                  None,
    "Isabelle SANTOS":              "04290026",
    "Nicole RIVET":                 None,
    "Christian GORKA":              "04430029",
    "Claude VACHER":                None,
    "Isabelle SANTOS":              "04290026",
    "Joëlle NICOLAS":               None,
    "Roland QUENTEL":               None,
    "Joëlle NICOLAS":               None,
    "Substitute 1":                 None,
}

# ---------------------------------------------------------------------------
# 3. Tournament data
# ---------------------------------------------------------------------------

TOURNOIS = [
    {
        "nc": 6836,
        "name": "Championship Rhône-Alpes MCR (1)",
        "city": "Lyon",
        "start_date": "2025-10-25",
        "end_date":   "2025-10-25",
        "results": [
            (1,  "Sandra BERTHOMMIER",           403,  12),
            (2,  "Lina PICH",                    353,  12),
            (3,  "Sarah CHANRION",                300,  11),
            (4,  "Catherine EBLE",                244,  11),
            (5,  "Olivier BOIVIN",                187,  10),
            (6,  "Élise TAPONIER",                398,   9),
            (7,  "Antoine MEUNIER",               132,   9),
            (8,  "Olivier DEPRAZ",                169,   8),
            (9,  "Pascal BALANDRAS",             -142,   7),
            (10, "Kim Mai LUU DUC",                93,   6),
            (11, "Nathalie DUCROUX",              -88,   6),
            (12, "Sylvie CHHOR",                 -152,   6),
            (13, "Annie-Claude BONNOT",           -161,   6),
            (14, "Nacera GUEBLI",                  15,   5),
            (15, "Lise-Claire BERNAILLE",         -146,   5),
            (16, "Alvin Eu Jin KUNG",             -217,   5),
            (17, "Pascale MARTINET",              -373,   5),
            (18, "Jody LABEDAN",                  -185,   4),
            (19, "Gabriel BALAVOINE",             -207,   2),
            (20, "Fabienne RENEAUD",              -545,   1),
        ],
    },
    {
        "nc": 6928,
        "name": "Championship Rhône-Alpes MCR (2)",
        "city": "Cityfranche",
        "start_date": "2025-12-06",
        "end_date":   "2025-12-06",
        "results": [
            (1,  "Gerald VLAMYNCK",               839,  16),
            (2,  "Olivier BOIVIN",                802,  16),
            (3,  "Loïc DE KERGOMMEAUX",           698,  14),
            (4,  "Nacera GUEBLI",                 265,  11),
            (5,  "Sandra BERTHOMMIER",            259,  11),
            (6,  "Thibaut ARNOLD",                254,  10),
            (7,  "Pascal BALANDRAS",              221,  10),
            (8,  "Bruno DE AGUIAR",               165,  10),
            (9,  "Emilie GODFRIN",                541,   9),
            (10, "Nicolas BAPTISTE",              227,   9),
            (11, "Olivier DEPRAZ",                -42,   9),
            (12, "Lina PICH",                     182,   8),
            (13, "Morgane DE KERGOMMEAUX",          -9,   8),
            (14, "Jean-François PARRIAUD",         103,   7),
            (15, "Nathalie DUCROUX",                33,   7),
            (16, "Catherine CHAPUY",               -99,   7),
            (17, "Antoine MEUNIER",               -253,   7),
            (18, "Erwan DE KERGOMMEAUX",            17,   6),
            (19, "Élise TAPONIER",                  -4,   6),
            (20, "Anne Sophie GROSSET",            -58,   6),
            (21, "Emmanuelle HUGOT",               -37,   5),
            (22, "Frederic PETIT",                -161,   4),
            (23, "Gabriel BALAVOINE",             -233,   4),
            (24, "Sarah CHANRION",                -235,   4),
            (25, "Thierry CHARVIN",               -257,   4),
            (26, "Jody LABEDAN",                  -389,   4),
            (27, "Frédéric VERRIER",              -421,   3),
            (28, "Nathalie ROBIN",                -572,   3),
            (29, "Lise-Claire BERNAILLE",          -232,   2),
            (30, "Annie-Claude BONNOT",            -425,   2),
            (31, "Séphora MABANDELA",             -559,   2),
            (32, "Marie France LANDRIN MARAILLAC", -620,   0),
        ],
    },
    {
        "nc": 6935,
        "name": "Championship Rhône-Alpes MCR (3)",
        "city": "Valence",
        "start_date": "2026-01-10",
        "end_date":   "2026-01-10",
        "results": [
            (1,  "Zhishun XU",                    939,  16),
            (2,  "Loïc DE KERGOMMEAUX",           468,  12),
            (3,  "Jean-François PARRIAUD",         316,  12),
            (4,  "Erwan DE KERGOMMEAUX",           405,  11),
            (5,  "Pascale MARTINET",               297,  11),
            (6,  "Gerald VLAMYNCK",                222,  10),
            (7,  "Olivier DEPRAZ",                 127,  10),
            (8,  "Sylvie CHHOR",                   209,   9),
            (9,  "Elisabeth REVOL",               -100,   8),
            (10, "Jody LABEDAN",                   126,   7),
            (11, "Annie-Claude BONNOT",              -2,   7),
            (12, "Emilie GODFRIN",                 -72,   7),
            (13, "Lina PICH",                     -215,   7),
            (14, "Lise-Claire BERNAILLE",            1,   6),
            (15, "Séphora MABANDELA",              -28,   6),
            (16, "Nathalie DUCROUX",               -47,   6),
            (17, "Alvin Eu Jin KUNG",             -148,   6),
            (18, "Nacera GUEBLI",                 -210,   6),
            (19, "Élise TAPONIER",                  69,   5),
            (20, "Thomas ROUSSEAU",               -100,   5),
            (21, "Pascal BALANDRAS",              -142,   5),
            (22, "Antoine MEUNIER",               -368,   5),
            (23, "Isabelle GATEAU",                -79,   4),
            (24, "Laurence CAHAGNE",              -196,   4),
            (25, "Frédéric VERRIER",              -257,   4),
            (26, "Sarah CHANRION",                -241,   3),
            (27, "Fabienne RENEAUD",              -549,   3),
            (28, "Catherine CHAPUY",              -425,   1),
        ],
    },
    {
        "nc": 6972,
        "name": "Championship Rhône-Alpes MCR (4)",
        "city": "Annecy",
        "start_date": "2026-02-14",
        "end_date":   "2026-02-14",
        "results": [
            (1,  "Gerald VLAMYNCK",               818,  16),
            (2,  "Marc-Antoine HOFMANN",           453,  12),
            (3,  "Frederic PETIT",                 349,  12),
            (4,  "Olivier BOIVIN",                 275,  11),
            (5,  "Erwan DE KERGOMMEAUX",           173,  11),
            (6,  "Marie-Claude ROLAND",            398,  10),
            (7,  "Jody LABEDAN",                   336,  10),
            (8,  "Nathalie JACQUART",              265,  10),
            (9,  "Lina PICH",                      160,  10),
            (10, "Manuel SANTOS",                  390,   9),
            (11, "Zhishun XU",                     273,   9),
            (12, "Nathalie DUCROUX",               245,   9),
            (13, "Loïc DE KERGOMMEAUX",            119,   9),
            (14, "Kim Mai LUU DUC",                200,   8),
            (15, "Nicolas BAPTISTE",               156,   8),
            (16, "Anne Sophie GROSSET",            114,   8),
            (17, "Jianmei TAO",                    253,   7),
            (18, "Jean-François PARRIAUD",           82,   7),
            (19, "Emilie GODFRIN",                -106,   7),
            (20, "Anna CANOVA PUTINIER",            -79,   6),
            (21, "Alvin Eu Jin KUNG",             -153,   6),
            (22, "Célia LICIN",                   -180,   6),
            (23, "Nacera GUEBLI",                    3,   5),
            (24, "Isabelle SANTOS",                -62,   5),
            (25, "Nicole RIVET",                  -246,   5),
            (26, "Christian GORKA",               -257,   5),
            (27, "Laurence CAHAGNE",              -439,   5),
            (28, "Pascal BALANDRAS",              -232,   4),
            (29, "Olivier DEPRAZ",                -270,   4),
            (30, "Séphora MABANDELA",             -275,   4),
            (31, "Annie-Claude BONNOT",            -371,   4),
            (32, "Antoine MEUNIER",               -266,   3),
            (33, "Isabelle GATEAU",               -333,   2),
            (34, "Claude VACHER",                 -531,   2),
            (35, "Morgane DE KERGOMMEAUX",         -613,   2),
            (36, "Elisabeth REVOL",               -548,   1),
        ],
    },
    {
        "nc": 6936,
        "name": "Championship Rhône-Alpes MCR (5)",
        "city": "Valence",
        "start_date": "2026-04-18",
        "end_date":   "2026-04-18",
        "results": [
            (1,  "Frederic PETIT",                548,  13),
            (2,  "Zhishun XU",                    520,  12),
            (3,  "Isabelle SANTOS",               392,  12),
            (4,  "Élise TAPONIER",                362,  12),
            (5,  "Annie-Claude BONNOT",            170,  12),
            (6,  "Nathalie DUCROUX",              207,  11),
            (7,  "Erwan DE KERGOMMEAUX",          355,  10),
            (8,  "Elisabeth REVOL",               392,   9),
            (9,  "Sandra BERTHOMMIER",            126,   8),
            (10, "Loïc DE KERGOMMEAUX",            66,   8),
            (11, "Jean-François PARRIAUD",          51,   8),
            (12, "Pascale MARTINET",                -2,   8),
            (13, "Lina PICH",                      171,   7),
            (14, "Olivier DEPRAZ",                 -21,   7),
            (15, "Séphora MABANDELA",              -23,   7),
            (16, "Sarah CHANRION",                 146,   6),
            (17, "Nacera GUEBLI",                   65,   6),
            (18, "Kim Mai LUU DUC",                 42,   6),
            (19, "Frédéric VERRIER",               -30,   6),
            (20, "Jody LABEDAN",                  -234,   6),
            (21, "Pascal BALANDRAS",              -209,   5),
            (22, "Lise-Claire BERNAILLE",          -365,   4),
            (23, "Laurence CAHAGNE",              -177,   3),
            (24, "Joëlle NICOLAS",                -425,   3),
            (25, "Roland QUENTEL",                -521,   3),
            (26, "Christian GORKA",               -300,   2),
            (27, "Antoine MEUNIER",               -517,   1),
            (28, "Substitute 1",                  -746,   1),
        ],
    },
]

# ---------------------------------------------------------------------------
# 4. Import
# ---------------------------------------------------------------------------

from datetime import date as _date

for t_data in TOURNOIS:
    nb = len(t_data["results"])

    # Create or retrieve the tournament
    tournoi = db.query(Tournament).filter_by(
        name=t_data["name"], country="FR"
    ).first()
    if not tournoi:
        tournoi = Tournament(
            ema_id=None,
            rules="MCR",
            name=t_data["name"],
            city=t_data["city"],
            country="FR",
            start_date=_date.fromisoformat(t_data["start_date"]),
            end_date=_date.fromisoformat(t_data["end_date"]),
            nb_players=nb,
            coefficient=0.0,
            tournament_type="normal",
            status="actif",
            approval=None,
        )
        db.add(tournoi)
        db.flush()
        print(f"\nTournament créé : [{tournoi.id}] {tournoi.name}")
    else:
        print(f"\nTournament existant : [{tournoi.id}] {tournoi.name}")
        # Clear old results for clean re-import
        db.query(Result).filter_by(tournament_id=tournoi.id).delete()
        db.query(AnonymousResult).filter_by(tournament_id=tournoi.id).delete()

    # Lier au championnat
    lien = db.query(ChampionshipTournament).filter_by(
        championship_id=edition.id, tournament_id=tournoi.id
    ).first()
    if not lien:
        db.add(ChampionshipTournament(championship_id=edition.id, tournament_id=tournoi.id))

    # Insert results
    nb_identifies = 0
    nb_anonymes = 0
    for pos, nom_site, mahjong, points in t_data["results"]:
        ranking = ema_points(pos, nb)
        player_id = MAPPING.get(nom_site)

        if player_id:
            joueur = db.query(Player).filter_by(id=player_id).first()
            if joueur:
                db.add(Result(
                    tournament_id=tournoi.id,
                    player_id=player_id,
                    position=pos,
                    points=points,
                    mahjong=mahjong,
                    ranking=ranking,
                    nationality=joueur.nationality,
                ))
                nb_identifies += 1
            else:
                print(f"  WARN: player_id {player_id} introuvable pour {nom_site}")
                player_id = None

        if not player_id:
            parts = nom_site.split(" ", 1)
            prenom = parts[0] if len(parts) > 1 else ""
            nom_famille = parts[1] if len(parts) > 1 else nom_site
            db.add(AnonymousResult(
                tournament_id=tournoi.id,
                position=pos,
                nationality="FR",
                first_name=prenom,
                last_name=nom_famille,
            ))
            nb_anonymes += 1

    print(f"  {nb_identifies} identifiés, {nb_anonymes} anonymes")

db.commit()
db.close()
print("\nImport terminé.")
