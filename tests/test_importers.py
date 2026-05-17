"""
Tests des fonctions de parsing des scripts d'import.
Aucune dépendance DB ou réseau — on teste uniquement les fonctions pures.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date


# ── importers/calendar.py ────────────────────────────────────────────────────

from scripts.importers.calendar import type_from_nom, parse_dates, _mois_suivant


class TestTypeFromNom:
    def test_normal(self):
        assert type_from_nom("Paris MCR Open 2026") == "normal"

    def test_oemc(self):
        assert type_from_nom("European MCR Championship 2026") == "oemc"

    def test_wmc(self):
        assert type_from_nom("World MCR Championship 2024") == "wmc"

    def test_oerc(self):
        assert type_from_nom("European Riichi Championship 2024") == "oerc"

    def test_wrc(self):
        assert type_from_nom("World Riichi Championship 2025") == "wrc"

    def test_case_insensitive(self):
        assert type_from_nom("OEMC 2026 : European MCR Championship") == "oemc"


class TestMoisSuivant:
    def test_milieu_annee(self):
        assert _mois_suivant(5, 2026) == (6, 2026)

    def test_decembre(self):
        assert _mois_suivant(12, 2026) == (1, 2027)

    def test_janvier(self):
        assert _mois_suivant(1, 2026) == (2, 2026)


class TestParseDates:
    def test_un_seul_jour(self):
        debut, fin = parse_dates("15", 5, 2026)
        assert debut == date(2026, 5, 15)
        assert fin == date(2026, 5, 15)

    def test_deux_jours_meme_mois(self):
        debut, fin = parse_dates("9-10", 5, 2026)
        assert debut == date(2026, 5, 9)
        assert fin == date(2026, 5, 10)

    def test_chevauchement_mois(self):
        # 31 mai - 1 juin
        debut, fin = parse_dates("31-01", 5, 2026)
        assert debut == date(2026, 5, 31)
        assert fin == date(2026, 6, 1)

    def test_plusieurs_jours(self):
        debut, fin = parse_dates("2-3-4-5", 6, 2026)
        assert debut == date(2026, 6, 2)
        assert fin == date(2026, 6, 5)

    def test_suffixes_mois_litteraux(self):
        debut, fin = parse_dates("31oct-01nov", 10, 2026)
        assert debut == date(2026, 10, 31)
        assert fin == date(2026, 11, 1)


# ── importers/ema.py ─────────────────────────────────────────────────────────

from scripts.importers.ema import parse_tournament


EMA_HTML_SAMPLE = """
<html><body>
<table>
<tr><td class="PlayerBloc_2">Number</td><td class="PlayerBloc_2">123</td></tr>
<tr><td class="PlayerBloc_2">Name</td><td class="PlayerBloc_2">Test Tournament MCR 2026</td></tr>
<tr><td class="PlayerBloc_2">City</td><td class="PlayerBloc_2">Paris</td></tr>
<tr><td class="PlayerBloc_2">Country</td><td class="PlayerBloc_2">fr</td></tr>
<tr><td class="PlayerBloc_2">Date</td><td class="PlayerBloc_2">15/05/2026</td></tr>
<tr><td class="PlayerBloc_2">Date end</td><td class="PlayerBloc_2">17/05/2026</td></tr>
<tr><td class="PlayerBloc_2">Players</td><td class="PlayerBloc_2">64</td></tr>
<tr><td class="PlayerBloc_2">Coefficient</td><td class="PlayerBloc_2">1.5</td></tr>
<tr><td class="PlayerBloc_2">Rules</td><td class="PlayerBloc_2">MCR</td></tr>
</table>
</body></html>
"""


class TestParseTournament:
    def test_page_vide(self):
        assert parse_tournament("<html></html>", 1) is None

    def test_sans_numero(self):
        html = "<html><body><td class='PlayerBloc_2'>Name</td><td class='PlayerBloc_2'>Test</td></body></html>"
        assert parse_tournament(html, 1) is None


# ── app/ranking_history.py ───────────────────────────────────────────────────

from app.ranking_history import semaines_entre, semaines_actives, PREMIERE_SEMAINE
from app.ranking import FREEZE_DEBUT, FREEZE_FIN
from datetime import timedelta


class TestSemainesEntre:
    def test_deux_semaines(self):
        debut = date(2026, 5, 11)
        fin = date(2026, 5, 18)
        result = list(semaines_entre(debut, fin))
        assert result == [date(2026, 5, 11), date(2026, 5, 18)]

    def test_meme_semaine(self):
        d = date(2026, 5, 11)
        result = list(semaines_entre(d, d))
        assert result == [d]

    def test_debut_non_lundi(self):
        # Ramène au lundi
        result = list(semaines_entre(date(2026, 5, 13), date(2026, 5, 18)))
        assert result[0] == date(2026, 5, 11)


class TestSemainesActives:
    def test_hors_freeze(self):
        semaines = [date(2026, 5, 11), date(2026, 5, 18)]
        assert semaines_actives(semaines) == semaines

    def test_pendant_freeze(self):
        semaines = [FREEZE_DEBUT, FREEZE_DEBUT + timedelta(weeks=1)]
        assert semaines_actives(semaines) == []

    def test_mixte(self):
        hors = date(2026, 5, 11)
        dans = FREEZE_DEBUT
        result = semaines_actives([hors, dans])
        assert result == [hors]
