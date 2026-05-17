"""
Import Golden League MCR 2024-2025.
Source : mahjongclubdurhone.fr/championnat.php?id=6561
Formule : moyenne des 3 meilleurs rankings EMA (gradient 0-1000).
"""

import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date as _date
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

serie = db.query(SerieChampionnat).filter_by(slug="golden-league-mcr").first()
if not serie:
    serie = SerieChampionnat(
        slug="golden-league-mcr",
        nom="Golden League MCR",
        regles="MCR",
        pays="FR",
        description="Circuit national MCR, organisé par la Fédération française de Mahjong.",
    )
    db.add(serie)
    db.flush()
    print(f"Série créée : {serie.nom}")
else:
    print(f"Série existante : {serie.nom}")

edition = db.query(Championnat).filter_by(serie_id=serie.id, annee=2025).first()
if not edition:
    edition = Championnat(
        serie_id=serie.id,
        annee=2025,
        nom="Golden League MCR 2024-2025",
        formule="moyenne_n_meilleurs",
        params=json.dumps({"n": 3}),
    )
    db.add(edition)
    db.flush()
    print(f"Édition créée : {edition.nom}")
else:
    print(f"Édition existante : {edition.nom}")

# ---------------------------------------------------------------------------
# 2. Mapping NOM Prénom (format site) → joueur_id
# ---------------------------------------------------------------------------

MAPPING: dict[str, str | None] = {
    "BAPTISTE Nicolas":          "04410014",
    "MATHERN Claire":            "04130003",
    "HEINIS Eloïse":             "04130107",
    "AGUERRE Cédric":            "04090080",
    "XANTHOPOULOS Catherine":    "04130032",
    "HARTMANN Richard":          "04240032",
    "COSTEY Jonathan":           "04030087",
    "HOARAU Marion":             "04090055",
    "NOUVEL Yvette":             "04420002",
    "WAECHTER Jade":             "04130121",
    "MATHIS Philippe":           "04280050",
    "MARTIN Anthony":            None,
    "ROY Olivier":               "04210015",
    "XIANG Alain":               "04310069",
    "VLAMYNCK Gérald":           "04040243",
    "MEYER-BISCH Agnès":         "04280021",
    "RABESIAKA Lily":            "04210055",
    "BOUTONNET Thomas":          "04280015",
    "DE AGUIAR Bruno":           "04280033",
    "DE KERGOMMEAUX Loïc":       "04290031",
    "TITO Estelle":              "04170032",
    "GUERIN Guillaume":          "04090093",
    "BEUGIN Pierre":             None,
    "TRAN Nghia-Khang":          "04040183",
    "TOUSSAINT Kevin":           "04130015",
    "TOUSSAINT Florence":        None,
    "MONTAUT Sylvestre":         None,
    "RECULARD Floriane":         None,
    "EBLE Catherine":            "04010055",
    "ARNAUD Caroline":           "04090060",
    "FUNG Saiming":              "04090110",
    "GORKA Christian":           "04430029",
    "LEMAIRE Philippe":          None,
    "EBLE Philippe":             "04010054",
    "MIOULANE Françoise":        None,
    "TAPONIER Élise":            "04040122",
    "TIERCIN Mareva":            None,
    "MEYER Marie-France":        "04430021",
    "NOUVEL Bernard":            None,
    "QUENTEL Roland":            None,
    "SHIEH Show-Ling Christelle": None,
    "GUEBLI Nacera":             "04430030",
    "LUCAS Claire":              None,
    "IRLE Marie":                "04010044",
    "CAHAGNE Laurence":          None,
    "NICOLAS Joelle":            None,
    "LEMAIRE Simone":            None,
    "DEMICHEL Eva":              "04130106",
    "DELBOS Josiane":            "04090041",
    "LAY Frederic":              "04240017",
    "ZABOROWSKA Anna":           "04210040",
    "SANTOS Manuel":             "04290023",
    "HERDIER Romain":            "04130027",
    "BENEFICE Camille":          "04090122",
    "KAMMERER Raphaël":          "04240027",
    "BOUVERET Cédric":           None,
    "DOLLE Valerie":             "04240013",
    "MEISTERTZHEIM Maxence":     "04280058",
    "CHEN Chaolei":              "04160080",
    "LAPLAGNE Fanette":          "04130026",
    "MICHELI Paul":              "04130157",
    "PETIT Matthieu":            "04240048",
    "IDOUSKA Hasna":             "04160072",  # IDOUSKA=CÉZANNE IP? Non → Hasna Idouska
    "PETIPAS Myriam":            None,
    "CHAMPENOIS Philippe":       None,
    "WALMSLEY Morgan":           "04310089",
    "HAMANT Mathilde":           None,
    "BARTHEZ Isabelle":          "04130141",
    "RAK Cyrille":               "04090026",
    "RAK Agnes":                 "04090016",
    "ZHAO Yulong":               "04310048",
    "MANZO Annie":               "04090024",
    "IDOTA Koji":                None,
    "BONDOIN Sandra":            "04040047",
    "TERTRE Manuel":             "04160092",
    "TRONCHE Dominique":         None,
    "LASSAYS Cécile":            "04440006",
    "EA Anthony":                "04040105",
    "MANZO Bruno":               "04090025",
    "DESTRIEUX Gabriel":         "04090078",
    "OPHELTES Jean-Yves":        None,
    "PFEIFFER Jili":             "04040205",
    "GELSO RUIZ Mael":           "04440030",
    "LAUNAIS Jocelyne":          "04210010",
    "BITOT Frédéric":            "04210014",
    "TALBOT Julien":             "04090134",
    "BEAUSSART Stéphane":        "04440018",
    "AMONY Cassandra":           "04210047",
    "BOUCHET Louise":            "04210056",
    "DENIZARD Tiffany":          None,
    "LANDIER Jocelyne":          "04490021",
    "RIVAL Bastien":             None,
    "VENT D'EST Remplaçant":     None,
}

# ---------------------------------------------------------------------------
# 3. Données des tournois (format: position, nom_site, mahjong, points)
# Note: sur ce site, "Points de table" = points MCR, "Points" = mahjong (score brut)
# ---------------------------------------------------------------------------

TOURNOIS = [
    {
        "nom": "Golden League MCR - Coupe des pirates",
        "lieu": "Paris",
        "date_debut": "2025-02-08",
        "date_fin":   "2025-02-08",
        "resultats": [
            (1,  "BAPTISTE Nicolas",          669,  21),
            (2,  "RAK Cyrille",               763,  20),
            (3,  "ROY Olivier",               208,  20),
            (4,  "ZHAO Yulong",               726,  19),
            (5,  "MANZO Annie",               713,  18),
            (6,  "IDOTA Koji",                576,  17),
            (7,  "BONDOIN Sandra",            542,  17),
            (8,  "MEYER-BISCH Agnès",         469,  17),
            (9,  "TERTRE Manuel",             196,  17),
            (10, "MATHERN Claire",            578,  16),
            (11, "RAK Agnes",                 313,  16),
            (12, "XIANG Alain",                84,  16),
            (13, "TRONCHE Dominique",         245,  15),
            (14, "LASSAYS Cécile",            219,  15),
            (15, "AGUERRE Cédric",             37,  15),
            (16, "WAECHTER Jade",             178,  14),
            (17, "TRAN Nghia-Khang",          123,  13),
            (18, "HOARAU Marion",              -2,  13),
            (19, "BARTHEZ Isabelle",           -7,  13),
            (20, "DELBOS Josiane",            -14,  13),
            (21, "EA Anthony",                166,  11),
            (22, "MANZO Bruno",                19,  11),
            (23, "DESTRIEUX Gabriel",          -97,  11),
            (24, "MEISTERTZHEIM Maxence",     -102,  10),
            (25, "OPHELTES Jean-Yves",        -233,  10),
            (26, "PFEIFFER Jili",             -310,  10),
            (27, "RABESIAKA Lily",            -352,  10),
            (28, "GELSO RUIZ Mael",           -464,  10),
            (29, "LAUNAIS Jocelyne",          -226,   9),
            (30, "DE AGUIAR Bruno",           -233,   9),
            (31, "BITOT Frédéric",            -282,   9),
            (32, "TALBOT Julien",             -295,   9),
            (33, "TITO Estelle",              -213,   8),
            (34, "AMONY Cassandra",           -361,   8),
            (35, "BEAUSSART Stéphane",        -552,   7),
            (36, "CHEN Chaolei",              -195,   6),
            (37, "BOUCHET Louise",            -572,   6),
            (38, "DENIZARD Tiffany",          -822,   5),
            (39, "LANDIER Jocelyne",          -673,   3),
            (40, "RIVAL Bastien",             -839,   3),
        ],
    },
    {
        "nom": "Golden League MCR - East en ILL",
        "lieu": "Paris",
        "date_debut": "2025-03-08",
        "date_fin":   "2025-03-08",
        "resultats": [
            (1,  "DE KERGOMMEAUX Loïc",        766,  23),
            (2,  "GUERIN Guillaume",            579,  21),
            (3,  "ARNAUD Caroline",             436,  21),
            (4,  "TRAN Nghia-Khang",            240,  20),
            (5,  "DEMICHEL Eva",                725,  18),
            (6,  "AGUERRE Cédric",              808,  17),
            (7,  "DELBOS Josiane",              630,  17),
            (8,  "LAY Frederic",                499,  17),
            (9,  "ZABOROWSKA Anna",             374,  16),
            (10, "SANTOS Manuel",               333,  16),
            (11, "XIANG Alain",                 213,  16),
            (12, "BAPTISTE Nicolas",            285,  15),
            (13, "MATHERN Claire",              275,  15),
            (14, "HERDIER Romain",              143,  15),
            (15, "BENEFICE Camille",            483,  14),
            (16, "ROY Olivier",                 276,  14),
            (17, "KAMMERER Raphaël",            194,  14),
            (18, "RABESIAKA Lily",              124,  14),
            (19, "DE AGUIAR Bruno",              82,  14),
            (20, "FUNG Saiming",                -42,  14),
            (21, "BOUVERET Cédric",             -80,  14),
            (22, "HOARAU Marion",               380,  13),
            (23, "DOLLE Valerie",               234,  13),
            (24, "NOUVEL Yvette",               128,  13),
            (25, "MICHELI Paul",               -111,  13),
            (26, "MEISTERTZHEIM Maxence",       -42,  12),
            (27, "CHEN Chaolei",               -135,  11),
            (28, "HARTMANN Richard",           -213,  11),
            (29, "VLAMYNCK Gérald",            -250,  11),
            (30, "LAPLAGNE Fanette",           -252,  10),
            (31, "BOUTONNET Thomas",           -402,  10),
            (32, "PETIT Matthieu",              -79,   9),
            (33, "IDOUSKA Hasna",              -619,   9),
            (34, "BARTHEZ Isabelle",           -120,   7),
            (35, "PETIPAS Myriam",             -294,   7),
            (36, "TITO Estelle",               -800,   7),
            (37, "CHAMPENOIS Philippe",        -352,   6),
            (38, "WALMSLEY Morgan",            -728,   6),
            (39, "MEYER-BISCH Agnès",          -769,   5),
            (40, "AMONY Cassandra",            -637,   3),
            (41, "MATHIS Philippe",            -828,   3),
            (42, "HAMANT Mathilde",            -618,   2),
            (43, "RECULARD Floriane",          -840,   2),
            (44, "VENT D'EST Remplaçant",         0,   0),
        ],
    },
    {
        "nom": "Golden League MCR - Round 3",
        "lieu": "Pelleautier",
        "date_debut": "2025-04-19",
        "date_fin":   "2025-04-19",
        "resultats": [
            (1,  "BAPTISTE Nicolas",           869,  24),
            (2,  "EBLE Catherine",             326,  21),
            (3,  "ARNAUD Caroline",            772,  20),
            (4,  "VLAMYNCK Gérald",            493,  19),
            (5,  "TRAN Nghia-Khang",           449,  18),
            (6,  "FUNG Saiming",               367,  16),
            (7,  "GORKA Christian",            263,  15),
            (8,  "LEMAIRE Philippe",           129,  15),
            (9,  "EBLE Philippe",              193,  13),
            (10, "AGUERRE Cédric",              -6,  12),
            (11, "MIOULANE Françoise",          34,  11),
            (12, "TAPONIER Élise",              23,  11),
            (13, "TIERCIN Mareva",             -16,  10),
            (14, "NOUVEL Yvette",              -42,  10),
            (15, "MEYER Marie-France",        -256,  10),
            (16, "NOUVEL Bernard",             -47,   9),
            (17, "QUENTEL Roland",            -300,   9),
            (18, "SHIEH Show-Ling Christelle",-368,   9),
            (19, "GUEBLI Nacera",             -456,   9),
            (20, "LUCAS Claire",              -270,   8),
            (21, "IRLE Marie",               -415,   7),
            (22, "CAHAGNE Laurence",          -556,   6),
            (23, "NICOLAS Joelle",            -568,   6),
            (24, "LEMAIRE Simone",            -628,   6),
        ],
    },
    {
        "nom": "Golden League MCR - Round 4",
        "lieu": "Nancy",
        "date_debut": "2025-06-08",
        "date_fin":   "2025-06-08",
        "resultats": [
            (1,  "BAPTISTE Nicolas",           849,  23),
            (2,  "MATHERN Claire",             393,  18),
            (3,  "HEINIS Eloïse",              143,  18),
            (4,  "AGUERRE Cédric",             621,  17),
            (5,  "XANTHOPOULOS Catherine",     247,  17),
            (6,  "HARTMANN Richard",           138,  16),
            (7,  "COSTEY Jonathan",             96,  16),
            (8,  "HOARAU Marion",               97,  15),
            (9,  "NOUVEL Yvette",              -56,  15),
            (10, "WAECHTER Jade",              398,  14),
            (11, "MATHIS Philippe",            394,  14),
            (12, "MARTIN Anthony",              99,  14),
            (13, "ROY Olivier",                 43,  13),
            (14, "XIANG Alain",               -125,  13),
            (15, "VLAMYNCK Gérald",           -193,  12),
            (16, "MEYER-BISCH Agnès",         -126,  11),
            (17, "RABESIAKA Lily",            -360,  11),
            (18, "BOUTONNET Thomas",            32,  10),
            (19, "DE AGUIAR Bruno",             13,  10),
            (20, "DE KERGOMMEAUX Loïc",       -101,  10),
            (21, "TITO Estelle",              -341,  10),
            (22, "GUERIN Guillaume",          -363,   8),
            (23, "BEUGIN Pierre",             -441,   8),
            (24, "TRAN Nghia-Khang",          -214,   7),
            (25, "TOUSSAINT Kevin",           -241,   7),
            (26, "TOUSSAINT Florence",        -264,   6),
            (27, "MONTAUT Sylvestre",         -336,   6),
            (28, "RECULARD Floriane",         -422,   4),
        ],
    },
]

# ---------------------------------------------------------------------------
# 4. Import
# ---------------------------------------------------------------------------

for t_data in TOURNOIS:
    nb = len(t_data["resultats"])

    tournoi = db.query(Tournoi).filter_by(nom=t_data["nom"], pays="FR").first()
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
        db.query(Resultat).filter_by(tournoi_id=tournoi.id).delete()
        db.query(ResultatAnonyme).filter_by(tournoi_id=tournoi.id).delete()

    lien = db.query(ChampionnatTournoi).filter_by(
        championnat_id=edition.id, tournoi_id=tournoi.id
    ).first()
    if not lien:
        db.add(ChampionnatTournoi(championnat_id=edition.id, tournoi_id=tournoi.id))

    nb_id = nb_anon = 0
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
                nb_id += 1
                continue
            else:
                print(f"  WARN: {joueur_id} introuvable pour {nom_site}")

        parts = nom_site.split(" ", 1)
        db.add(ResultatAnonyme(
            tournoi_id=tournoi.id,
            position=pos,
            nationalite="FR",
            nom=parts[0],
            prenom=parts[1] if len(parts) > 1 else "",
        ))
        nb_anon += 1

    print(f"  {nb_id} identifiés, {nb_anon} anonymes")

db.commit()
db.close()
print("\nImport Golden League terminé.")
