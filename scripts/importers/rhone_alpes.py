"""
Import du Championnat Rhône-Alpes MCR 2025-2026.

Données : 5 tournois passés, scraped depuis mahjongclubdurhone.fr
Formule classement : moyenne des 3 meilleurs rankings EMA (gradient 0-1000)

Mapping nom/prénom → joueur_id EMA (correspondance manuelle vérifiée).
Les joueurs sans EMA connu sont insérés en resultats_anonymes.
"""

import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.models import (
    ChampionnatTournoi, Joueur, Resultat, ResultatAnonyme,
    SerieChampionnat, Championnat, Tournoi,
)
from app.ranking import points_ema_tournoi

db = SessionLocal()

# ---------------------------------------------------------------------------
# 1. Série et édition
# ---------------------------------------------------------------------------

serie = db.query(SerieChampionnat).filter_by(slug="rhone-alpes-mcr").first()
if not serie:
    serie = SerieChampionnat(
        slug="rhone-alpes-mcr",
        nom="Championnat Rhône-Alpes MCR",
        regles="MCR",
        pays="FR",
        description="Circuit régional Rhône-Alpes, organisé par le Mahjong Club du Rhône.",
    )
    db.add(serie)
    db.flush()
    print(f"Série créée : {serie.nom}")
else:
    print(f"Série existante : {serie.nom}")

edition = db.query(Championnat).filter_by(serie_id=serie.id, annee=2026).first()
if not edition:
    edition = Championnat(
        serie_id=serie.id,
        annee=2026,
        nom="Championnat Rhône-Alpes MCR 2025-2026",
        formule="moyenne_n_meilleurs",
        params=json.dumps({"n": 3}),
    )
    db.add(edition)
    db.flush()
    print(f"Édition créée : {edition.nom}")
else:
    print(f"Édition existante : {edition.nom}")

# ---------------------------------------------------------------------------
# 2. Mapping nom → joueur_id EMA
#    Format : "PRENOM NOM" (site) → joueur_id (DB)
#    None = joueur sans EMA connu → resultats_anonymes
# ---------------------------------------------------------------------------

MAPPING: dict[str, str | None] = {
    # Joueurs identifiés en base
    "Sandra BERTHOMMIER":           "04290001",
    "Lina PICH":                    "04290021",
    "Sarah CHANRION":               None,           # pas trouvé en base
    "Catherine EBLE":               "04010055",
    "Olivier BOIVIN":               "04040010",
    "Élise TAPONIER":               "04040122",
    "Elise TAPONIER":               "04040122",
    "Antoine MEUNIER":              None,           # pas trouvé (plusieurs Meunier ?)
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
# 3. Données des tournois
# ---------------------------------------------------------------------------

TOURNOIS = [
    {
        "nc": 6836,
        "nom": "Championnat Rhône-Alpes MCR (1)",
        "lieu": "Lyon",
        "date_debut": "2025-10-25",
        "date_fin":   "2025-10-25",
        "resultats": [
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
        "nom": "Championnat Rhône-Alpes MCR (2)",
        "lieu": "Villefranche",
        "date_debut": "2025-12-06",
        "date_fin":   "2025-12-06",
        "resultats": [
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
        "nom": "Championnat Rhône-Alpes MCR (3)",
        "lieu": "Valence",
        "date_debut": "2026-01-10",
        "date_fin":   "2026-01-10",
        "resultats": [
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
        "nom": "Championnat Rhône-Alpes MCR (4)",
        "lieu": "Annecy",
        "date_debut": "2026-02-14",
        "date_fin":   "2026-02-14",
        "resultats": [
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
        "nom": "Championnat Rhône-Alpes MCR (5)",
        "lieu": "Valence",
        "date_debut": "2026-04-18",
        "date_fin":   "2026-04-18",
        "resultats": [
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
    nb = len(t_data["resultats"])

    # Créer ou retrouver le tournoi
    tournoi = db.query(Tournoi).filter_by(
        nom=t_data["nom"], pays="FR"
    ).first()
    if not tournoi:
        tournoi = Tournoi(
            ema_id=None,
            regles="MCR",
            nom=t_data["nom"],
            lieu=t_data["lieu"],
            pays="FR",
            date_debut=_date.fromisoformat(t_data["date_debut"]),
            date_fin=_date.fromisoformat(t_data["date_fin"]),
            nb_joueurs=nb,
            coefficient=0.0,
            type_tournoi="normal",
            statut="actif",
            approbation=None,
        )
        db.add(tournoi)
        db.flush()
        print(f"\nTournoi créé : [{tournoi.id}] {tournoi.nom}")
    else:
        print(f"\nTournoi existant : [{tournoi.id}] {tournoi.nom}")
        # Nettoyer les anciens résultats pour ré-import propre
        db.query(Resultat).filter_by(tournoi_id=tournoi.id).delete()
        db.query(ResultatAnonyme).filter_by(tournoi_id=tournoi.id).delete()

    # Lier au championnat
    lien = db.query(ChampionnatTournoi).filter_by(
        championnat_id=edition.id, tournoi_id=tournoi.id
    ).first()
    if not lien:
        db.add(ChampionnatTournoi(championnat_id=edition.id, tournoi_id=tournoi.id))

    # Insérer les résultats
    nb_identifies = 0
    nb_anonymes = 0
    for pos, nom_site, mahjong, points in t_data["resultats"]:
        ranking = points_ema_tournoi(pos, nb)
        joueur_id = MAPPING.get(nom_site)

        if joueur_id:
            joueur = db.query(Joueur).filter_by(id=joueur_id).first()
            if joueur:
                db.add(Resultat(
                    tournoi_id=tournoi.id,
                    joueur_id=joueur_id,
                    position=pos,
                    points=points,
                    mahjong=mahjong,
                    ranking=ranking,
                    nationalite=joueur.nationalite,
                ))
                nb_identifies += 1
            else:
                print(f"  WARN: joueur_id {joueur_id} introuvable pour {nom_site}")
                joueur_id = None

        if not joueur_id:
            parts = nom_site.split(" ", 1)
            prenom = parts[0] if len(parts) > 1 else ""
            nom_famille = parts[1] if len(parts) > 1 else nom_site
            db.add(ResultatAnonyme(
                tournoi_id=tournoi.id,
                position=pos,
                nationalite="FR",
                prenom=prenom,
                nom=nom_famille,
            ))
            nb_anonymes += 1

    print(f"  {nb_identifies} identifiés, {nb_anonymes} anonymes")

db.commit()
db.close()
print("\nImport terminé.")
