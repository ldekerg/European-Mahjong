"""
Tests des fonctions métier pures de ranking.py.
Aucune dépendance DB ou réseau.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date
from app.ranking import (
    lundi_semaine,
    semaine_debut_tournoi,
    semaines_actives,
    contribution,
    points_ema_tournoi,
    _nb_tournois_part_a,
    _moyenne_ponderee,
    FREEZE_DEBUT,
    FREEZE_FIN,
)


# ── lundi_semaine ────────────────────────────────────────────────────────────

def test_lundi_semaine_lundi():
    assert lundi_semaine(date(2026, 5, 11)) == date(2026, 5, 11)

def test_lundi_semaine_mercredi():
    assert lundi_semaine(date(2026, 5, 13)) == date(2026, 5, 11)

def test_lundi_semaine_dimanche():
    assert lundi_semaine(date(2026, 5, 17)) == date(2026, 5, 11)

def test_lundi_semaine_debut_annee():
    assert lundi_semaine(date(2026, 1, 1)) == date(2025, 12, 29)


# ── semaine_debut_tournoi ────────────────────────────────────────────────────

def test_semaine_debut_tournoi_lundi():
    # Tournoi un lundi → actif le lundi suivant
    assert semaine_debut_tournoi(date(2026, 5, 11)) == date(2026, 5, 18)

def test_semaine_debut_tournoi_milieu_semaine():
    # Tournoi un mercredi → lundi de la semaine suivante
    assert semaine_debut_tournoi(date(2026, 5, 13)) == date(2026, 5, 18)


# ── semaines_actives ─────────────────────────────────────────────────────────

def test_semaines_actives_hors_freeze():
    # Deux semaines consécutives hors freeze
    debut = date(2026, 5, 11)
    cible = date(2026, 5, 18)
    assert semaines_actives(debut, cible) == 2

def test_semaines_actives_pendant_freeze():
    # Toute la période freeze → 0 semaines actives
    assert semaines_actives(FREEZE_DEBUT, FREEZE_FIN - __import__('datetime').timedelta(weeks=1)) == 0

def test_semaines_actives_une_semaine():
    assert semaines_actives(date(2026, 5, 11), date(2026, 5, 11)) == 1


# ── contribution ─────────────────────────────────────────────────────────────

def test_contribution_semaine_1():
    # Tournoi le lundi 11 mai, contribution à la semaine 18 mai (semaine 1) → 1.0
    assert contribution(date(2026, 5, 11), date(2026, 5, 18)) == 1.0

def test_contribution_avant_activation():
    # Cible = même semaine que debut_tournoi → 0.0
    assert contribution(date(2026, 5, 11), date(2026, 5, 11)) == 0.0

def test_contribution_semaine_52():
    debut = date(2025, 5, 12)
    # 52 semaines actives après semaine_debut → contribution 1.0
    cible = date(2026, 5, 11)
    c = contribution(debut, cible)
    assert c == 1.0

def test_contribution_semaine_53():
    # Semaine 53 → 0.5
    debut = date(2025, 5, 5)
    cible = date(2026, 5, 11)
    c = contribution(debut, cible)
    assert c == 0.5

def test_contribution_apres_104():
    # Plus de 104 semaines → 0.0
    debut = date(2024, 1, 1)
    cible = date(2026, 5, 11)
    assert contribution(debut, cible) == 0.0


# ── points_ema_tournoi ───────────────────────────────────────────────────────

def test_points_ema_premier():
    # 1er sur 100 joueurs → 1000
    assert points_ema_tournoi(1, 100) == 1000

def test_points_ema_dernier():
    # Dernier (100/100) → 0
    assert points_ema_tournoi(100, 100) == 0

def test_points_ema_milieu():
    # 51e sur 101 joueurs → 500
    assert points_ema_tournoi(51, 101) == 500

def test_points_ema_deuxieme_sur_deux():
    # 2e sur 2 → 0
    assert points_ema_tournoi(2, 2) == 0

def test_points_ema_premier_sur_deux():
    # 1er sur 2 → 1000
    assert points_ema_tournoi(1, 2) == 1000


# ── _nb_tournois_part_a ──────────────────────────────────────────────────────

def test_nb_part_a_cinq():
    assert _nb_tournois_part_a(5) == 5

def test_nb_part_a_dix():
    # 5 + ceil(0.8 * 5) = 5 + 4 = 9
    assert _nb_tournois_part_a(10) == 9

def test_nb_part_a_zero():
    assert _nb_tournois_part_a(0) == 5

def test_nb_part_a_un():
    assert _nb_tournois_part_a(1) == 5


# ── _moyenne_ponderee ────────────────────────────────────────────────────────

def test_moyenne_ponderee_simple():
    entries = [(1000, 1.0), (500, 1.0)]
    assert _moyenne_ponderee(entries, 0) == 750.0

def test_moyenne_ponderee_avec_manquants():
    # 1 résultat de 1000, 1 manquant (0) → (1000) / (1 + 1) = 500
    entries = [(1000, 1.0)]
    assert _moyenne_ponderee(entries, 1) == 500.0

def test_moyenne_ponderee_vide():
    assert _moyenne_ponderee([], 0) == 0.0

def test_moyenne_ponderee_poids_variables():
    entries = [(1000, 2.0), (0, 1.0)]
    # (1000*2 + 0*1) / (2 + 1) = 2000/3
    assert abs(_moyenne_ponderee(entries, 0) - 2000/3) < 0.001
