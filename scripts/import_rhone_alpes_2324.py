"""
Import Championnat Rhône-Alpes MCR 2023-2024.
6 tournois : 3 amicaux (Villefranche/Valence/Lyon) + 3 numérotés (4/6, 5/6, 6/6)
"""

import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date as _date
from database import SessionLocal
from models import (
    ChampionnatTournoi, Joueur, Resultat, ResultatAnonyme,
    SerieChampionnat, Championnat, Tournoi, Ville,
)
from ranking import points_ema_tournoi

db = SessionLocal()

serie = db.query(SerieChampionnat).filter_by(slug="rhone-alpes-mcr").first()
print(f"Série : {serie.nom}")

edition = db.query(Championnat).filter_by(serie_id=serie.id, annee=2024).first()
if not edition:
    edition = Championnat(
        serie_id=serie.id,
        annee=2024,
        nom="Championnat Rhône-Alpes MCR 2023-2024",
        formule="moyenne_n_meilleurs",
        params=json.dumps({"n": 3}),
    )
    db.add(edition)
    db.flush()
    print(f"Édition créée : {edition.nom}")
else:
    print(f"Édition existante : {edition.nom}")

MAPPING: dict[str, str | None] = {
    "CHARVIN Thierry":          "04460016",
    "BOIVIN Olivier":           "04040010",
    "SANTOS Manuel":            "04290023",
    "SANTOS Isabelle":          "04290026",
    "HALTER Pascal":            None,
    "CHHOR Sylvie":             None,
    "DE KERGOMMEAUX Erwan":     "04290030",
    "PICH Lina":                "04290021",
    "GODFRIN Emilie":           "04290038",
    "DE KERGOMMEAUX Loïc":      "04290031",
    "CHAREYRE Damien":          "04410015",
    "HUGOT Emmanuelle":         "04290006",
    "BERTHOMMIER Sandra":       "04290001",
    "CAVALLI Didier":           None,
    "MARTINET Pascale":         "04290029",
    "LAUVERNIER Francoise":     None,
    "TAPONIER Élise":           "04040122",
    "BAPTISTE Nicolas":         "04410014",
    "APFFEL Clément":           None,
    "CHAPUY Catherine":         "04460018",
    "ZHAO Hang":                None,
    "DUCROUX Nathalie":         "04460003",
    "CLASERT Laurene":          "04410013",
    "DESBENOIT Eric":           None,
    "BALANDRAS Pascal":         "04460017",
    "QUESSON Caroline":         None,
    "PETIT Frederic":           "04040189",
    "LEROY Pierre-Alain":       None,
    "RENEAUD Fabienne":         None,
    "DEPRAZ Olivier":           "04290052",
    "WOLCZYK Patricia":         None,
    "TACHE Olivier":            "04280001",
    "MIOULANE Françoise":       None,
    "VACHER Claude":            None,
    "EBLE Catherine":           "04010055",
    "PARRIAUD Jean-François":   "04290008",
    "CHOLLEY Geneviéve":        None,
    "BERRET Sébastien":         None,
    "GORKA Christian":          "04430029",
    "CAHAGNE Laurence":         None,
}

TOURNOIS = [
    {
        "nom": "Championnat Rhône-Alpes 23/24 (1)",
        "lieu": "Villefranche",
        "date_debut": "2023-12-16",
        "date_fin":   "2023-12-16",
        "resultats": [
            (1,  "CHARVIN Thierry",         14,  483),
            (2,  "BOIVIN Olivier",          13,  474),
            (3,  "SANTOS Manuel",           10,  290),
            (4,  "SANTOS Isabelle",         10,  221),
            (5,  "HALTER Pascal",           10,  121),
            (6,  "CHHOR Sylvie",             9,   78),
            (7,  "DE KERGOMMEAUX Erwan",     8,  155),
            (8,  "PICH Lina",                8,   10),
            (9,  "GODFRIN Emilie",           7,   -9),
            (10, "DE KERGOMMEAUX Loïc",      6,   91),
            (11, "CHAREYRE Damien",          6,  -14),
            (12, "HUGOT Emmanuelle",         6,  -46),
            (13, "BERTHOMMIER Sandra",       6,  -67),
            (14, "CAVALLI Didier",           6, -183),
            (15, "MARTINET Pascale",         5, -126),
            (16, "LAUVERNIER Francoise",     4,    9),
            (17, "TAPONIER Élise",           4, -286),
            (18, "BAPTISTE Nicolas",         4, -307),
            (19, "APFFEL Clément",           3, -200),
            (20, "CHAPUY Catherine",         1, -694),
        ],
    },
    {
        "nom": "Championnat Rhône-Alpes 23/24 (2)",
        "lieu": "Valence",
        "date_debut": "2024-01-20",
        "date_fin":   "2024-01-20",
        "resultats": [
            (1,  "SANTOS Isabelle",         12,  263),
            (2,  "SANTOS Manuel",           11,  614),
            (3,  "HUGOT Emmanuelle",        11,  374),
            (4,  "DE KERGOMMEAUX Erwan",    10,  222),
            (5,  "CHAREYRE Damien",          9,  274),
            (6,  "BALANDRAS Pascal",         9,  186),
            (7,  "TAPONIER Élise",           8,  -18),
            (8,  "BAPTISTE Nicolas",         8,  -49),
            (9,  "CHHOR Sylvie",             7,  140),
            (10, "CHAPUY Catherine",         5, -113),
            (11, "ZHAO Hang",                5, -261),
            (12, "DE KERGOMMEAUX Loïc",      5, -294),
            (13, "PICH Lina",                4, -311),
            (14, "DUCROUX Nathalie",         4, -368),
            (15, "CLASERT Laurene",          2, -266),
            (16, "MARTINET Pascale",         2, -393),
        ],
    },
    {
        "nom": "Championnat Rhône-Alpes 23/24 (3)",
        "lieu": "Lyon",
        "date_debut": "2024-03-02",
        "date_fin":   "2024-03-02",
        "resultats": [
            (1,  "CHHOR Sylvie",            13,  388),
            (2,  "BERTHOMMIER Sandra",      13,  315),
            (3,  "DE KERGOMMEAUX Erwan",    12,  802),
            (4,  "DESBENOIT Eric",          12,  652),
            (5,  "BAPTISTE Nicolas",        12,  650),
            (6,  "BOIVIN Olivier",          11,  297),
            (7,  "DE KERGOMMEAUX Loïc",     10,  483),
            (8,  "HUGOT Emmanuelle",         9,  258),
            (9,  "HALTER Pascal",            9,  131),
            (10, "CHAREYRE Damien",          8,   56),
            (11, "CHARVIN Thierry",          8, -109),
            (12, "SANTOS Isabelle",          7,   -9),
            (13, "DUCROUX Nathalie",         5, -121),
            (14, "BALAVOINE Gabriel",        5, -149),
            (15, "LEROY Pierre-Alain",       5, -234),
            (16, "RENEAUD Fabienne",         5, -251),
            (17, "SANTOS Manuel",            4, -277),
            (18, "QUESSON Caroline",         4, -493),
            (19, "MARTINET Pascale",         3, -301),
            (20, "CAVALLI Didier",           3, -350),
            (21, "PETIT Frederic",           3, -351),
            (22, "BALANDRAS Pascal",         3, -413),
            (23, "PICH Lina",                3, -499),
            (24, "CHAPUY Catherine",         1, -475),
        ],
    },
    {
        "nom": "Championnat Rhône-Alpes 23/24 (4)",
        "lieu": "Villefranche",
        "date_debut": "2024-04-13",
        "date_fin":   "2024-04-13",
        "resultats": [
            (1,  "BERTHOMMIER Sandra",      13,  835),
            (2,  "DE KERGOMMEAUX Loïc",     12,  796),
            (3,  "DEPRAZ Olivier",          12,  254),
            (4,  "SANTOS Isabelle",         10,  383),
            (5,  "TAPONIER Élise",          10,  256),
            (6,  "SANTOS Manuel",           10,  109),
            (7,  "ZHAO Hang",                9,  -13),
            (8,  "MARTINET Pascale",         9,  -36),
            (9,  "PICH Lina",                8,  171),
            (10, "BAPTISTE Nicolas",         8,   81),
            (11, "CHHOR Sylvie",             8, -128),
            (12, "BOIVIN Olivier",           7,  267),
            (13, "DUCROUX Nathalie",         7,  131),
            (14, "EBLE Catherine",           7,   33),
            (15, "BALANDRAS Pascal",         7,   15),
            (16, "WOLCZYK Patricia",         7, -241),
            (17, "TACHE Olivier",            6,  -61),
            (18, "CHARVIN Thierry",          6, -469),
            (19, "HALTER Pascal",            3,  -20),
            (20, "CHAREYRE Damien",          3, -249),
            (21, "MIOULANE Françoise",       2, -375),
            (22, "CHAPUY Catherine",         2, -517),
            (23, "VACHER Claude",            2, -639),
            (24, "CAVALLI Didier",           0, -583),
        ],
    },
    {
        "nom": "Championnat Rhône-Alpes 23/24 (5)",
        "lieu": "Valence",
        "date_debut": "2024-05-25",
        "date_fin":   "2024-05-25",
        "resultats": [
            (1,  "BOIVIN Olivier",          12,  727),
            (2,  "MARTINET Pascale",        12,  408),
            (3,  "PARRIAUD Jean-François",  12,  262),
            (4,  "DE KERGOMMEAUX Erwan",    11,  209),
            (5,  "SANTOS Manuel",           10,  402),
            (6,  "DE KERGOMMEAUX Loïc",     10,  361),
            (7,  "CHOLLEY Geneviéve",        9,  265),
            (8,  "BERRET Sébastien",         9,   87),
            (9,  "DEPRAZ Olivier",           8,   48),
            (10, "BAPTISTE Nicolas",         8,   27),
            (11, "BERTHOMMIER Sandra",       7,   44),
            (12, "CHAREYRE Damien",          5,  -17),
            (13, "CHAPUY Catherine",         5, -182),
            (14, "GORKA Christian",          5, -251),
            (15, "CHARVIN Thierry",          4, -197),
            (16, "CAHAGNE Laurence",         3, -320),
            (17, "SANTOS Isabelle",          3, -382),
            (18, "PICH Lina",                3, -509),
            (19, "EBLE Catherine",           2, -440),
            (20, "VACHER Claude",            2, -542),
        ],
    },
    {
        "nom": "Championnat Rhône-Alpes 23/24 (6)",
        "lieu": "Lyon",
        "date_debut": "2024-06-29",
        "date_fin":   "2024-06-29",
        "resultats": [
            (1,  "PARRIAUD Jean-François",  11,  264),
            (2,  "CHAPUY Catherine",        10,  308),
            (3,  "DE KERGOMMEAUX Loïc",     10,  154),
            (4,  "CHHOR Sylvie",            10,   92),
            (5,  "DE KERGOMMEAUX Erwan",     9,  235),
            (6,  "SANTOS Manuel",            9,  212),
            (7,  "DEPRAZ Olivier",           9,  137),
            (8,  "BOIVIN Olivier",           9,   86),
            (9,  "DESBENOIT Eric",           8,  270),
            (10, "HUGOT Emmanuelle",         8,   52),
            (11, "HALTER Pascal",            7,  -15),
            (12, "BERTHOMMIER Sandra",       6,   15),
            (13, "MARTINET Pascale",         6,  -80),
            (14, "BALANDRAS Pascal",         6, -161),
            (15, "TAPONIER Élise",           6, -200),
            (16, "PICH Lina",                5, -134),
            (17, "CHARVIN Thierry",          4,   11),
            (18, "GODFRIN Emilie",           3, -230),
            (19, "CAVALLI Didier",           3, -485),
            (20, "ZHAO Hang",                1, -531),
        ],
    },
]

for t_data in TOURNOIS:
    nb = len(t_data["resultats"])
    tournoi = db.query(Tournoi).filter_by(nom=t_data["nom"], pays="FR").first()
    if not tournoi:
        tournoi = Tournoi(
            ema_id=None, regles="MCR",
            nom=t_data["nom"], lieu=t_data["lieu"], pays="FR",
            date_debut=_date.fromisoformat(t_data["date_debut"]),
            date_fin=_date.fromisoformat(t_data["date_fin"]),
            nb_joueurs=nb, coefficient=0.0,
            type_tournoi="normal", statut="actif", approbation=None,
        )
        db.add(tournoi)
        db.flush()
        print(f"\nTournoi créé : [{tournoi.id}] {tournoi.nom}")
    else:
        print(f"\nTournoi existant : [{tournoi.id}] {tournoi.nom}")
        db.query(Resultat).filter_by(tournoi_id=tournoi.id).delete()
        db.query(ResultatAnonyme).filter_by(tournoi_id=tournoi.id).delete()

    v = db.query(Ville).filter_by(nom=tournoi.lieu, pays="FR").first()
    if not v:
        v = db.query(Ville).filter(Ville.nom.like(f"%{tournoi.lieu}%")).first()
    if v:
        tournoi.ville_id = v.id

    lien = db.query(ChampionnatTournoi).filter_by(
        championnat_id=edition.id, tournoi_id=tournoi.id
    ).first()
    if not lien:
        db.add(ChampionnatTournoi(championnat_id=edition.id, tournoi_id=tournoi.id))

    nb_id = nb_anon = 0
    for pos, nom_site, points, mahjong in t_data["resultats"]:
        ranking = points_ema_tournoi(pos, nb)
        joueur_id = MAPPING.get(nom_site)

        if joueur_id:
            joueur = db.query(Joueur).filter_by(id=joueur_id).first()
            if joueur:
                db.add(Resultat(
                    tournoi_id=tournoi.id, joueur_id=joueur_id,
                    position=pos, points=points, mahjong=mahjong,
                    ranking=ranking, nationalite=joueur.nationalite,
                ))
                nb_id += 1
                continue
            print(f"  WARN: {joueur_id} introuvable pour {nom_site}")

        parts = nom_site.split(" ", 1)
        db.add(ResultatAnonyme(
            tournoi_id=tournoi.id, position=pos, nationalite="FR",
            nom=parts[0], prenom=parts[1] if len(parts) > 1 else "",
        ))
        nb_anon += 1

    print(f"  {nb_id} identifiés, {nb_anon} anonymes")

db.commit()
db.close()
print("\nImport Rhône-Alpes 2023-2024 terminé.")
