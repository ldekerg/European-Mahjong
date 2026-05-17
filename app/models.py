from sqlalchemy import Column, String, Integer, Float, Date, ForeignKey, UniqueConstraint, Boolean, Index, text
from sqlalchemy.orm import relationship
from app.database import Base


class Player(Base):
    __tablename__ = "players"

    id          = Column(String, primary_key=True)   # EMA number e.g. "04290031"
    last_name   = Column(String, nullable=False)
    first_name  = Column(String, nullable=False)
    nationality = Column(String, nullable=False)      # country code e.g. "FR"
    # europeen | guest (ID starts with 24) | etranger (WMC/OEMC/WRC/OERC only)
    status      = Column(String, nullable=False, default="europeen")

    results = relationship("Result", back_populates="player")


class Tournament(Base):
    __tablename__ = "tournaments"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    ema_id          = Column(Integer, nullable=True)        # original EMA number, NULL if not yet assigned
    rules           = Column(String, nullable=False)         # MCR or RCR
    name            = Column(String, nullable=False)
    city            = Column(String, nullable=False)
    country         = Column(String, nullable=False)
    start_date      = Column(Date, nullable=False)
    end_date        = Column(Date, nullable=False)
    nb_players      = Column(Integer, nullable=False)
    coefficient     = Column(Float, nullable=False)          # MERS coefficient
    latitude        = Column(Float, nullable=True)           # deprecated — use city_obj
    longitude       = Column(Float, nullable=True)           # deprecated — use city_obj
    city_id         = Column(Integer, ForeignKey("cities.id"), nullable=True)

    city_obj        = relationship("City")
    # normal | wmc | oemc | wrc | oerc  (wmc/wrc excluded from ranking)
    tournament_type = Column(String, nullable=False, default="normal")
    # actif | calendrier | archive
    status          = Column(String, nullable=False, default="actif")
    # ok | pending | no_mers | NULL (for tournaments imported via EMA)
    approval        = Column(String, nullable=True)
    website         = Column(String, nullable=True)          # link to tournament website

    __table_args__ = (
        Index("uq_tournoi_ema_regles", "ema_id", "rules", unique=True,
              sqlite_where=text("ema_id IS NOT NULL")),
    )

    results = relationship("Result", back_populates="tournament")


class Result(Base):
    __tablename__ = "results"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    player_id     = Column(String, ForeignKey("players.id"), nullable=False)
    position      = Column(Integer, nullable=False)
    points        = Column(Integer, nullable=False)          # cumulative wins (0/1/2/4)
    mahjong       = Column(Integer, nullable=False)          # cumulative raw score
    ranking       = Column(Integer, nullable=False)          # EMA points awarded
    nationality   = Column(String, nullable=True)            # nationality at time of tournament

    tournament = relationship("Tournament", back_populates="results")
    player     = relationship("Player", back_populates="results")


class AnonymousResult(Base):
    """Tournament result for a player without an EMA number."""
    __tablename__ = "anonymous_results"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=False)
    position      = Column(Integer, nullable=False)
    nationality   = Column(String, nullable=True)            # uppercase ISO code e.g. "FR"
    last_name     = Column(String, nullable=True)
    first_name    = Column(String, nullable=True)

    tournament = relationship("Tournament")

    __table_args__ = (
        UniqueConstraint("tournament_id", "position", name="uq_anon_tournoi_position"),
    )


class NationalityChange(Base):
    __tablename__ = "nationality_changes"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    player_id          = Column(String, ForeignKey("players.id"), nullable=False)
    nationality_before = Column(String, nullable=False)
    nationality_after  = Column(String, nullable=False)
    change_date        = Column(Date, nullable=False)

    __table_args__ = (UniqueConstraint("player_id", "change_date"),)


class City(Base):
    __tablename__ = "cities"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    name      = Column(String, nullable=False)               # e.g. "Lyon"
    country   = Column(String, nullable=False)               # ISO code e.g. "FR"
    latitude  = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("name", "country", name="uq_ville_nom_pays"),
    )


class ChampionshipSeries(Base):
    __tablename__ = "championship_series"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    slug        = Column(String, unique=True, nullable=False)
    name        = Column(String, nullable=False)
    rules       = Column(String, nullable=False)              # MCR | RCR
    country     = Column(String, nullable=False)              # country code e.g. "FR"
    description = Column(String, nullable=True)

    editions = relationship("Championship", back_populates="series", order_by="Championship.year.desc()")

    __table_args__ = (Index("ix_serie_championnat_pays", "country"),)


class Championship(Base):
    __tablename__ = "championships"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    series_id     = Column(Integer, ForeignKey("championship_series.id"), nullable=False)
    year          = Column(Integer, nullable=False)
    name          = Column(String, nullable=True)             # optional name override
    formula       = Column(String, nullable=False, default="moyenne_n_meilleurs")
    params        = Column(String, nullable=False, default='{"n": 3}')  # JSON
    champion_id   = Column(String, ForeignKey("players.id"), nullable=True)
    champion_name = Column(String, nullable=True)             # free-text fallback

    series           = relationship("ChampionshipSeries", back_populates="editions")
    tournament_links = relationship("ChampionshipTournament", back_populates="championship")
    champion         = relationship("Player", foreign_keys=[champion_id])


class ChampionshipTournament(Base):
    __tablename__ = "championship_tournaments"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    championship_id = Column(Integer, ForeignKey("championships.id"), nullable=False)
    tournament_id   = Column(Integer, ForeignKey("tournaments.id"), nullable=False)

    championship = relationship("Championship", back_populates="tournament_links")
    tournament   = relationship("Tournament")

    __table_args__ = (
        UniqueConstraint("championship_id", "tournament_id", name="uq_champ_tournoi"),
        Index("ix_championnat_tournoi_tournoi", "tournament_id"),
    )


class RankingHistory(Base):
    __tablename__ = "ranking_history"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    week           = Column(Date, nullable=False)
    rules          = Column(String, nullable=False)
    player_id      = Column(String, ForeignKey("players.id"), nullable=False)
    position       = Column(Integer, nullable=False)
    score          = Column(Float, nullable=False)
    nb_tournaments = Column(Integer, nullable=True)
    nb_gold        = Column(Integer, nullable=True)   # 1st place in active tournaments
    nb_silver      = Column(Integer, nullable=True)   # 2nd place
    nb_bronze      = Column(Integer, nullable=True)   # 3rd place

    __table_args__ = (
        UniqueConstraint("week", "rules", "player_id", name="uq_classement_semaine"),
        Index("ix_classement_joueur", "player_id", "rules", "week"),
        Index("ix_classement_semaine", "week", "rules"),
    )
