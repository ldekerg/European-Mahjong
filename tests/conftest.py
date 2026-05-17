"""
Shared pytest fixtures for route integration tests.
Uses an in-memory SQLite database populated with minimal test data.
"""

import sys, os
# Set before any app import so module-level create_all is skipped
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/ema_ranking.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as _db_module
from app.database import Base, get_db
from app.models import (
    Player, Tournament, Result, AnonymousResult,
    RankingHistory, City,
)
import app.main as _main_module
from app.main import app

# ── In-memory test database ───────────────────────────────────────────────────

import tempfile, atexit
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
TEST_DB_PATH = _tmp.name
atexit.register(lambda: os.unlink(TEST_DB_PATH) if os.path.exists(TEST_DB_PATH) else None)

TEST_DB_URL = f"sqlite:///{TEST_DB_PATH}"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=test_engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# Patch SessionLocal everywhere it's used directly (not via dependency injection)
_db_module.SessionLocal = TestSession
_main_module.SessionLocal = TestSession


# ── Fixtures ──────────────────────────────────────────────────────────────────

# Create tables in test DB immediately
Base.metadata.create_all(bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Seed minimal test data once per test session."""
    db = TestSession()

    # Players
    p1 = Player(id="04290001", last_name="DUPONT", first_name="Jean", nationality="FR", status="europeen")
    p2 = Player(id="04290002", last_name="MARTIN", first_name="Marie", nationality="FR", status="europeen")
    p3 = Player(id="09990001", last_name="SMITH", first_name="John", nationality="GB", status="europeen")
    db.add_all([p1, p2, p3])

    # Tournaments
    t1 = Tournament(
        id=1, ema_id=100, rules="MCR", name="Test Open MCR 2025",
        city="Paris", country="France", start_date=date(2025, 3, 1),
        end_date=date(2025, 3, 2), nb_players=3, coefficient=1.0,
        tournament_type="normal", status="actif",
    )
    t2 = Tournament(
        id=2, ema_id=101, rules="MCR", name="Test Open MCR 2024",
        city="Lyon", country="France", start_date=date(2024, 6, 15),
        end_date=date(2024, 6, 15), nb_players=3, coefficient=1.0,
        tournament_type="normal", status="actif",
    )
    t3 = Tournament(
        id=3, ema_id=None, rules="MCR", name="Future MCR 2026",
        city="Bordeaux", country="France", start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1), nb_players=0, coefficient=1.0,
        tournament_type="normal", status="calendrier",
    )
    db.add_all([t1, t2, t3])

    # Results
    db.add_all([
        Result(tournament_id=1, player_id="04290001", position=1, points=4, mahjong=350, ranking=1000),
        Result(tournament_id=1, player_id="04290002", position=2, points=2, mahjong=280, ranking=500),
        Result(tournament_id=1, player_id="09990001", position=3, points=0, mahjong=200, ranking=0),
        Result(tournament_id=2, player_id="04290001", position=1, points=4, mahjong=320, ranking=1000),
        Result(tournament_id=2, player_id="04290002", position=2, points=2, mahjong=250, ranking=500),
        Result(tournament_id=2, player_id="09990001", position=3, points=0, mahjong=180, ranking=0),
    ])

    # Ranking history
    week = date(2026, 5, 11)
    db.add_all([
        RankingHistory(week=week, rules="MCR", player_id="04290001", position=1, score=800.0, nb_tournaments=2, nb_gold=2, nb_silver=0, nb_bronze=0),
        RankingHistory(week=week, rules="MCR", player_id="04290002", position=2, score=400.0, nb_tournaments=2, nb_gold=0, nb_silver=2, nb_bronze=0),
    ])

    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="session")
def client(setup_db):
    """FastAPI test client — depends on setup_db to ensure data is seeded first."""
    with TestClient(app) as c:
        yield c
