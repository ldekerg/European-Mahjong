from sqlalchemy import Column, String, Integer, Float, Date, ForeignKey, UniqueConstraint, Boolean, Index
from sqlalchemy.orm import relationship
from database import Base


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
    ema_id = Column(Integer, nullable=False)       # numéro EMA original
    regles = Column(String, nullable=False)        # MCR ou RCR
    nom = Column(String, nullable=False)
    lieu = Column(String, nullable=False)
    pays = Column(String, nullable=False)
    date_debut = Column(Date, nullable=False)
    date_fin = Column(Date, nullable=False)
    nb_joueurs = Column(Integer, nullable=False)
    coefficient = Column(Float, nullable=False)    # MERS
    latitude  = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # normal | wmc | oemc | wrc | oerc  (wmc/wrc exclus du classement)
    type_tournoi = Column(String, nullable=False, default="normal")

    __table_args__ = (UniqueConstraint("ema_id", "regles", name="uq_tournoi_ema_regles"),)

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
