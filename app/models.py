from sqlalchemy import Column, String, Integer, Float, Date, ForeignKey, UniqueConstraint, Boolean, Index, text
from sqlalchemy.orm import relationship
from app.database import Base


class Joueur(Base):
    __tablename__ = "joueurs"

    id = Column(String, primary_key=True)  # EMA Number ex: "04290031"
    nom = Column(String, nullable=False)
    prenom = Column(String, nullable=False)
    nationalite = Column(String, nullable=False)  # code pays ex: "FR"
    # europeen | guest (ID commence par 24) | etranger (uniquement WMC/OEMC/WRC/OERC)
    statut = Column(String, nullable=False, default="europeen")

    resultats = relationship("Resultat", back_populates="joueur")


class Tournoi(Base):
    __tablename__ = "tournois"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ema_id = Column(Integer, nullable=True)        # numéro EMA original, NULL si pas encore assigné
    regles = Column(String, nullable=False)        # MCR ou RCR
    nom = Column(String, nullable=False)
    lieu = Column(String, nullable=False)
    pays = Column(String, nullable=False)
    date_debut = Column(Date, nullable=False)
    date_fin = Column(Date, nullable=False)
    nb_joueurs = Column(Integer, nullable=False)
    coefficient = Column(Float, nullable=False)    # MERS
    latitude  = Column(Float, nullable=True)   # déprecié — utiliser ville_id
    longitude = Column(Float, nullable=True)   # déprecié — utiliser ville_id
    ville_id  = Column(Integer, ForeignKey("villes.id"), nullable=True)

    ville     = relationship("Ville")
    # normal | wmc | oemc | wrc | oerc  (wmc/wrc exclus du classement)
    type_tournoi = Column(String, nullable=False, default="normal")
    # actif | calendrier | archive
    statut = Column(String, nullable=False, default="actif")
    # ok | pending | no_mers | NULL (pour les tournois importés via EMA)
    approbation = Column(String, nullable=True)
    url_site = Column(String, nullable=True)    # lien vers le site du tournoi (calendrier EMA)

    __table_args__ = (
        # Unicité (ema_id, regles) seulement quand ema_id n'est pas NULL (index partiel SQLite)
        Index("uq_tournoi_ema_regles", "ema_id", "regles", unique=True,
              sqlite_where=text("ema_id IS NOT NULL")),
    )

    resultats = relationship("Resultat", back_populates="tournoi")


class Resultat(Base):
    __tablename__ = "resultats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournoi_id = Column(Integer, ForeignKey("tournois.id"), nullable=False)
    joueur_id = Column(String, ForeignKey("joueurs.id"), nullable=False)
    position = Column(Integer, nullable=False)
    points = Column(Integer, nullable=False)   # victoires cumulées (0/1/2/4)
    mahjong = Column(Integer, nullable=False)  # score brut cumulé
    ranking = Column(Integer, nullable=False)  # points EMA attribués
    nationalite = Column(String, nullable=True)  # nationalité au moment du tournoi

    tournoi = relationship("Tournoi", back_populates="resultats")
    joueur = relationship("Joueur", back_populates="resultats")


class ResultatAnonyme(Base):
    """Résultat d'un tournoi pour un joueur sans numéro EMA (non importable dans resultats)."""
    __tablename__ = "resultats_anonymes"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    tournoi_id  = Column(Integer, ForeignKey("tournois.id"), nullable=False)
    position    = Column(Integer, nullable=False)
    nationalite = Column(String, nullable=True)   # code ISO maj ex: "FR", vide si inconnu
    nom         = Column(String, nullable=True)   # peut être vide
    prenom      = Column(String, nullable=True)   # peut être vide

    tournoi = relationship("Tournoi")

    __table_args__ = (
        UniqueConstraint("tournoi_id", "position", name="uq_anon_tournoi_position"),
    )


class ChangementNationalite(Base):
    __tablename__ = "changements_nationalite"

    id = Column(Integer, primary_key=True, autoincrement=True)
    joueur_id = Column(String, ForeignKey("joueurs.id"), nullable=False)
    nationalite_avant = Column(String, nullable=False)
    nationalite_apres = Column(String, nullable=False)
    date_changement = Column(Date, nullable=False)

    __table_args__ = (UniqueConstraint("joueur_id", "date_changement"),)


class Ville(Base):
    __tablename__ = "villes"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    nom       = Column(String, nullable=False)   # ex: "Lyon"
    pays      = Column(String, nullable=False)   # code ISO ex: "FR"
    latitude  = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("nom", "pays", name="uq_ville_nom_pays"),
    )


class SerieChampionnat(Base):
    __tablename__ = "serie_championnat"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    slug        = Column(String, unique=True, nullable=False)   # ex: "france-mcr"
    nom         = Column(String, nullable=False)                # ex: "Championnat de France MCR"
    regles      = Column(String, nullable=False)                # MCR | RCR
    pays        = Column(String, nullable=False)                # code pays ex: "FR"
    description = Column(String, nullable=True)

    editions = relationship("Championnat", back_populates="serie", order_by="Championnat.annee.desc()")

    __table_args__ = (Index("ix_serie_championnat_pays", "pays"),)


class Championnat(Base):
    __tablename__ = "championnat"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    serie_id = Column(Integer, ForeignKey("serie_championnat.id"), nullable=False)
    annee    = Column(Integer, nullable=False)
    nom          = Column(String, nullable=True)       # override optionnel
    formule      = Column(String, nullable=False, default="moyenne_n_meilleurs")
    params       = Column(String, nullable=False, default='{"n": 3}')  # JSON
    champion_id  = Column(String, ForeignKey("joueurs.id"), nullable=True)   # joueur EMA identifié
    champion_nom = Column(String, nullable=True)   # fallback texte libre (anonyme ou surcharge)

    serie    = relationship("SerieChampionnat", back_populates="editions")
    liens    = relationship("ChampionnatTournoi", back_populates="championnat")
    champion = relationship("Joueur", foreign_keys=[champion_id])


class ChampionnatTournoi(Base):
    __tablename__ = "championnat_tournoi"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    championnat_id  = Column(Integer, ForeignKey("championnat.id"), nullable=False)
    tournoi_id      = Column(Integer, ForeignKey("tournois.id"), nullable=False)

    championnat = relationship("Championnat", back_populates="liens")
    tournoi     = relationship("Tournoi")

    __table_args__ = (
        UniqueConstraint("championnat_id", "tournoi_id", name="uq_champ_tournoi"),
        Index("ix_championnat_tournoi_tournoi", "tournoi_id"),
    )


class ClassementHistorique(Base):
    __tablename__ = "classement_historique"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    semaine  = Column(Date, nullable=False)
    regles   = Column(String, nullable=False)
    joueur_id = Column(String, ForeignKey("joueurs.id"), nullable=False)
    position = Column(Integer, nullable=False)
    score    = Column(Float, nullable=False)
    nb_tournois = Column(Integer, nullable=True)
    nb_or       = Column(Integer, nullable=True)  # 1er dans tournois actifs
    nb_argent   = Column(Integer, nullable=True)  # 2e
    nb_bronze   = Column(Integer, nullable=True)  # 3e

    __table_args__ = (
        UniqueConstraint("semaine", "regles", "joueur_id", name="uq_classement_semaine"),
        Index("ix_classement_joueur", "joueur_id", "regles", "semaine"),
        Index("ix_classement_semaine", "semaine", "regles"),
    )
