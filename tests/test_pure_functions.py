"""
Tests for pure (non-DB, non-network) functions across the codebase.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import date
from markupsafe import Markup


# ── i18n: trad ───────────────────────────────────────────────────────────────

from app.i18n import trad

def test_trad_existing_key():
    assert trad("nav.home", "fr") == "EMA Ranking"

def test_trad_existing_key_en():
    assert trad("nav.home", "en") == "EMA Ranking"

def test_trad_nested_key():
    result = trad("common.date", "fr")
    assert isinstance(result, str) and len(result) > 0

def test_trad_missing_key_returns_key():
    assert trad("nonexistent.key", "fr") == "nonexistent.key"

def test_trad_missing_lang_falls_back_to_fr():
    result = trad("nav.home", "xx")
    assert result == "EMA Ranking"

def test_trad_interpolation():
    result = trad("player.inactive_show", "en", n=5)
    assert "5" in result


# ── i18n: _to_iso ─────────────────────────────────────────────────────────────

from app.i18n import _to_iso

def test_to_iso_two_letter():
    assert _to_iso("FR") == "FR"

def test_to_iso_country_name():
    assert _to_iso("France") == "FR"

def test_to_iso_lowercase():
    assert _to_iso("fr") == "FR"

def test_to_iso_unknown():
    assert _to_iso("Atlantis") is None

def test_to_iso_empty():
    assert _to_iso("") is None


# ── i18n: flag_emoji ──────────────────────────────────────────────────────────

from app.i18n import flag_emoji

def test_flag_emoji_fr():
    assert flag_emoji("FR") == "🇫🇷"

def test_flag_emoji_lowercase():
    assert flag_emoji("fr") == "🇫🇷"

def test_flag_emoji_country_name():
    assert flag_emoji("France") == "🇫🇷"

def test_flag_emoji_guest():
    assert flag_emoji("GUEST") == "🌍"

def test_flag_emoji_unknown():
    result = flag_emoji("XX")
    assert result == "🌍"

def test_flag_emoji_empty():
    assert flag_emoji("") == ""


# ── i18n: ema_color ───────────────────────────────────────────────────────────

from app.i18n import ema_color

def test_ema_color_max():
    result = ema_color(1000)
    assert "background" in result
    assert "color" in result
    assert "hsl(120" in result  # green

def test_ema_color_zero():
    result = ema_color(0)
    assert "hsl(0" in result   # red

def test_ema_color_mid():
    result = ema_color(500)
    assert "hsl(60" in result  # yellow

def test_ema_color_clamps_above():
    assert ema_color(2000) == ema_color(1000)

def test_ema_color_clamps_below():
    assert ema_color(-100) == ema_color(0)


# ── i18n: fmt_date ────────────────────────────────────────────────────────────

from app.i18n import fmt_date

def test_fmt_date_normal():
    assert fmt_date("2026-05-17") == "17/05/2026"

def test_fmt_date_empty():
    assert fmt_date("") == ""

def test_fmt_date_none():
    assert fmt_date(None) == ""

def test_fmt_date_short():
    assert fmt_date("2026") == "2026"


# ── i18n: prenom_propre ───────────────────────────────────────────────────────

from app.i18n import prenom_propre

def test_prenom_propre_basic():
    assert prenom_propre("MARIE") == "Marie"

def test_prenom_propre_accent_correction():
    assert prenom_propre("LOIC") == "Loïc"

def test_prenom_propre_multiple():
    assert prenom_propre("JEAN FRANCOIS") == "Jean François"

def test_prenom_propre_empty():
    assert prenom_propre("") == ""

def test_prenom_propre_none():
    assert prenom_propre(None) is None


# ── countries: _score_equipe ──────────────────────────────────────────────────

from app.routes.countries import _score_equipe

def test_score_equipe_three_players():
    players = [{"score": 900}, {"score": 600}, {"score": 300}]
    assert _score_equipe(players) == 600.0

def test_score_equipe_less_than_three():
    players = [{"score": 900}, {"score": 600}]
    assert _score_equipe(players) == 500.0  # (900+600+0)/3

def test_score_equipe_empty():
    assert _score_equipe([]) == 0.0

def test_score_equipe_one_player():
    assert _score_equipe([{"score": 900}]) == 300.0  # (900+0+0)/3

def test_score_equipe_more_than_three():
    # Only top 3 are used
    players = [{"score": 900}, {"score": 800}, {"score": 700}, {"score": 600}]
    assert _score_equipe(players) == round((900 + 800 + 700) / 3, 2)


# ── ema.py: parse_date ────────────────────────────────────────────────────────

from scripts.importers.ema import parse_date

def test_parse_date_ddmmyyyy():
    start, end = parse_date("06/10/2024")
    assert start == date(2024, 10, 6)
    assert end == date(2024, 10, 6)

def test_parse_date_range_same_month():
    start, end = parse_date("11-12 Mar.2023")
    assert start == date(2023, 3, 11)
    assert end == date(2023, 3, 12)

def test_parse_date_single_day():
    start, end = parse_date("5 Oct.2019")
    assert start == date(2019, 10, 5)
    assert end == date(2019, 10, 5)

def test_parse_date_cross_month():
    start, end = parse_date("28 Sep.-1 Oct.2022")
    assert start == date(2022, 9, 28)
    assert end == date(2022, 10, 1)

def test_parse_date_two_digit_year():
    start, end = parse_date("9 Feb. 25")
    assert start == date(2025, 2, 9)

def test_parse_date_invalid():
    start, end = parse_date("not a date")
    assert start == date(1900, 1, 1)
    assert end == date(1900, 1, 1)

def test_parse_date_long_month_name():
    start, end = parse_date("31 May - 1 June 2008")
    assert start == date(2008, 5, 31)
    assert end == date(2008, 6, 1)
