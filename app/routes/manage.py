import csv, io, os, bcrypt
from datetime import date
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, Query
from fastapi.responses import RedirectResponse, JSONResponse, Response, FileResponse
from sqlalchemy.orm import Session


def _recompute_coefficient(tournament: "Tournament", db: Session):
    """Recompute and save the MERS coefficient from current results."""
    from app.ranking import mers_coefficient
    if not tournament.start_date or tournament.start_date.year == 1900:
        return
    nb_days = max(1, (tournament.end_date - tournament.start_date).days + 1) if tournament.end_date else 1
    nats = [r.nationality or "" for r in tournament.results]
    nats += [a.nationality or "" for a in db.query(AnonymousResult).filter_by(tournament_id=tournament.id).all()]
    tournament.coefficient = mers_coefficient(nb_days, tournament.nb_players, nats, tournament.tournament_type)
    db.commit()


def _recompute_tournament_weeks(tournament: "Tournament"):
    """Recompute ranking_history for all weeks affected by this tournament.
    Runs synchronously — fine for single-tournament edits (max ~104 weeks).
    """
    from app.ranking import tournament_first_week, week_monday
    from app.ranking_history import compute_week, weeks_between, filter_active_weeks

    if not tournament.start_date or tournament.start_date.year == 1900:
        return 0

    first = tournament_first_week(tournament.start_date)
    today_week = week_monday(date.today())
    weeks = filter_active_weeks(list(weeks_between(first, today_week)))
    rules = tournament.rules
    for w in weeks:
        compute_week(w, rules)
    return len(weeks)
from sqlalchemy import func

import json, shutil, uuid
from pathlib import Path
from datetime import datetime as _dt

from app.database import get_db, SessionLocal
from app.models import AdminUser, Tournament, Player, Result, AnonymousResult, City, NationalityChange, Championship, ChampionshipSeries, ChampionshipTournament, AuditLog, Referee, TournamentReferee, RankingHistory
from app.i18n import templates, ISO_NOM_PAYS

# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------
_DB_PATH = Path(os.environ.get("DATABASE_URL", "sqlite:///./data/ema_ranking.db").replace("sqlite:///", ""))
_BACKUPS_DIR = Path(os.environ.get("BACKUPS_DIR", "./backups"))


def _take_snapshot(label: str = "") -> Path:
    """Copy the SQLite DB file to backups/. Returns the backup path."""
    _BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _dt.utcnow().strftime("%Y%m%d_%H%M%S")
    slug = label.replace(" ", "_")[:40] if label else "manual"
    dest = _BACKUPS_DIR / f"ranking_{ts}_{slug}.db"
    shutil.copy2(_DB_PATH, dest)
    # Keep only the 30 most recent backups
    backups = sorted(_BACKUPS_DIR.glob("ranking_*.db"))
    for old in backups[:-30]:
        old.unlink(missing_ok=True)
    return dest


# ---------------------------------------------------------------------------
# Audit log helpers
# ---------------------------------------------------------------------------

def _obj_to_dict(obj) -> dict:
    """Serialize a SQLAlchemy model instance to a plain dict (column values only)."""
    return {c.name: str(getattr(obj, c.name)) for c in obj.__table__.columns}


def _audit(db: Session, request: Request, action: str, table: str, row_id,
           description: str = "", old=None, new=None, session_id: str | None = None):
    """Write one audit log entry."""
    username = request.session.get("admin_username", "?")
    entry = AuditLog(
        admin_user=username,
        action=action,
        table_name=table,
        row_id=str(row_id) if row_id is not None else None,
        description=description,
        old_values=json.dumps(_obj_to_dict(old), default=str) if old is not None else None,
        new_values=json.dumps(_obj_to_dict(new), default=str) if new is not None else None,
        session_id=session_id,
    )
    db.add(entry)
    # (caller must db.commit())

# Tournament types that get an ema_id assigned automatically
EMA_TYPES = {'normal', 'oemc', 'oerc', 'non_mers'}


def _next_ema_id(db: Session, rules: str) -> int:
    """Returns max(ema_id)+1 for the given rules, scoped to non-world tournaments."""
    result = db.query(func.max(Tournament.ema_id)).filter(
        Tournament.rules == rules,
        Tournament.ema_id < 1_000_000,  # exclude WMC/WRC ids
    ).scalar()
    return (result or 0) + 1

router = APIRouter(prefix="/manage")

PAGE_SIZE = 50


def _resolve_tournament_type(form_type: str, rules: str) -> str:
    """Resolve 'championship'/'world' to the actual type based on rules."""
    if form_type == "championship":
        return "oemc" if rules == "MCR" else "oerc"
    if form_type == "world":
        return "wmc" if rules == "MCR" else "wrc"
    return form_type


def _parse_city_id(form_value: str) -> int | None:
    """Return city_id int from form value, or None if empty/invalid."""
    try:
        v = int(form_value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_manage_user(request: Request) -> AdminUser | None:
    username = request.session.get("admin_username")
    if not username:
        return None
    db = SessionLocal()
    try:
        return db.query(AdminUser).filter_by(username=username).first()
    finally:
        db.close()


def _require_auth(request: Request):
    user = _get_manage_user(request)
    if not user:
        return RedirectResponse("/manage/login", status_code=302)
    return user


def _allowed_countries(user: AdminUser) -> list[str]:
    """Returns the list of countries this user can manage. Superadmin gets all."""
    if user.role == "superadmin":
        return sorted(ISO_NOM_PAYS.keys())
    return user.country_list


def _base_ctx(request: Request, user: AdminUser, section: str) -> dict:
    return {
        "request": request,
        "manage_user": user,
        "manage_section": section,
        "flash": request.session.pop("flash", None),
    }


def _set_flash(request: Request, message: str, type: str = "success"):
    request.session["flash"] = {"message": message, "type": type}


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@router.get("/login")
def login_page(request: Request):
    if _get_manage_user(request):
        return RedirectResponse("/manage/", status_code=302)
    return templates.TemplateResponse(request, "manage/login.html", {"request": request, "error": None})


@router.post("/login")
async def login_post(request: Request, db: Session = Depends(get_db)):
    import bcrypt
    from datetime import datetime as _dt
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    user = db.query(AdminUser).filter_by(username=username).first()
    if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        user.last_login = _dt.utcnow()
        db.commit()
        request.session["admin_username"] = user.username
        request.session["admin_role"] = user.role
        return RedirectResponse("/manage/", status_code=302)
    return templates.TemplateResponse(request, "manage/login.html",
                                      {"request": request, "error": "Identifiants incorrects."})


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/manage/login", status_code=302)


@router.post("/account/password")
async def account_password(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    current = form.get("current_password", "")
    new_pwd = form.get("new_password", "")
    confirm = form.get("confirm_password", "")

    admin = db.query(AdminUser).filter_by(username=user.username).first()

    if not bcrypt.checkpw(current.encode(), admin.password_hash.encode()):
        _set_flash(request, "Current password is incorrect.", "error")
    elif len(new_pwd) < 8:
        _set_flash(request, "New password must be at least 8 characters.", "error")
    elif new_pwd != confirm:
        _set_flash(request, "Passwords do not match.", "error")
    else:
        admin.password_hash = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
        db.commit()
        _set_flash(request, "Password updated successfully.")

    # Redirect back to the page the user was on
    referer = request.headers.get("referer", "/manage/")
    return RedirectResponse(referer, status_code=302)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    countries = _allowed_countries(user)

    def _filter(q):
        if user.role != "superadmin" and countries:
            return q.filter(Tournament.country.in_(countries))
        return q

    def _filter_players(q):
        if user.role != "superadmin" and countries:
            return q.filter(Player.nationality.in_(countries))
        return q

    nb_tournaments = _filter(db.query(func.count(Tournament.id))).scalar()
    nb_players = _filter_players(db.query(func.count(Player.id))).scalar()
    nb_cities = db.query(func.count(City.id)).scalar()

    ctx = _base_ctx(request, user, "dashboard")
    ctx.update({"nb_tournaments": nb_tournaments, "nb_players": nb_players, "nb_cities": nb_cities})
    return templates.TemplateResponse(request, "manage/dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Tournaments
# ---------------------------------------------------------------------------

@router.get("/tournaments/")
def tournaments_list(
    request: Request,
    q: str = "", rules: str = "", country: str = "",
    sort: str = "date", asc: int = 0,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    countries = _allowed_countries(user)

    qr = db.query(Tournament).outerjoin(City, Tournament.city_id == City.id)
    if user.role != "superadmin":
        qr = qr.filter(Tournament.country.in_(countries))
    if q:
        qr = qr.filter(Tournament.name.ilike(f"%{q}%") | City.name.ilike(f"%{q}%"))
    if rules:
        qr = qr.filter(Tournament.rules == rules)
    if country:
        qr = qr.filter(Tournament.country == country)

    col_map = {
        "date":    Tournament.start_date,
        "name":    Tournament.name,
        "city":    City.name,
        "country": Tournament.country,
        "players": Tournament.nb_players,
        "coeff":   Tournament.coefficient,
        "ema_id":  Tournament.ema_id,
    }
    order_col = col_map.get(sort, Tournament.start_date)
    qr = qr.order_by(order_col if asc else order_col.desc())

    total = qr.count()
    tournaments = qr.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    qs_parts = [f"q={q}", f"rules={rules}", f"country={country}"]
    qs = "&".join(p for p in qs_parts if p.split("=")[1])

    ctx = _base_ctx(request, user, "tournaments")
    ctx.update({
        "tournaments": tournaments,
        "q": q, "rules": rules, "country": country,
        "sort": sort, "asc": asc,
        "filter_countries": countries,
        "page": page, "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        "qs": qs,
    })
    return templates.TemplateResponse(request, "manage/tournaments.html", ctx)


def _championships_for_select(db: Session) -> list:
    return db.query(Championship).join(ChampionshipSeries).order_by(
        ChampionshipSeries.name, Championship.year.desc()
    ).all()


def _current_championship_id(db: Session, tournament_id: int) -> int | None:
    link = db.query(ChampionshipTournament).filter_by(tournament_id=tournament_id).first()
    return link.championship_id if link else None


def _save_championship_link(db: Session, tournament_id: int, championship_id: int | None):
    """Set or clear the championship link for a tournament."""
    existing = db.query(ChampionshipTournament).filter_by(tournament_id=tournament_id).first()
    if championship_id:
        if existing:
            existing.championship_id = championship_id
        else:
            db.add(ChampionshipTournament(tournament_id=tournament_id, championship_id=championship_id))
    elif existing:
        db.delete(existing)


@router.get("/tournaments/new")
def tournament_new(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    ctx = _base_ctx(request, user, "tournaments")
    ctx.update({
        "tournament": None,
        "cities": db.query(City).order_by(City.name).all(),
        "allowed_countries": _allowed_countries(user),
        "championships": _championships_for_select(db),
        "current_championship_id": None,
    })
    return templates.TemplateResponse(request, "manage/tournament_form.html", ctx)


@router.post("/tournaments/new")
async def tournament_new_post(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    allowed = _allowed_countries(user)
    country = form.get("country", "")
    if user.role != "superadmin" and country not in allowed:
        _set_flash(request, "Pays non autorisé.", "error")
        return RedirectResponse("/manage/tournaments/new", status_code=302)

    from app.ranking import mers_coefficient as _mcoeff
    t_type  = _resolve_tournament_type(form.get("tournament_type", "normal"), form.get("rules", "MCR"))
    ema_id  = _next_ema_id(db, form["rules"]) if t_type in EMA_TYPES else None
    start   = date.fromisoformat(form["start_date"])
    end     = date.fromisoformat(form["end_date"])
    nb_days = max(1, (end - start).days + 1)
    nb_p    = int(form["nb_players"])
    coeff   = _mcoeff(nb_days, nb_p, [], t_type)  # 0 countries until results are imported

    t = Tournament(
        ema_id=ema_id,
        rules=form["rules"],
        name=form["name"],
        city_id=_parse_city_id(form.get("city_id")),
        country=country,
        start_date=start,
        end_date=end,
        nb_players=nb_p,
        coefficient=coeff,
        tournament_type=t_type,
        status=form.get("status", "actif"),
        approval=form.get("approval") or None,
        website=form.get("website") or None,
    )
    db.add(t)
    db.flush()  # get t.id before commit

    champ_id = int(form["championship_id"]) if form.get("championship_id") else None
    _save_championship_link(db, t.id, champ_id)
    _audit(db, request, "CREATE", "tournaments", t.id,
           description=f"Created tournament «{t.name}»", new=t)
    db.commit()

    suffix = f" (ID EMA : {ema_id})" if ema_id else ""
    _set_flash(request, f"Tournoi « {t.name} » créé{suffix}.")
    return RedirectResponse("/manage/tournaments/", status_code=302)


@router.get("/tournaments/{tournament_id}/edit")
def tournament_edit(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    t = db.query(Tournament).filter_by(id=tournament_id).first()
    if not t:
        return RedirectResponse("/manage/tournaments/", status_code=302)
    allowed = _allowed_countries(user)
    if user.role != "superadmin" and t.country not in allowed:
        _set_flash(request, "Accès refusé.", "error")
        return RedirectResponse("/manage/tournaments/", status_code=302)

    ctx = _base_ctx(request, user, "tournaments")
    ctx.update({
        "tournament": t,
        "cities": db.query(City).order_by(City.name).all(),
        "allowed_countries": allowed,
        "championships": _championships_for_select(db),
        "current_championship_id": _current_championship_id(db, tournament_id),
        "referee_assignments": db.query(TournamentReferee).filter_by(tournament_id=tournament_id).all(),
    })
    return templates.TemplateResponse(request, "manage/tournament_form.html", ctx)


@router.post("/tournaments/{tournament_id}/edit")
async def tournament_edit_post(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    t = db.query(Tournament).filter_by(id=tournament_id).first()
    if not t:
        return RedirectResponse("/manage/tournaments/", status_code=302)
    allowed = _allowed_countries(user)
    if user.role != "superadmin" and t.country not in allowed:
        _set_flash(request, "Accès refusé.", "error")
        return RedirectResponse("/manage/tournaments/", status_code=302)

    form = await request.form()
    t_type = _resolve_tournament_type(form.get("tournament_type", t.tournament_type), form.get("rules", t.rules))

    # Assign ema_id if type changed to an EMA type and it had none
    if t_type in EMA_TYPES and not t.ema_id:
        t.ema_id = _next_ema_id(db, form.get("rules", t.rules))

    old_snapshot = _obj_to_dict(t)

    from app.ranking import mers_coefficient as _mcoeff
    t.rules      = form["rules"]
    t.name       = form["name"]
    t.country    = form["country"]
    t.city_id    = _parse_city_id(form.get("city_id"))
    t.start_date = date.fromisoformat(form["start_date"])
    t.end_date   = date.fromisoformat(form["end_date"])
    t.nb_players = int(form["nb_players"])
    t.tournament_type = t_type
    # Recompute coefficient from current results + updated dates/players
    nb_days = max(1, (t.end_date - t.start_date).days + 1)
    nats    = [r.nationality or "" for r in t.results]
    nats   += [a.nationality or "" for a in db.query(AnonymousResult).filter_by(tournament_id=t.id).all()]
    t.coefficient = _mcoeff(nb_days, t.nb_players, nats, t_type)
    t.status   = form.get("status", t.status)
    t.approval = form.get("approval") or None
    t.website  = form.get("website") or None

    champ_id = int(form["championship_id"]) if form.get("championship_id") else None
    _save_championship_link(db, t.id, champ_id)

    entry = AuditLog(
        admin_user=request.session.get("admin_username", "?"),
        action="UPDATE", table_name="tournaments", row_id=str(t.id),
        description=f"Updated tournament «{t.name}»",
        old_values=json.dumps(old_snapshot, default=str),
        new_values=json.dumps(_obj_to_dict(t), default=str),
    )
    db.add(entry)
    db.commit()
    _set_flash(request, f"Tournoi « {t.name} » mis à jour.")
    return RedirectResponse("/manage/tournaments/", status_code=302)


# ---------------------------------------------------------------------------
# Tournament observers / referees / report upload
# ---------------------------------------------------------------------------

@router.post("/tournaments/{tournament_id}/obs")
async def tournament_obs_post(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    """Save obs_observer field and optionally upload a PDF report."""
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    t = db.query(Tournament).filter_by(id=tournament_id).first()
    if not t:
        return JSONResponse({"error": "Not found"}, status_code=404)
    allowed = _allowed_countries(user)
    if user.role != "superadmin" and t.country not in allowed:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    form = await request.form()
    old_obs = t.obs_observer
    old_path = t.obs_report_path

    obs = form.get("obs_observer", "").strip()
    t.obs_observer = obs or None

    pdf_file: UploadFile | None = form.get("obs_report_file")
    if pdf_file and pdf_file.filename:
        import os as _os
        reports_dir = _os.path.join(_os.path.dirname(__file__), "../../app/static/obs_reports")
        _os.makedirs(reports_dir, exist_ok=True)
        prefix = f"TR{t.ema_id}" if t.ema_id else f"T{t.id}"
        safe_name = f"{prefix}_{pdf_file.filename}"
        dest = _os.path.join(reports_dir, safe_name)
        with open(dest, "wb") as f:
            f.write(await pdf_file.read())
        t.obs_report_path = f"/static/obs_reports/{safe_name}"

    changes = []
    if old_obs != t.obs_observer:
        changes.append(f"observer: {old_obs!r} → {t.obs_observer!r}")
    if old_path != t.obs_report_path:
        changes.append(f"report: {t.obs_report_path}")
    if changes:
        db.add(AuditLog(
            admin_user=request.session.get("admin_username", "?"),
            action="UPDATE", table_name="tournaments", row_id=str(t.id),
            description=f"Observer/report updated on «{t.name}»: {'; '.join(changes)}",
        ))

    db.commit()
    return JSONResponse({"ok": True, "obs_observer": t.obs_observer, "obs_report_path": t.obs_report_path})


@router.post("/tournaments/{tournament_id}/referees/add")
async def tournament_referee_add(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    """Add a referee assignment to a tournament."""
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    t = db.query(Tournament).filter_by(id=tournament_id).first()
    if not t:
        return JSONResponse({"error": "Not found"}, status_code=404)
    allowed = _allowed_countries(user)
    if user.role != "superadmin" and t.country not in allowed:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    data = await request.json()
    name      = (data.get("name") or "").strip()
    referee_id = data.get("referee_id")  # int or None
    player_id  = data.get("player_id")   # str or None

    if not name:
        return JSONResponse({"error": "Name required"}, status_code=400)

    ra = TournamentReferee(
        tournament_id=tournament_id,
        name=name,
        referee_id=int(referee_id) if referee_id else None,
        player_id=str(player_id) if player_id else None,
    )
    db.add(ra)
    db.add(AuditLog(
        admin_user=request.session.get("admin_username", "?"),
        action="CREATE", table_name="tournament_referees", row_id=str(tournament_id),
        description=f"Added referee «{name}» to «{t.name}»",
    ))
    db.commit()
    db.refresh(ra)
    return JSONResponse({"id": ra.id, "name": ra.name, "referee_id": ra.referee_id, "player_id": ra.player_id})


@router.post("/tournaments/{tournament_id}/referees/{ra_id}/remove")
async def tournament_referee_remove(tournament_id: int, ra_id: int, request: Request, db: Session = Depends(get_db)):
    """Remove a referee assignment from a tournament."""
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    t = db.query(Tournament).filter_by(id=tournament_id).first()
    if not t:
        return JSONResponse({"error": "Not found"}, status_code=404)
    allowed = _allowed_countries(user)
    if user.role != "superadmin" and t.country not in allowed:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    ra = db.query(TournamentReferee).filter_by(id=ra_id, tournament_id=tournament_id).first()
    if ra:
        db.add(AuditLog(
            admin_user=request.session.get("admin_username", "?"),
            action="DELETE", table_name="tournament_referees", row_id=str(tournament_id),
            description=f"Removed referee «{ra.name}» from «{t.name}»",
        ))
        db.delete(ra)
        db.commit()
    return JSONResponse({"ok": True})


@router.get("/tournaments/{tournament_id}/referees/search")
def tournament_referee_search(tournament_id: int, q: str, request: Request, db: Session = Depends(get_db)):
    """Search players and referees by name for autocomplete."""
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    q = q.strip().lower()
    if not q or len(q) < 2:
        return JSONResponse([])

    results = []
    # Search referees first
    refs = db.query(Referee).filter(
        Referee.name.ilike(f"%{q}%")
    ).limit(10).all()
    seen_player_ids = set()
    for r in refs:
        entry = {"type": "referee", "referee_id": r.id, "player_id": r.player_id, "rules": r.rules, "name": r.name}
        if r.player_id:
            seen_player_ids.add(r.player_id)
        results.append(entry)

    # Search players (not already covered via referee)
    players = db.query(Player).filter(
        (Player.last_name + " " + Player.first_name).ilike(f"%{q}%")
    ).limit(10).all()
    for p in players:
        if p.id not in seen_player_ids:
            results.append({"type": "player", "referee_id": None, "player_id": p.id, "rules": None,
                            "name": f"{p.last_name} {p.first_name}"})

    return JSONResponse(results[:15])


@router.get("/tournaments/{tournament_id}/results/template")
def tournament_results_template(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    t = db.query(Tournament).filter_by(id=tournament_id).first()
    name = t.name.replace(" ", "_")[:40] if t else "tournament"
    content = "position,ema_id,last_name,first_name,nationality,points,mahjong\n"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}_results.csv"'},
    )


@router.get("/tournaments/{tournament_id}/results")
def tournament_results(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    t = db.query(Tournament).filter_by(id=tournament_id).first()
    if not t:
        return RedirectResponse("/manage/tournaments/", status_code=302)

    results = db.query(Result).filter_by(tournament_id=tournament_id).order_by(Result.position).all()
    anon_results = db.query(AnonymousResult).filter_by(tournament_id=tournament_id).order_by(AnonymousResult.position).all()
    ctx = _base_ctx(request, user, "tournaments")
    ctx.update({"tournament": t, "results": results, "anon_results": anon_results})
    return templates.TemplateResponse(request, "manage/tournament_results.html", ctx)


@router.post("/tournaments/{tournament_id}/results/save")
async def tournament_results_save(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    t = db.query(Tournament).filter_by(id=tournament_id).first()
    if not t:
        return RedirectResponse("/manage/tournaments/", status_code=302)

    _take_snapshot(f"before_save_t{tournament_id}")

    from app.ranking import ema_points
    form = await request.form()

    # Delete removed rows (EMA results and anonymous results)
    deleted_ids = [i.strip() for i in form.get("deleted_ids", "").split(",") if i.strip()]
    for rid in deleted_ids:
        if rid.startswith("anon_"):
            anon_id = int(rid[5:])
            db.query(AnonymousResult).filter_by(id=anon_id, tournament_id=tournament_id).delete()
        else:
            try:
                db.query(Result).filter_by(id=int(rid), tournament_id=tournament_id).delete()
            except (ValueError, TypeError):
                pass

    # Collect all row keys (existing ids are integers, new rows are "new_N")
    result_ids = [k[len("result_id_"):] for k in form.keys() if k.startswith("result_id_")]
    updated, created, errors = 0, 0, []

    for rid in result_ids:
        position = int(form.get(f"position_{rid}", 1))
        points   = int(form.get(f"points_{rid}", 0))
        mahjong  = int(form.get(f"mahjong_{rid}", 0))
        ranking  = ema_points(position, t.nb_players)
        ema_id   = form.get(f"ema_id_{rid}", "").strip()
        last_name  = form.get(f"last_name_{rid}", "").strip().upper()
        first_name = form.get(f"first_name_{rid}", "").strip()
        nationality = form.get(f"nationality_{rid}", "").strip().upper()

        if rid.startswith("new_"):
            # New row
            if ema_id:
                player = db.query(Player).filter_by(id=ema_id).first()
                if not player:
                    if not last_name or not first_name or not nationality:
                        errors.append(f"New row: player {ema_id} not found and name/nationality missing.")
                        continue
                    player = Player(id=ema_id, last_name=last_name, first_name=first_name,
                                    nationality=nationality, status="europeen")
                    db.add(player)
                    db.flush()
                db.add(Result(tournament_id=tournament_id, player_id=player.id,
                               position=position, points=points, mahjong=mahjong, ranking=ranking,
                               nationality=player.nationality))
            else:
                if not nationality:
                    errors.append("New row: nationality required for anonymous result.")
                    continue
                db.add(AnonymousResult(tournament_id=tournament_id, position=position,
                                        nationality=nationality,
                                        last_name=last_name or None, first_name=first_name or None))
            created += 1
        elif rid.startswith("anon_"):
            # Existing anonymous result
            anon_id = int(rid[5:])
            anon = db.query(AnonymousResult).filter_by(id=anon_id, tournament_id=tournament_id).first()
            if not anon:
                continue

            if ema_id:
                # Convert anonymous → EMA result
                player = db.query(Player).filter_by(id=ema_id).first()
                if not player:
                    if not last_name or not first_name or not nationality:
                        errors.append(f"Anon row {anon_id}: player {ema_id} not found and name/nationality missing.")
                        continue
                    player = Player(id=ema_id, last_name=last_name, first_name=first_name,
                                    nationality=nationality or anon.nationality, status="europeen")
                    db.add(player)
                    db.flush()
                db.add(Result(tournament_id=tournament_id, player_id=player.id,
                               position=position, points=points, mahjong=mahjong, ranking=ranking,
                               nationality=player.nationality))
                db.delete(anon)
                created += 1
            else:
                # Update anonymous result fields
                anon.position    = position
                anon.last_name   = last_name or anon.last_name
                anon.first_name  = first_name or anon.first_name
                anon.nationality = nationality or anon.nationality
                anon.points      = points
                anon.mahjong     = mahjong
                anon.ranking     = ema_points(position, t.nb_players)
                updated += 1

        else:
            # Existing EMA result — update
            r = db.query(Result).filter_by(id=int(rid), tournament_id=tournament_id).first()
            if not r:
                continue
            r.position = position
            r.points   = points
            r.mahjong  = mahjong
            r.ranking  = ranking

            # Player change: if ema_id field was modified
            if ema_id and ema_id != r.player_id:
                player = db.query(Player).filter_by(id=ema_id).first()
                if not player:
                    if not last_name or not first_name or not nationality:
                        errors.append(f"Row {rid}: player {ema_id} not found and name/nationality missing.")
                        continue
                    player = Player(id=ema_id, last_name=last_name, first_name=first_name,
                                    nationality=nationality, status="europeen")
                    db.add(player)
                    db.flush()
                r.player_id   = player.id
                r.nationality = player.nationality
            elif not ema_id and last_name:
                # Name/nat correction on existing player
                if r.player:
                    r.player.last_name  = last_name
                    r.player.first_name = first_name or r.player.first_name
                    if nationality:
                        r.player.nationality = nationality
                        r.nationality = nationality
            updated += 1

    db.commit()
    parts = []
    if updated: parts.append(f"{updated} updated")
    if created: parts.append(f"{created} added")
    msg = ", ".join(parts) or "No changes."
    if errors:
        msg += " — Errors: " + " | ".join(errors[:5])

    _recompute_coefficient(t, db)
    nb_weeks = _recompute_tournament_weeks(t)
    if nb_weeks:
        msg += f" — Ranking recomputed for {nb_weeks} week{'s' if nb_weeks > 1 else ''}."

    _audit(db, request, "UPDATE", "results", tournament_id,
           description=f"Saved results for «{t.name}»: {msg}")
    db.commit()

    _set_flash(request, msg, "success" if not errors else "warning")
    return RedirectResponse(f"/manage/tournaments/{tournament_id}/results", status_code=302)


@router.post("/tournaments/{tournament_id}/results/import")
async def tournament_results_import(
    tournament_id: int, request: Request,
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    t = db.query(Tournament).filter_by(id=tournament_id).first()
    if not t:
        return RedirectResponse("/manage/tournaments/", status_code=302)

    # Snapshot before overwriting results
    _take_snapshot(f"before_import_t{tournament_id}")

    replace = True

    content = await csv_file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    # Normalize headers: lowercase + strip
    reader.fieldnames = [h.strip().lower() for h in (reader.fieldnames or [])]

    if replace:
        db.query(Result).filter_by(tournament_id=tournament_id).delete()
        db.query(AnonymousResult).filter_by(tournament_id=tournament_id).delete()

    from app.ranking import ema_points
    nb_players = t.nb_players

    imported, anon_imported, created, errors = 0, 0, 0, []
    for i, row in enumerate(reader, start=2):
        try:
            position    = int(row.get("position", 0))
            player_id   = row.get("ema_id", "").strip()
            points      = int(row.get("points", 0))
            mahjong     = int(row.get("mahjong", 0))
            ranking     = ema_points(position, nb_players)
            nationality = (row.get("nationality") or row.get("nationalite") or "").strip().upper()
            last_name   = (row.get("last_name") or row.get("nom") or "").strip().upper()
            first_name  = (row.get("first_name") or row.get("prenom") or "").strip()

            if not player_id:
                # No EMA ID → anonymous result, all fields required
                if not nationality or not last_name or not first_name:
                    errors.append(f"Row {i}: no ema_id — last_name, first_name and nationality are required.")
                    continue
                db.add(AnonymousResult(
                    tournament_id=tournament_id,
                    position=position,
                    nationality=nationality,
                    last_name=last_name,
                    first_name=first_name,
                ))
                anon_imported += 1

            else:
                player = db.query(Player).filter_by(id=player_id).first()
                if not player:
                    # Unknown EMA ID → create the player (all fields required)
                    if not nationality or not last_name or not first_name:
                        errors.append(f"Row {i}: player {player_id} not found — last_name, first_name and nationality are required to create it.")
                        continue
                    player = Player(
                        id=player_id,
                        last_name=last_name,
                        first_name=first_name,
                        nationality=nationality,
                        status="europeen",
                    )
                    db.add(player)
                    db.flush()
                    created += 1

                r = Result(
                    tournament_id=tournament_id,
                    player_id=player.id,
                    position=position,
                    points=points,
                    mahjong=mahjong,
                    ranking=ranking,
                    nationality=player.nationality,
                )
                db.merge(r) if not replace else db.add(r)
                imported += 1

        except Exception as e:
            errors.append(f"Row {i}: {e}")

    db.commit()
    parts = []
    if imported:   parts.append(f"{imported} result{'s' if imported > 1 else ''} imported")
    if created:    parts.append(f"{created} player{'s' if created > 1 else ''} created")
    if anon_imported: parts.append(f"{anon_imported} anonymous result{'s' if anon_imported > 1 else ''} imported")
    msg = ", ".join(parts) or "Nothing imported."
    if errors:
        msg += " — Errors: " + " | ".join(errors[:5])

    _recompute_coefficient(t, db)
    nb_weeks = _recompute_tournament_weeks(t)
    if nb_weeks:
        msg += f" — Ranking recomputed for {nb_weeks} week{'s' if nb_weeks > 1 else ''}."

    _audit(db, request, "IMPORT", "results", tournament_id,
           description=f"CSV import for «{t.name}»: {msg}")
    db.commit()

    _set_flash(request, msg, "success" if not errors else "warning")
    return RedirectResponse(f"/manage/tournaments/{tournament_id}/results", status_code=302)


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

@router.get("/players/")
def players_list(
    request: Request,
    q: str = "", country: str = "",
    sort: str = "name", asc: int = 1,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    countries = _allowed_countries(user)

    qr = db.query(Player)
    if user.role != "superadmin":
        qr = qr.filter(Player.nationality.in_(countries))
    if q:
        like = f"%{q}%"
        qr = qr.filter(Player.last_name.ilike(like) | Player.first_name.ilike(like) | Player.id.ilike(like))
    if country:
        qr = qr.filter(Player.nationality == country)

    col_map = {
        "id":          Player.id,
        "name":        Player.last_name,
        "first_name":  Player.first_name,
        "nationality": Player.nationality,
        "status":      Player.status,
    }
    order_col = col_map.get(sort, Player.last_name)
    qr = qr.order_by(order_col if asc else order_col.desc())

    total = qr.count()
    players = qr.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    qs_parts = [f"q={q}", f"country={country}"]
    qs = "&".join(p for p in qs_parts if p.split("=")[1])

    ctx = _base_ctx(request, user, "players")
    ctx.update({
        "players": players,
        "q": q, "country": country,
        "sort": sort, "asc": asc,
        "filter_countries": countries,
        "page": page, "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        "qs": qs,
    })
    return templates.TemplateResponse(request, "manage/players.html", ctx)


@router.get("/players/{player_id}/lookup")
def player_lookup(player_id: str, request: Request, db: Session = Depends(get_db)):
    """AJAX endpoint — returns player info by EMA ID."""
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return JSONResponse({"found": False})
    p = db.query(Player).filter_by(id=player_id.strip()).first()
    if not p:
        return JSONResponse({"found": False})
    return JSONResponse({
        "found": True,
        "id": p.id,
        "last_name": p.last_name,
        "first_name": p.first_name,
        "nationality": p.nationality,
    })


@router.get("/players/new")
def player_new(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    ctx = _base_ctx(request, user, "players")
    ctx.update({"player": None, "changements": [], "allowed_countries": _allowed_countries(user)})
    return templates.TemplateResponse(request, "manage/player_form.html", ctx)


@router.post("/players/new")
async def player_new_post(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    allowed = _allowed_countries(user)
    nationality = form.get("nationality", "")
    if user.role != "superadmin" and nationality not in allowed:
        _set_flash(request, "Pays non autorisé.", "error")
        return RedirectResponse("/manage/players/new", status_code=302)

    player_id = form.get("id", "").strip()
    if db.query(Player).filter_by(id=player_id).first():
        _set_flash(request, f"ID {player_id} déjà utilisé.", "error")
        return RedirectResponse("/manage/players/new", status_code=302)

    p = Player(
        id=player_id,
        last_name=form["last_name"].strip().upper(),
        first_name=form["first_name"].strip(),
        nationality=nationality,
        status=form.get("status", "europeen"),
    )
    db.add(p)
    db.flush()
    _audit(db, request, "CREATE", "players", p.id,
           description=f"Created player {p.first_name} {p.last_name}", new=p)
    db.commit()
    _set_flash(request, f"Joueur {p.first_name} {p.last_name} créé.")
    return RedirectResponse("/manage/players/", status_code=302)


@router.get("/players/{player_id}/edit")
def player_edit(player_id: str, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    p = db.query(Player).filter_by(id=player_id).first()
    if not p:
        return RedirectResponse("/manage/players/", status_code=302)
    allowed = _allowed_countries(user)
    if user.role != "superadmin" and p.nationality not in allowed:
        _set_flash(request, "Accès refusé.", "error")
        return RedirectResponse("/manage/players/", status_code=302)

    changements = db.query(NationalityChange).filter_by(player_id=player_id).order_by(NationalityChange.change_date).all()
    photo_path = os.path.join(os.path.dirname(__file__), "../static/photos", f"{player_id}.jpg")
    ctx = _base_ctx(request, user, "players")
    ctx.update({"player": p, "changements": changements, "allowed_countries": allowed, "player_photo": os.path.exists(photo_path)})
    return templates.TemplateResponse(request, "manage/player_form.html", ctx)


@router.post("/players/{player_id}/edit")
async def player_edit_post(player_id: str, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    p = db.query(Player).filter_by(id=player_id).first()
    if not p:
        return RedirectResponse("/manage/players/", status_code=302)
    allowed = _allowed_countries(user)
    if user.role != "superadmin" and p.nationality not in allowed:
        _set_flash(request, "Accès refusé.", "error")
        return RedirectResponse("/manage/players/", status_code=302)

    form = await request.form()
    new_nationality = form.get("nationality", p.nationality)

    # Record nationality change if needed
    if new_nationality != p.nationality:
        chg = NationalityChange(
            player_id=p.id,
            nationality_before=p.nationality,
            nationality_after=new_nationality,
            change_date=date.today(),
        )
        db.add(chg)

    old_snapshot = _obj_to_dict(p)
    p.last_name = form["last_name"].strip().upper()
    p.first_name = form["first_name"].strip()
    p.nationality = new_nationality
    p.status = form.get("status", p.status)
    entry = AuditLog(
        admin_user=request.session.get("admin_username", "?"),
        action="UPDATE", table_name="players", row_id=str(p.id),
        description=f"Updated player {p.first_name} {p.last_name}",
        old_values=json.dumps(old_snapshot, default=str),
        new_values=json.dumps(_obj_to_dict(p), default=str),
    )
    db.add(entry)
    db.commit()
    _set_flash(request, f"Joueur {p.first_name} {p.last_name} mis à jour.")
    return RedirectResponse("/manage/players/", status_code=302)


@router.post("/players/{player_id}/delete")
async def player_delete(player_id: str, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    p = db.query(Player).filter_by(id=player_id).first()
    if not p:
        return RedirectResponse("/manage/players/", status_code=302)

    # Check all linked data
    links = {
        "results":             db.query(Result).filter_by(player_id=player_id).count(),
        "ranking history":     db.query(RankingHistory).filter_by(player_id=player_id).count(),
        "referee records":     db.query(Referee).filter_by(player_id=player_id).count(),
        "referee assignments": db.query(TournamentReferee).filter_by(player_id=player_id).count(),
        "nationality changes": db.query(NationalityChange).filter_by(player_id=player_id).count(),
        "observed tournaments": db.query(Tournament).filter_by(obs_player_id=player_id).count(),
    }
    blocking = {k: v for k, v in links.items() if v > 0}
    if blocking:
        detail = ", ".join(f"{v} {k}" for k, v in blocking.items())
        _set_flash(request, f"Cannot delete {p.first_name} {p.last_name}: linked to {detail}.", "error")
        return RedirectResponse(f"/manage/players/{player_id}/edit", status_code=302)

    _audit(db, request, "DELETE", "players", p.id,
           description=f"Deleted player {p.first_name} {p.last_name} ({p.id})",
           old=p)
    db.delete(p)
    db.commit()

    # Remove photo if present
    photo = os.path.join(os.path.dirname(__file__), "../static/photos", f"{player_id}.jpg")
    if os.path.exists(photo):
        os.remove(photo)

    _set_flash(request, f"Player {p.first_name} {p.last_name} ({player_id}) deleted.")
    return RedirectResponse("/manage/players/", status_code=302)


PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "../static/photos")

@router.post("/players/{player_id}/photo")
async def player_photo_upload(player_id: str, request: Request, photo: UploadFile = File(...), db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    p = db.query(Player).filter_by(id=player_id).first()
    if not p:
        return RedirectResponse("/manage/players/", status_code=302)

    content = await photo.read()
    if len(content) > 5 * 1024 * 1024:
        _set_flash(request, "Photo trop lourde (max 5 Mo).", "error")
        return RedirectResponse(f"/manage/players/{player_id}/edit", status_code=302)

    os.makedirs(PHOTOS_DIR, exist_ok=True)
    dest = os.path.join(PHOTOS_DIR, f"{player_id}.jpg")
    with open(dest, "wb") as f:
        f.write(content)

    _set_flash(request, "Photo mise à jour.")
    return RedirectResponse(f"/manage/players/{player_id}/edit", status_code=302)


@router.post("/players/{player_id}/photo/delete")
async def player_photo_delete(player_id: str, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    dest = os.path.join(PHOTOS_DIR, f"{player_id}.jpg")
    if os.path.exists(dest):
        os.remove(dest)
        _set_flash(request, "Photo supprimée.")
    return RedirectResponse(f"/manage/players/{player_id}/edit", status_code=302)


# ---------------------------------------------------------------------------
# Cities
# ---------------------------------------------------------------------------

@router.get("/cities/")
def cities_list(
    request: Request,
    q: str = "",
    sort: str = "name", asc: int = 1,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user

    nb_col = func.count(Tournament.id).label("nb_tournaments")
    qr = db.query(City, nb_col)\
           .outerjoin(Tournament, Tournament.city_id == City.id)\
           .group_by(City.id)

    if q:
        qr = qr.filter(City.name.ilike(f"%{q}%") | City.country.ilike(f"%{q}%"))

    if user.role != "superadmin":
        allowed = _allowed_countries(user)
        if allowed:
            qr = qr.filter(City.country.in_(allowed))

    col_map = {
        "name":    City.name,
        "country": City.country,
        "lat":     City.latitude,
        "lon":     City.longitude,
        "nb":      nb_col,
    }
    order_col = col_map.get(sort, City.name)
    qr = qr.order_by(order_col if asc else order_col.desc())

    total = qr.count()
    rows = qr.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
    cities = [{"city": r[0], "nb_tournaments": r[1]} for r in rows]

    qs = f"q={q}" if q else ""
    ctx = _base_ctx(request, user, "cities")
    ctx.update({
        "cities": cities, "q": q,
        "sort": sort, "asc": asc,
        "page": page, "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        "qs": qs,
    })
    return templates.TemplateResponse(request, "manage/cities.html", ctx)


@router.post("/cities/delete")
async def cities_delete(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    ids = [int(i) for i in form.getlist("city_ids") if i.isdigit()]
    if not ids:
        _set_flash(request, "No cities selected.", "error")
        return RedirectResponse("/manage/cities/", status_code=302)

    deleted = 0
    for city_id in ids:
        c = db.query(City).filter_by(id=city_id).first()
        if c:
            _audit(db, request, "DELETE", "cities", city_id,
                   description=f"Deleted city «{c.name}» ({c.country})", old=c)
        db.query(Tournament).filter(Tournament.city_id == city_id).update({"city_id": None})
        db.query(City).filter_by(id=city_id).delete()
        deleted += 1

    db.commit()
    _set_flash(request, f"{deleted} cit{'ies' if deleted > 1 else 'y'} deleted.")
    return RedirectResponse("/manage/cities/", status_code=302)


@router.post("/cities/create-ajax")
async def city_create_ajax(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return JSONResponse({"error": "Non authentifié."}, status_code=401)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Requête invalide."}, status_code=400)

    name    = (data.get("name") or "").strip()
    country = (data.get("country") or "").strip().upper()
    try:
        lat = float(data["latitude"])
        lon = float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        return JSONResponse({"error": "Latitude et longitude invalides."})

    if not name or not country:
        return JSONResponse({"error": "Nom et pays sont obligatoires."})

    existing = db.query(City).filter_by(name=name, country=country).first()
    if existing:
        return JSONResponse({"error": f"La ville « {name} » ({country}) existe déjà.", "id": existing.id, "name": existing.name, "country": existing.country})

    c = City(name=name, country=country, latitude=lat, longitude=lon)
    db.add(c)
    db.flush()
    _audit(db, request, "CREATE", "cities", c.id,
           description=f"Created city «{c.name}» ({c.country})", new=c)
    db.commit()
    return JSONResponse({"id": c.id, "name": c.name, "country": c.country})


@router.post("/cities/merge-preview")
async def cities_merge_preview(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    ids = [int(i) for i in form.getlist("city_ids") if i.isdigit()]
    if len(ids) < 2:
        _set_flash(request, "Sélectionnez au moins 2 villes à fusionner.", "error")
        return RedirectResponse("/manage/cities/", status_code=302)

    rows = db.query(City, func.count(Tournament.id).label("nb_tournaments"))\
             .outerjoin(Tournament, Tournament.city_id == City.id)\
             .filter(City.id.in_(ids))\
             .group_by(City.id)\
             .order_by(func.count(Tournament.id).desc())\
             .all()

    if not rows:
        _set_flash(request, "Villes introuvables.", "error")
        return RedirectResponse("/manage/cities/", status_code=302)

    cities = [{"city": r[0], "nb_tournaments": r[1]} for r in rows]
    total_tournaments = sum(c["nb_tournaments"] for c in cities)

    ctx = _base_ctx(request, user, "cities")
    ctx.update({"cities": cities, "total_tournaments": total_tournaments})
    return templates.TemplateResponse(request, "manage/cities_merge.html", ctx)


@router.post("/cities/merge")
async def cities_merge(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    all_ids = [int(i) for i in form.getlist("city_ids") if i.isdigit()]
    keep_id = int(form.get("keep_id", 0))

    if keep_id not in all_ids or len(all_ids) < 2:
        _set_flash(request, "Sélection invalide.", "error")
        return RedirectResponse("/manage/cities/", status_code=302)

    drop_ids = [i for i in all_ids if i != keep_id]
    keep_city = db.query(City).filter_by(id=keep_id).first()
    if not keep_city:
        _set_flash(request, "Ville cible introuvable.", "error")
        return RedirectResponse("/manage/cities/", status_code=302)

    total_moved = 0
    sid = str(uuid.uuid4())[:8]
    for drop_id in drop_ids:
        drop_city = db.query(City).filter_by(id=drop_id).first()
        moved = db.query(Tournament).filter(Tournament.city_id == drop_id)\
                  .update({"city_id": keep_id})
        total_moved += moved
        if drop_city:
            _audit(db, request, "DELETE", "cities", drop_id,
                   description=f"Merged city «{drop_city.name}» into «{keep_city.name}»",
                   old=drop_city, session_id=sid)
        db.query(City).filter_by(id=drop_id).delete()

    db.commit()
    _set_flash(request, f"Fusion effectuée : {len(drop_ids)} ville(s) supprimée(s), {total_moved} tournoi(s) rattaché(s) à « {keep_city.name} ».")
    return RedirectResponse("/manage/cities/", status_code=302)


@router.get("/cities/new")
def city_new(request: Request):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    ctx = _base_ctx(request, user, "cities")
    ctx.update({"city": None, "allowed_countries": _allowed_countries(user)})
    return templates.TemplateResponse(request, "manage/city_form.html", ctx)


@router.post("/cities/new")
async def city_new_post(request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    c = City(
        name=form["name"].strip(),
        country=form["country"].strip().upper(),
        latitude=float(form["latitude"]),
        longitude=float(form["longitude"]),
    )
    db.add(c)
    db.flush()
    _audit(db, request, "CREATE", "cities", c.id,
           description=f"Created city «{c.name}» ({c.country})", new=c)
    db.commit()
    _set_flash(request, f"Ville « {c.name} » créée.")
    return RedirectResponse("/manage/cities/", status_code=302)


@router.get("/cities/{city_id}/edit")
def city_edit(city_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    c = db.query(City).filter_by(id=city_id).first()
    if not c:
        return RedirectResponse("/manage/cities/", status_code=302)
    city_tournaments = (
        db.query(Tournament)
        .filter(Tournament.city_id == city_id)
        .order_by(Tournament.start_date.desc())
        .all()
    )
    ctx = _base_ctx(request, user, "cities")
    ctx.update({"city": c, "allowed_countries": _allowed_countries(user),
                "city_tournaments": city_tournaments})
    return templates.TemplateResponse(request, "manage/city_form.html", ctx)


@router.post("/cities/{city_id}/edit")
async def city_edit_post(city_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    c = db.query(City).filter_by(id=city_id).first()
    if not c:
        return RedirectResponse("/manage/cities/", status_code=302)
    form = await request.form()
    old_snapshot = _obj_to_dict(c)
    c.name = form["name"].strip()
    c.country = form["country"].strip().upper()
    c.latitude = float(form["latitude"])
    c.longitude = float(form["longitude"])
    entry = AuditLog(
        admin_user=request.session.get("admin_username", "?"),
        action="UPDATE", table_name="cities", row_id=str(c.id),
        description=f"Updated city «{c.name}»",
        old_values=json.dumps(old_snapshot, default=str),
        new_values=json.dumps(_obj_to_dict(c), default=str),
    )
    db.add(entry)
    db.commit()
    _set_flash(request, f"Ville « {c.name} » mise à jour.")
    return RedirectResponse("/manage/cities/", status_code=302)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit/")
def audit_list(
    request: Request,
    page: int = Query(1, ge=1),
    table: str = "", action: str = "", admin: str = "",
    db: Session = Depends(get_db),
):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != "superadmin":
        _set_flash(request, "Access denied.", "error")
        return RedirectResponse("/manage/", status_code=302)

    qr = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if table:
        qr = qr.filter(AuditLog.table_name == table)
    if action:
        qr = qr.filter(AuditLog.action == action)
    if admin:
        qr = qr.filter(AuditLog.admin_user == admin)

    total = qr.count()
    entries = qr.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    tables  = [r[0] for r in db.query(AuditLog.table_name).distinct().order_by(AuditLog.table_name).all()]
    actions = [r[0] for r in db.query(AuditLog.action).distinct().order_by(AuditLog.action).all()]
    admins  = [r[0] for r in db.query(AuditLog.admin_user).distinct().order_by(AuditLog.admin_user).all()]

    # Build sorted list of (datetime, filename) from snapshot filenames
    _BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    _snapshots = []
    for f in sorted(_BACKUPS_DIR.glob("ranking_*.db")):
        try:
            parts = f.stem.split("_")
            ts = _dt.strptime(parts[1] + parts[2], "%Y%m%d%H%M%S")
            _snapshots.append((ts, f.name))
        except Exception:
            pass

    def _nearest_snapshot(entry_ts: _dt) -> str | None:
        """Return the most recent snapshot filename taken before entry_ts."""
        result = None
        for ts, name in _snapshots:
            if ts <= entry_ts:
                result = name
            else:
                break
        return result

    # Attach nearest snapshot to each entry
    entries_with_snap = [
        (e, _nearest_snapshot(e.timestamp))
        for e in entries
    ]

    ctx = _base_ctx(request, user, "audit")
    ctx.update({
        "entries_with_snap": entries_with_snap,
        "page": page, "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        "table": table, "action": action, "admin": admin,
        "tables": tables, "actions": actions, "admins": admins,
        "total": total,
    })
    return templates.TemplateResponse(request, "manage/audit.html", ctx)


@router.post("/audit/{entry_id}/undo")
async def audit_undo(entry_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != "superadmin":
        _set_flash(request, "Access denied.", "error")
        return RedirectResponse("/manage/", status_code=302)

    entry = db.query(AuditLog).filter_by(id=entry_id).first()
    if not entry:
        _set_flash(request, "Audit entry not found.", "error")
        return RedirectResponse("/manage/audit/", status_code=302)

    if entry.action not in ("UPDATE", "CREATE", "DELETE"):
        _set_flash(request, f"Action «{entry.action}» cannot be undone automatically.", "error")
        return RedirectResponse("/manage/audit/", status_code=302)

    # ── tournament_referees: special handling ────────────────────────────────
    if entry.table_name == "tournament_referees":
        try:
            tournament_id = int(entry.row_id)
            if entry.action == "CREATE":
                # Undo CREATE = find and delete the row matching description
                # row_id is tournament_id; find the last matching TournamentReferee
                # We stored the name in the description — parse it out
                import re as _re
                m = _re.search(r"Added referee «(.+?)»", entry.description or "")
                name = m.group(1) if m else None
                if name:
                    ra = db.query(TournamentReferee).filter_by(
                        tournament_id=tournament_id, name=name
                    ).order_by(TournamentReferee.id.desc()).first()
                    if ra:
                        db.delete(ra)
                        _audit(db, request, "UNDO", "tournament_referees", str(tournament_id),
                               description=f"Undid #{entry_id}: removed referee «{name}»")
                        db.commit()
                        _set_flash(request, f"Undone: removed referee «{name}».")
                    else:
                        _set_flash(request, "Referee row not found (already removed?).", "error")
                else:
                    _set_flash(request, "Cannot parse referee name from log.", "error")

            elif entry.action == "DELETE":
                # Undo DELETE = re-add the TournamentReferee row
                import re as _re
                m = _re.search(r"Removed referee «(.+?)»", entry.description or "")
                name = m.group(1) if m else None
                if name:
                    db.add(TournamentReferee(tournament_id=tournament_id, name=name))
                    _audit(db, request, "UNDO", "tournament_referees", str(tournament_id),
                           description=f"Undid #{entry_id}: restored referee «{name}»")
                    db.commit()
                    _set_flash(request, f"Undone: restored referee «{name}» (as free text, re-link manually if needed).")
                else:
                    _set_flash(request, "Cannot parse referee name from log.", "error")

            else:
                _set_flash(request, "UPDATE on tournament_referees not supported.", "error")
        except Exception as e:
            _set_flash(request, f"Undo failed: {e}", "error")
        return RedirectResponse("/manage/audit/", status_code=302)

    if entry.action == "DELETE":
        _set_flash(request, "DELETE cannot be undone automatically — restore a snapshot instead.", "error")
        return RedirectResponse("/manage/audit/", status_code=302)

    _TABLE_MODEL = {
        "tournaments": Tournament,
        "players":     Player,
        "cities":      City,
    }
    model = _TABLE_MODEL.get(entry.table_name)
    if not model:
        _set_flash(request, f"Table «{entry.table_name}» undo not supported.", "error")
        return RedirectResponse("/manage/audit/", status_code=302)

    try:
        old_data = json.loads(entry.old_values) if entry.old_values else None
        new_data = json.loads(entry.new_values) if entry.new_values else {}
        pk = entry.row_id if entry.table_name == "players" else int(entry.row_id)

        if entry.action == "UPDATE" and old_data:
            obj = db.get(model, pk)
            if not obj:
                _set_flash(request, "Row no longer exists.", "error")
                return RedirectResponse("/manage/audit/", status_code=302)

            # Restore all non-PK columns
            for col in obj.__table__.columns:
                if col.name in old_data and not col.primary_key:
                    val = old_data[col.name]
                    try:
                        setattr(obj, col.name, None if val == "None" else val)
                    except Exception:
                        pass

            # Player-specific: remove NationalityChange created by this edit
            if entry.table_name == "players":
                old_nat = old_data.get("nationality")
                new_nat = new_data.get("nationality")
                if old_nat and new_nat and old_nat != new_nat and old_nat != "None":
                    db.query(NationalityChange).filter_by(
                        player_id=entry.row_id,
                        nationality_before=old_nat,
                        nationality_after=new_nat,
                    ).delete()

            # Tournament-specific: recompute ranking_history after restoring dates/players/type
            if entry.table_name == "tournaments":
                db.flush()
                _recompute_tournament_weeks(obj)

            _audit(db, request, "UNDO", entry.table_name, entry.row_id,
                   description=f"Undid #{entry_id}: {entry.description}")
            db.commit()
            _set_flash(request, f"Undone: {entry.description}")

        elif entry.action == "CREATE":
            obj = db.get(model, pk)
            if not obj:
                _set_flash(request, "Row already gone.", "error")
                return RedirectResponse("/manage/audit/", status_code=302)

            # Remove dependents before deleting
            if entry.table_name == "tournaments":
                db.query(Result).filter_by(tournament_id=pk).delete()
                db.query(AnonymousResult).filter_by(tournament_id=pk).delete()
                db.query(ChampionshipTournament).filter_by(tournament_id=pk).delete()
            elif entry.table_name == "players":
                if db.query(Result).filter_by(player_id=entry.row_id).count():
                    _set_flash(request, "Cannot undo: player already has results.", "error")
                    return RedirectResponse("/manage/audit/", status_code=302)
            elif entry.table_name == "cities":
                # Unlink tournaments pointing to this city
                db.query(Tournament).filter_by(city_id=pk).update({"city_id": None})

            _audit(db, request, "UNDO", entry.table_name, entry.row_id,
                   description=f"Undid CREATE #{entry_id} — deleted row", old=obj)
            db.delete(obj)
            db.commit()
            _set_flash(request, f"Row deleted (undo of CREATE #{entry_id}).")

        else:
            _set_flash(request, "Nothing to undo.", "error")
    except Exception as e:
        _set_flash(request, f"Undo failed: {e}", "error")

    return RedirectResponse("/manage/audit/", status_code=302)


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------

@router.get("/backups/")
def backups_list(request: Request):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != "superadmin":
        _set_flash(request, "Access denied.", "error")
        return RedirectResponse("/manage/", status_code=302)

    _BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(_BACKUPS_DIR.glob("ranking_*.db"), reverse=True)
    backups = []
    for f in files:
        stat = f.stat()
        # Parse timestamp from filename (ranking_YYYYMMDD_HHMMSS_*.db) — more reliable than st_mtime
        try:
            parts = f.stem.split("_")  # ['ranking', 'YYYYMMDD', 'HHMMSS', ...]
            mtime = _dt.strptime(parts[1] + parts[2], "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            mtime = _dt.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        backups.append({
            "name": f.name,
            "size_kb": round(stat.st_size / 1024),
            "mtime": mtime,
        })

    ctx = _base_ctx(request, user, "backups")
    ctx["backups"] = backups
    return templates.TemplateResponse(request, "manage/backups.html", ctx)


@router.post("/backups/create")
async def backups_create(request: Request):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != "superadmin":
        _set_flash(request, "Access denied.", "error")
        return RedirectResponse("/manage/", status_code=302)
    dest = _take_snapshot("manual")
    _set_flash(request, f"Snapshot created: {dest.name}")
    return RedirectResponse("/manage/backups/", status_code=302)


@router.get("/backups/download/{filename}")
def backups_download(filename: str, request: Request):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != "superadmin":
        _set_flash(request, "Access denied.", "error")
        return RedirectResponse("/manage/", status_code=302)
    if not filename.startswith("ranking_") or not filename.endswith(".db") or "/" in filename:
        return JSONResponse({"error": "Invalid filename."}, status_code=400)
    path = _BACKUPS_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "File not found."}, status_code=404)
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@router.get("/bots/")
def bots_list(request: Request):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != "superadmin":
        _set_flash(request, "Access denied.", "error")
        return RedirectResponse("/manage/", status_code=302)

    from app.main import _bot_log, _ban_store
    import time as _time
    now = _time.time()
    banned = [
        {"ip": ip, "until": ban_until, "remaining": int(ban_until - now)}
        for ip, ban_until in sorted(_ban_store.items(), key=lambda x: -x[1])
        if ban_until > now
    ]
    ctx = _base_ctx(request, user, "bots")
    ctx.update({"events": list(reversed(_bot_log)), "banned": banned})
    return templates.TemplateResponse(request, "manage/bots.html", ctx)


@router.post("/bots/{ip}/unban")
def bot_unban(ip: str, request: Request):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    from app.main import _ban_store
    _ban_store.pop(ip, None)
    _set_flash(request, f"IP {ip} unbanned.")
    return RedirectResponse("/manage/bots/", status_code=302)


# ---------------------------------------------------------------------------
# Admins (superadmin only)
# ---------------------------------------------------------------------------

def _require_superadmin(request: Request):
    user = _require_auth(request)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != "superadmin":
        return RedirectResponse("/manage/", status_code=302)
    return user


@router.get("/admins/")
def admins_list(request: Request, db: Session = Depends(get_db)):
    user = _require_superadmin(request)
    if isinstance(user, RedirectResponse):
        return user
    admins = db.query(AdminUser).order_by(AdminUser.username).all()
    ctx = _base_ctx(request, user, "admins")
    ctx["admins"] = admins
    return templates.TemplateResponse(request, "manage/admins.html", ctx)


@router.post("/admins/create")
async def admins_create(request: Request, db: Session = Depends(get_db)):
    user = _require_superadmin(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    username  = form.get("username", "").strip()
    password  = form.get("password", "").strip()
    role      = form.get("role", "admin")
    countries = form.get("countries", "").strip()

    if not username or not password:
        _set_flash(request, "Username and password are required.", "error")
        return RedirectResponse("/manage/admins/", status_code=302)
    if len(password) < 8:
        _set_flash(request, "Password must be at least 8 characters.", "error")
        return RedirectResponse("/manage/admins/", status_code=302)
    if db.query(AdminUser).filter_by(username=username).first():
        _set_flash(request, f"Username '{username}' already exists.", "error")
        return RedirectResponse("/manage/admins/", status_code=302)
    if role not in ("superadmin", "admin"):
        role = "admin"

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    new_admin = AdminUser(
        username=username,
        password_hash=pw_hash,
        role=role,
        countries=countries or None,
    )
    db.add(new_admin)
    db.commit()
    _set_flash(request, f"Admin '{username}' created.")
    return RedirectResponse("/manage/admins/", status_code=302)


@router.post("/admins/{admin_id}/update")
async def admins_update(admin_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_superadmin(request)
    if isinstance(user, RedirectResponse):
        return user
    target = db.query(AdminUser).filter_by(id=admin_id).first()
    if not target:
        _set_flash(request, "Admin not found.", "error")
        return RedirectResponse("/manage/admins/", status_code=302)

    form = await request.form()
    new_username  = form.get("username", "").strip()
    new_password  = form.get("password", "").strip()
    new_role      = form.get("role", target.role)
    new_countries = form.get("countries", "").strip()

    if new_username and new_username != target.username:
        if db.query(AdminUser).filter_by(username=new_username).first():
            _set_flash(request, f"Username '{new_username}' already taken.", "error")
            return RedirectResponse("/manage/admins/", status_code=302)
        target.username = new_username

    if new_password:
        if len(new_password) < 8:
            _set_flash(request, "New password must be at least 8 characters.", "error")
            return RedirectResponse("/manage/admins/", status_code=302)
        target.password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

    if new_role in ("superadmin", "admin"):
        # Prevent removing own superadmin role
        if target.username == user.username and new_role != "superadmin":
            _set_flash(request, "You cannot remove your own superadmin role.", "error")
            return RedirectResponse("/manage/admins/", status_code=302)
        target.role = new_role

    target.countries = new_countries or None
    db.commit()
    _set_flash(request, f"Admin '{target.username}' updated.")
    return RedirectResponse("/manage/admins/", status_code=302)


@router.post("/admins/{admin_id}/delete")
async def admins_delete(admin_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_superadmin(request)
    if isinstance(user, RedirectResponse):
        return user
    target = db.query(AdminUser).filter_by(id=admin_id).first()
    if not target:
        _set_flash(request, "Admin not found.", "error")
        return RedirectResponse("/manage/admins/", status_code=302)
    if target.username == user.username:
        _set_flash(request, "You cannot delete your own account.", "error")
        return RedirectResponse("/manage/admins/", status_code=302)
    db.delete(target)
    db.commit()
    _set_flash(request, f"Admin '{target.username}' deleted.")
    return RedirectResponse("/manage/admins/", status_code=302)
