import json
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Championship, ChampionshipSeries, ChampionshipTournament, Tournament, Player
from app.i18n import templates
from app.routes.manage import _require_auth, _allowed_countries, _base_ctx, _set_flash

router = APIRouter(prefix="/manage/championships")


# ---------------------------------------------------------------------------
# Series list
# ---------------------------------------------------------------------------

@router.get("/")
def championships_list(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    allowed = _allowed_countries(user)

    qr = db.query(ChampionshipSeries)
    if user.role != "superadmin":
        qr = qr.filter(ChampionshipSeries.country.in_(allowed))
    series_list = qr.order_by(ChampionshipSeries.country, ChampionshipSeries.name).all()

    ctx = _base_ctx(request, user, "championships")
    ctx["series_list"] = series_list
    return templates.TemplateResponse(request, "manage/championships.html", ctx)


# ---------------------------------------------------------------------------
# New series
# ---------------------------------------------------------------------------

@router.get("/new")
def series_new(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    ctx = _base_ctx(request, user, "championships")
    ctx.update({"series": None, "allowed_countries": _allowed_countries(user)})
    return templates.TemplateResponse(request, "manage/championship_series_form.html", ctx)


@router.post("/new")
async def series_new_post(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    allowed = _allowed_countries(user)
    country = form.get("country", "")
    if user.role != "superadmin" and country not in allowed:
        _set_flash(request, "Pays non autorisé.", "error")
        return RedirectResponse("/manage/championships/new", status_code=302)

    if db.query(ChampionshipSeries).filter_by(slug=form["slug"]).first():
        _set_flash(request, f"Slug « {form['slug']} » déjà utilisé.", "error")
        return RedirectResponse("/manage/championships/new", status_code=302)

    s = ChampionshipSeries(
        slug=form["slug"].strip(),
        name=form["name"].strip(),
        rules=form["rules"],
        country=country,
        description=form.get("description") or None,
    )
    db.add(s)
    db.commit()
    _set_flash(request, f"Série « {s.name} » créée.")
    return RedirectResponse(f"/manage/championships/{s.slug}/", status_code=302)


# ---------------------------------------------------------------------------
# Edit series
# ---------------------------------------------------------------------------

@router.get("/{slug}/edit")
def series_edit(slug: str, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    s = db.query(ChampionshipSeries).filter_by(slug=slug).first()
    if not s:
        return RedirectResponse("/manage/championships/", status_code=302)
    ctx = _base_ctx(request, user, "championships")
    ctx.update({"series": s, "allowed_countries": _allowed_countries(user)})
    return templates.TemplateResponse(request, "manage/championship_series_form.html", ctx)


@router.post("/{slug}/edit")
async def series_edit_post(slug: str, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    s = db.query(ChampionshipSeries).filter_by(slug=slug).first()
    if not s:
        return RedirectResponse("/manage/championships/", status_code=302)
    form = await request.form()
    s.name = form["name"].strip()
    s.rules = form["rules"]
    s.country = form["country"]
    s.description = form.get("description") or None
    db.commit()
    _set_flash(request, f"Série « {s.name} » mise à jour.")
    return RedirectResponse(f"/manage/championships/{slug}/", status_code=302)


# ---------------------------------------------------------------------------
# Editions list for a series
# ---------------------------------------------------------------------------

@router.get("/{slug}/")
def editions_list(slug: str, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    s = db.query(ChampionshipSeries).filter_by(slug=slug).first()
    if not s:
        return RedirectResponse("/manage/championships/", status_code=302)
    editions = db.query(Championship).filter_by(series_id=s.id).order_by(Championship.year.desc()).all()

    ctx = _base_ctx(request, user, "championships")
    ctx.update({"series": s, "editions": editions})
    return templates.TemplateResponse(request, "manage/championship_editions.html", ctx)


# ---------------------------------------------------------------------------
# New edition
# ---------------------------------------------------------------------------

@router.get("/{slug}/new")
def edition_new(slug: str, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    s = db.query(ChampionshipSeries).filter_by(slug=slug).first()
    if not s:
        return RedirectResponse("/manage/championships/", status_code=302)

    available = _available_tournaments(db, s)
    players = db.query(Player).filter(Player.nationality == s.country).order_by(Player.last_name).all()

    ctx = _base_ctx(request, user, "championships")
    ctx.update({
        "series": s, "edition": None,
        "available_tournaments": available,
        "linked_ids": set(),
        "players": players,
    })
    return templates.TemplateResponse(request, "manage/championship_edition_form.html", ctx)


@router.post("/{slug}/new")
async def edition_new_post(slug: str, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    s = db.query(ChampionshipSeries).filter_by(slug=slug).first()
    if not s:
        return RedirectResponse("/manage/championships/", status_code=302)

    form = await request.form()
    year = int(form["year"])

    if db.query(Championship).filter_by(series_id=s.id, year=year).first():
        _set_flash(request, f"Une édition {year} existe déjà pour cette série.", "error")
        return RedirectResponse(f"/manage/championships/{slug}/new", status_code=302)

    n = int(form.get("param_n") or 3)
    e = Championship(
        series_id=s.id,
        year=year,
        name=form.get("name") or None,
        formula="moyenne_n_meilleurs",
        params=json.dumps({"n": n}),
        champion_id=form.get("champion_id") or None,
        champion_name=form.get("champion_name") or None,
    )
    db.add(e)
    db.flush()
    _save_tournament_links(db, e.id, form.getlist("tournament_ids"))
    db.commit()
    _set_flash(request, f"Édition {year} créée.")
    return RedirectResponse(f"/manage/championships/{slug}/", status_code=302)


# ---------------------------------------------------------------------------
# Edit edition
# ---------------------------------------------------------------------------

@router.get("/{slug}/{year}/edit")
def edition_edit(slug: str, year: int, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    s = db.query(ChampionshipSeries).filter_by(slug=slug).first()
    e = db.query(Championship).filter_by(series_id=s.id, year=year).first() if s else None
    if not s or not e:
        return RedirectResponse("/manage/championships/", status_code=302)

    linked_ids = {lnk.tournament_id for lnk in e.tournament_links}
    available = _available_tournaments(db, s)
    players = db.query(Player).filter(Player.nationality == s.country).order_by(Player.last_name).all()

    ctx = _base_ctx(request, user, "championships")
    ctx.update({
        "series": s, "edition": e,
        "available_tournaments": available,
        "linked_ids": linked_ids,
        "players": players,
    })
    return templates.TemplateResponse(request, "manage/championship_edition_form.html", ctx)


@router.post("/{slug}/{year}/edit")
async def edition_edit_post(slug: str, year: int, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    s = db.query(ChampionshipSeries).filter_by(slug=slug).first()
    e = db.query(Championship).filter_by(series_id=s.id, year=year).first() if s else None
    if not s or not e:
        return RedirectResponse("/manage/championships/", status_code=302)

    form = await request.form()
    n = int(form.get("param_n") or 3)
    e.name = form.get("name") or None
    e.formula = "moyenne_n_meilleurs"
    e.params = json.dumps({"n": n})
    e.champion_id = form.get("champion_id") or None
    e.champion_name = form.get("champion_name") or None

    _save_tournament_links(db, e.id, form.getlist("tournament_ids"))
    db.commit()
    _set_flash(request, f"Édition {year} mise à jour.")
    return RedirectResponse(f"/manage/championships/{slug}/", status_code=302)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _available_tournaments(db, series: ChampionshipSeries):
    """Returns tournaments matching the series rules and country, ordered by date desc."""
    return db.query(Tournament).filter(
        Tournament.rules == series.rules,
        Tournament.country == series.country,
    ).order_by(Tournament.start_date.desc()).all()


def _save_tournament_links(db, championship_id: int, tournament_ids: list[str]):
    """Replace all tournament links for a championship edition."""
    db.query(ChampionshipTournament).filter_by(championship_id=championship_id).delete()
    for tid in tournament_ids:
        try:
            db.add(ChampionshipTournament(championship_id=championship_id, tournament_id=int(tid)))
        except (ValueError, TypeError):
            pass
