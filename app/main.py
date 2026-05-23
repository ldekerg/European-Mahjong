from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from typing import Optional
from sqlalchemy.orm import Session

from app.database import engine, SessionLocal, get_db
import app.models as models
from app.routes import players, tournaments, hof, championships
from app.routes import countries
from app.routes import formulas
from app.routes import about
from app.routes import manage
from app.routes import manage_championships
from app.i18n import templates
from app.models import RankingHistory, Player
from app.ranking import week_monday, ranking

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request as StarletteRequest
import bcrypt
from datetime import datetime as _dt


class AdminAuth(AuthenticationBackend):
    async def login(self, request: StarletteRequest) -> bool:
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")

        db = SessionLocal()
        try:
            from app.models import AdminUser
            user = db.query(AdminUser).filter_by(username=username).first()
            if not user:
                return False
            if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
                return False
            user.last_login = _dt.utcnow()
            db.commit()
            request.session["admin_username"] = user.username
            request.session["admin_role"] = user.role
            return True
        finally:
            db.close()

    async def logout(self, request: StarletteRequest) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: StarletteRequest) -> bool:
        return "admin_username" in request.session


def _is_superadmin(request: StarletteRequest) -> bool:
    return request.session.get("admin_role") == "superadmin"


from app.models import (
    Player as PlayerModel, Tournament as TournamentModel, Result as ResultModel,
    AnonymousResult, NationalityChange, City,
    ChampionshipSeries, Championship, ChampionshipTournament, RankingHistory as RankingHistoryModel,
)


class _AdminBase(ModelView):
    """Base view: read-only for admin, full access for superadmin."""
    def can_create(self, request: StarletteRequest) -> bool:
        return _is_superadmin(request)
    def can_edit(self, request: StarletteRequest) -> bool:
        return _is_superadmin(request)
    def can_delete(self, request: StarletteRequest) -> bool:
        return _is_superadmin(request)


class PlayerAdmin(_AdminBase, model=PlayerModel):
    name = "Player"
    name_plural = "Players"
    icon = "fa-solid fa-user"
    column_list = [PlayerModel.id, PlayerModel.last_name, PlayerModel.first_name,
                   PlayerModel.nationality, PlayerModel.status]
    column_searchable_list = [PlayerModel.id, PlayerModel.last_name, PlayerModel.first_name,
                               PlayerModel.nationality]
    column_sortable_list = [PlayerModel.id, PlayerModel.last_name, PlayerModel.first_name,
                             PlayerModel.nationality, PlayerModel.status]
    column_default_sort = [(PlayerModel.last_name, False)]


class TournamentAdmin(_AdminBase, model=TournamentModel):
    name = "Tournament"
    name_plural = "Tournaments"
    icon = "fa-solid fa-trophy"
    column_list = [TournamentModel.id, TournamentModel.ema_id, TournamentModel.rules,
                   TournamentModel.name, TournamentModel.city_id, TournamentModel.country,
                   TournamentModel.start_date, TournamentModel.nb_players,
                   TournamentModel.coefficient, TournamentModel.tournament_type,
                   TournamentModel.status]
    column_searchable_list = [TournamentModel.name, TournamentModel.country, TournamentModel.ema_id]
    column_sortable_list = [TournamentModel.id, TournamentModel.ema_id, TournamentModel.rules,
                             TournamentModel.start_date, TournamentModel.nb_players,
                             TournamentModel.coefficient, TournamentModel.country]
    column_default_sort = [(TournamentModel.start_date, True)]


class ResultAdmin(_AdminBase, model=ResultModel):
    name = "Result"
    name_plural = "Results"
    icon = "fa-solid fa-list-ol"
    column_list = [ResultModel.id, ResultModel.tournament_id, ResultModel.player_id,
                   ResultModel.position, ResultModel.points, ResultModel.ranking,
                   ResultModel.nationality]
    column_searchable_list = [ResultModel.player_id, ResultModel.tournament_id]
    column_sortable_list = [ResultModel.id, ResultModel.tournament_id, ResultModel.player_id,
                             ResultModel.position, ResultModel.ranking]


class AnonymousResultAdmin(_AdminBase, model=AnonymousResult):
    name = "Anonymous Result"
    name_plural = "Anonymous Results"
    icon = "fa-solid fa-user-secret"
    column_list = [AnonymousResult.id, AnonymousResult.tournament_id, AnonymousResult.position,
                   AnonymousResult.nationality, AnonymousResult.last_name, AnonymousResult.first_name]
    column_searchable_list = [AnonymousResult.tournament_id, AnonymousResult.last_name]


class NationalityChangeAdmin(_AdminBase, model=NationalityChange):
    name = "Nationality Change"
    name_plural = "Nationality Changes"
    icon = "fa-solid fa-flag"
    column_list = [NationalityChange.id, NationalityChange.player_id,
                   NationalityChange.nationality_before, NationalityChange.nationality_after,
                   NationalityChange.change_date]
    column_searchable_list = [NationalityChange.player_id]
    column_sortable_list = [NationalityChange.change_date, NationalityChange.player_id]


class CityAdmin(_AdminBase, model=City):
    name = "City"
    name_plural = "Cities"
    icon = "fa-solid fa-map-marker-alt"
    column_list = [City.id, City.name, City.country, City.latitude, City.longitude]
    column_searchable_list = [City.name, City.country]
    column_sortable_list = [City.name, City.country]


class ChampionshipSeriesAdmin(_AdminBase, model=ChampionshipSeries):
    name = "Championship Series"
    name_plural = "Championship Series"
    icon = "fa-solid fa-medal"
    column_list = [ChampionshipSeries.id, ChampionshipSeries.slug, ChampionshipSeries.name,
                   ChampionshipSeries.rules, ChampionshipSeries.country]
    column_searchable_list = [ChampionshipSeries.slug, ChampionshipSeries.name,
                               ChampionshipSeries.country]


class ChampionshipAdmin(_AdminBase, model=Championship):
    name = "Championship"
    name_plural = "Championships"
    icon = "fa-solid fa-crown"
    column_list = [Championship.id, Championship.series_id, Championship.year,
                   Championship.name, Championship.formula, Championship.champion_id]
    column_sortable_list = [Championship.year, Championship.series_id]


class ChampionshipTournamentAdmin(_AdminBase, model=ChampionshipTournament):
    name = "Championship Tournament"
    name_plural = "Championship Tournaments"
    icon = "fa-solid fa-link"
    column_list = [ChampionshipTournament.id, ChampionshipTournament.championship_id,
                   ChampionshipTournament.tournament_id]
    column_searchable_list = [ChampionshipTournament.championship_id,
                               ChampionshipTournament.tournament_id]


class RankingHistoryAdmin(_AdminBase, model=RankingHistoryModel):
    name = "Ranking History"
    name_plural = "Ranking History"
    icon = "fa-solid fa-chart-line"
    column_list = [RankingHistoryModel.id, RankingHistoryModel.week, RankingHistoryModel.rules,
                   RankingHistoryModel.player_id, RankingHistoryModel.position,
                   RankingHistoryModel.score, RankingHistoryModel.nb_tournaments]
    column_searchable_list = [RankingHistoryModel.player_id]
    column_sortable_list = [RankingHistoryModel.week, RankingHistoryModel.rules,
                             RankingHistoryModel.position, RankingHistoryModel.score]
    column_default_sort = [(RankingHistoryModel.week, True), (RankingHistoryModel.position, False)]


class AdminUserAdmin(_AdminBase, model=models.AdminUser):
    name = "Admin User"
    name_plural = "Admin Users"
    icon = "fa-solid fa-shield-halved"
    column_list = [models.AdminUser.id, models.AdminUser.username, models.AdminUser.role,
                   models.AdminUser.countries, models.AdminUser.created_at, models.AdminUser.last_login]
    column_sortable_list = [models.AdminUser.username, models.AdminUser.role,
                             models.AdminUser.created_at]
    form_excluded_columns = ["password_hash", "last_login", "created_at"]
    def can_create(self, request: StarletteRequest) -> bool:
        return False  # use CLI only
    def can_edit(self, request: StarletteRequest) -> bool:
        return False  # use CLI only
    def can_delete(self, request: StarletteRequest) -> bool:
        return _is_superadmin(request)

if os.getenv("DATABASE_URL"):
    models.Base.metadata.create_all(bind=engine)

from starlette.middleware.sessions import SessionMiddleware

# Rate limiter — 30 req/min per IP, applied only to public routes
limiter = Limiter(key_func=get_remote_address, default_limits=[])

app = FastAPI(title="EMA Ranking")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "ema-admin-secret"))
app.add_middleware(SlowAPIMiddleware)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

admin = Admin(app, engine, title="EMA Admin", base_url="/admin",
              authentication_backend=AdminAuth(secret_key=os.getenv("SECRET_KEY", "ema-admin-secret")))
admin.add_view(PlayerAdmin)
admin.add_view(TournamentAdmin)
admin.add_view(ResultAdmin)
admin.add_view(AnonymousResultAdmin)
admin.add_view(NationalityChangeAdmin)
admin.add_view(CityAdmin)
admin.add_view(ChampionshipSeriesAdmin)
admin.add_view(ChampionshipAdmin)
admin.add_view(ChampionshipTournamentAdmin)
admin.add_view(RankingHistoryAdmin)
admin.add_view(AdminUserAdmin)

app.include_router(players.router)
app.include_router(tournaments.router)
app.include_router(hof.router)
app.include_router(countries.router)
app.include_router(championships.router)
app.include_router(formulas.router)
app.include_router(about.router)
app.include_router(manage.router)
app.include_router(manage_championships.router)


def get_rank_delta(db: Session, week: date, regles: str) -> dict:
    """Returns {player_id: previous_week_position} to compute the rank delta."""
    from datetime import timedelta
    prev_week = week - timedelta(weeks=1)
    rows = db.query(RankingHistory.player_id, RankingHistory.position).filter(
        RankingHistory.week == prev_week,
        RankingHistory.rules == regles,
    ).all()
    return {r[0]: r[1] for r in rows}


def get_week_ranking(db: Session, week: date, regles: str) -> list:
    """Retrieves the ranking from history or computes it on the fly."""
    rows = (
        db.query(RankingHistory, Player)
        .join(Player, RankingHistory.player_id == Player.id)
        .filter(
            RankingHistory.week == week,
            RankingHistory.rules == regles,
        )
        .order_by(RankingHistory.position)
        .all()
    )
    if rows:
        return [
            {
                "position":    ch.position,
                "player_id":   ch.player_id,
                "name":         j.last_name,
                "first_name":      j.first_name,
                "nationality": j.nationality,
                "score":       ch.score,
                "nb_tournaments": ch.nb_tournaments or 0,
                "nb_gold":       ch.nb_gold or 0,
                "nb_silver":   ch.nb_silver or 0,
                "nb_bronze":   ch.nb_bronze or 0,
                "delta":       None,  # filled in later
            }
            for ch, j in rows
        ]
    # On-the-fly computation if week not yet stored
    raw = ranking(db, week, regles)
    players_map = {j.id: j for j in db.query(Player).all()}
    return [
        {
            "position":    r["position"],
            "player_id":   r["player_id"],
            "name":         players_map[r["player_id"]].last_name,
            "first_name":      players_map[r["player_id"]].first_name,
            "nationality": players_map[r["player_id"]].nationality,
            "score":       r["score"],
            "nb_tournaments": r["nb_tournaments"],
            "nb_gold":       r["nb_gold"],
            "nb_silver":   r["nb_silver"],
            "nb_bronze":   r["nb_bronze"],
        }
        for r in raw
        if r["player_id"] in players_map
    ]


PUBLIC_PREFIXES = ("/home", "/ranking", "/players", "/tournaments", "/countries",
                   "/hof", "/championships", "/ranking-system", "/classement", "/accueil",
                   "/joueurs", "/tournois", "/pays", "/palmares")

EXEMPT_PREFIXES = ("/static", "/manage", "/admin", "/verify")

_TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")
_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Simple in-memory rate limiter: 30 req/min per IP on public routes
import time, collections, urllib.request, urllib.parse
_rl_store: dict = collections.defaultdict(list)
_rl_limit = 30
_rl_window = 60  # seconds


@app.middleware("http")
async def captcha_and_rate_limit(request: Request, call_next):
    path = request.url.path

    # Skip exempt routes
    if any(path.startswith(p) for p in EXEMPT_PREFIXES):
        return await call_next(request)

    is_public = any(path.startswith(p) for p in PUBLIC_PREFIXES) or path == "/"

    if is_public:
        # 1. Rate limiting
        ip = get_remote_address(request)
        now = time.time()
        _rl_store[ip] = [t for t in _rl_store[ip] if t > now - _rl_window]
        if len(_rl_store[ip]) >= _rl_limit:
            return JSONResponse(
                {"detail": "Too many requests. Please slow down."},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        _rl_store[ip].append(now)

        # 2. Turnstile captcha — check via cookie directly (session not yet available in middleware)
        if _TURNSTILE_SECRET and request.cookies.get("human_verified") != "true":
            next_url = str(request.url)
            return RedirectResponse(f"/verify?next={urllib.parse.quote(next_url)}", status_code=302)

    return await call_next(request)


@app.get("/verify")
async def verify_get(request: Request, next: str = "/home"):
    from fastapi.templating import Jinja2Templates as _J
    from app.i18n import templates as _tpl
    return _tpl.TemplateResponse(request, "verify.html", {"next": next})


@app.post("/verify")
async def verify_post(request: Request):
    form = await request.form()
    token = form.get("cf-turnstile-response", "")
    next_url = form.get("next", "/home")

    verified = False
    if _TURNSTILE_SECRET and token:
        try:
            data = urllib.parse.urlencode({
                "secret": _TURNSTILE_SECRET,
                "response": token,
                "remoteip": get_remote_address(request),
            }).encode()
            req = urllib.request.Request(_TURNSTILE_VERIFY_URL, data=data)
            with urllib.request.urlopen(req, timeout=5) as resp:
                import json as _json
                result = _json.loads(resp.read())
                verified = result.get("success", False)
        except Exception:
            verified = False
    elif not _TURNSTILE_SECRET:
        # No secret configured (dev mode) — always pass
        verified = True

    if verified:
        response = RedirectResponse(next_url, status_code=302)
        # Cookie de session navigateur (expire à la fermeture du navigateur)
        response.set_cookie("human_verified", "true", httponly=True, samesite="lax")
        return response

    return RedirectResponse(f"/verify?next={urllib.parse.quote(next_url)}", status_code=302)


@app.get("/home")
def home(request: Request, db: Session = Depends(get_db)):
    from app.models import Tournament, Result, AnonymousResult
    from app.routes.hof import _meilleur_europeen
    from sqlalchemy import func, exists
    try:
        today = date.today()
        week_date = week_monday(today)

        # Global stats
        nb_players   = db.query(Player).filter(Player.status == "europeen").count()
        nb_tournaments  = db.query(Tournament).count()
        nb_classes_mcr = db.query(RankingHistory.player_id).filter(
            RankingHistory.week == week_date,
            RankingHistory.rules  == "MCR",
        ).distinct().count()
        nb_classes_rcr = db.query(RankingHistory.player_id).filter(
            RankingHistory.week == week_date,
            RankingHistory.rules  == "RCR",
        ).distinct().count()

        # Top 5 MCR and RCR
        def top5(rules):
            rows = (
                db.query(RankingHistory, Player)
                .join(Player, RankingHistory.player_id == Player.id)
                .filter(
                    RankingHistory.week == week_date,
                    RankingHistory.rules  == rules,
                )
                .order_by(RankingHistory.position)
                .limit(5).all()
            )
            return [{"position": ch.position, "player": j, "score": ch.score} for ch, j in rows]

        # Last played tournaments: with results AND past date
        has_resultats = exists().where(Result.tournament_id == Tournament.id)
        from datetime import date as _date
        recent = (
            db.query(Tournament)
            .filter(
                Tournament.start_date <= today,
                Tournament.start_date != _date(1900, 1, 1),
                has_resultats,
            )
            .order_by(Tournament.start_date.desc())
            .limit(8).all()
        )

        # Upcoming tournaments: future date AND no results
        has_no_resultats = ~exists().where(Result.tournament_id == Tournament.id)
        upcoming = (
            db.query(Tournament)
            .filter(
                Tournament.start_date > today,
                has_no_resultats,
                Tournament.tournament_type == "normal",
            )
            .order_by(Tournament.start_date)
            .limit(6).all()
        )

        # Calendar (for the compact home partial)
        from collections import defaultdict
        cal_tournaments = (
            db.query(Tournament)
            .filter(Tournament.status == "calendrier")
            .order_by(Tournament.start_date)
            .all()
        )
        cal_by_month = defaultdict(list)
        for t in cal_tournaments:
            cal_by_month[(t.start_date.year, t.start_date.month)].append(t)
        from app.i18n import _LOCALES, _detect_lang
        _lang = _detect_lang(request)
        _months = _LOCALES.get(_lang, _LOCALES.get("fr", {})).get("common", {}).get("months", [])
        calendar_by_month = [
            {"label": f"{_months[m-1]} {y}" if _months else f"{m}/{y}", "tournaments": ts}
            for (y, m), ts in sorted(cal_by_month.items())
        ]

        recent_calendar = (
            db.query(Tournament)
            .filter(Tournament.status == "calendrier", Tournament.created_at.isnot(None))
            .order_by(Tournament.created_at.desc())
            .limit(5)
            .all()
        )

        # Reigning champions
        champions = {
            "oemc": _meilleur_europeen(db, "oemc"),
            "wmc":  _meilleur_europeen(db, "wmc"),
            "oerc": _meilleur_europeen(db, "oerc"),
            "wrc":  _meilleur_europeen(db, "wrc"),
        }

    finally:
        pass

    return templates.TemplateResponse(request, "home.html", {
        "nb_players":    nb_players,
        "nb_tournaments":   nb_tournaments,
        "nb_classes_mcr": nb_classes_mcr,
        "nb_classes_rcr": nb_classes_rcr,
        "top_mcr":       top5("MCR"),
        "top_rcr":       top5("RCR"),
        "recent":           recent,
        "upcoming":          upcoming,
        "champions":          champions,
        "calendar_by_month": calendar_by_month,
        "recent_calendar":   recent_calendar,
    })


@app.get("/ranking")
def accueil(
    request: Request,
    week: Optional[str] = Query(None),
    player_filter: Optional[str] = Query(None),
    rules: Optional[str] = Query(None),  # active tab to display (MCR or RCR)
    db: Session = Depends(get_db),
):
    try:
        if week:
            try:
                week_date = week_monday(date.fromisoformat(week))
            except ValueError:
                week_date = week_monday(date.today())
        else:
            week_date = week_monday(date.today())

        mcr = get_week_ranking(db, week_date, "MCR")
        rcr = get_week_ranking(db, week_date, "RCR")

        # Compute rank delta
        for lst, rules_key in [(mcr, "MCR"), (rcr, "RCR")]:
            prev = get_rank_delta(db, week_date, rules_key)
            for r in lst:
                p = prev.get(r["player_id"])
                r["delta"] = (p - r["position"]) if p else None  # positive = moved up

        # All weeks for prev/next navigation
        weeks_raw = [
            row[0] for row in
            db.query(RankingHistory.week)
            .filter(RankingHistory.rules == "MCR")
            .distinct()
            .order_by(RankingHistory.week)
            .all()
        ]
        total = len(weeks_raw)
        current_idx = next((i for i, s in enumerate(weeks_raw) if s == week_date), total - 1)
        week_prev = weeks_raw[current_idx - 1].isoformat() if current_idx > 0 else None
        week_next = weeks_raw[current_idx + 1].isoformat() if current_idx < total - 1 else None

        # Dropdown: all weeks grouped by year
        from collections import defaultdict
        by_year: dict = defaultdict(list)
        for i, s in enumerate(weeks_raw):
            by_year[s.year].append({"date": s, "num": i + 1})
        available_weeks = [
            {"year": yr, "weeks": list(reversed(wks))}
            for yr, wks in sorted(by_year.items(), reverse=True)
        ]
    finally:
        pass

    current_week = week_monday(date.today())
    today_date = date.today()

    return templates.TemplateResponse(request, "ranking.html", {
        "mcr": mcr,
        "rcr": rcr,
        "current_week": current_week,
        "today_date": today_date,
        "week": week_date,
        "week_num": current_idx + 1,
        "week_prev": week_prev,
        "week_next": week_next,
        "available_weeks": available_weeks,
        "selected_player": player_filter,
        "active_tab": (rules or "MCR").upper(),
        "default_player": mcr[0]["player_id"] if mcr else None,
        "default_player_mcr": mcr[0]["player_id"] if mcr else None,
        "default_player_rcr": rcr[0]["player_id"] if rcr else None,
    })


@app.get("/")
def root():
    return RedirectResponse(url="/home")


# ---------------------------------------------------------------------------
# Legacy URL redirections (old French route names)
# ---------------------------------------------------------------------------

@app.get("/classement")
def legacy_classement(request: Request):
    # Preserve query params: ?joueur=X&regles=Y&semaine=Z → /ranking?player_filter=X&rules=Y&week=Z
    p = request.query_params
    params = {}
    if p.get("joueur"):       params["player_filter"] = p["joueur"]
    if p.get("regles"):       params["rules"]         = p["regles"]
    if p.get("semaine"):      params["week"]           = p["semaine"]
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"/ranking{'?' + qs if qs else ''}", status_code=301)

@app.get("/accueil")
def legacy_accueil():
    return RedirectResponse("/home", status_code=301)

@app.get("/joueurs")
@app.get("/joueurs/")
def legacy_joueurs():
    return RedirectResponse("/players/", status_code=301)

@app.get("/joueurs/{player_id}")
def legacy_joueur(player_id: str):
    return RedirectResponse(f"/players/{player_id}", status_code=301)

@app.get("/tournois")
@app.get("/tournois/")
def legacy_tournois():
    return RedirectResponse("/tournaments/", status_code=301)

@app.get("/tournois/{path:path}")
def legacy_tournoi(path: str):
    return RedirectResponse(f"/tournaments/{path}", status_code=301)

@app.get("/pays")
@app.get("/pays/")
def legacy_pays():
    return RedirectResponse("/countries/", status_code=301)

@app.get("/pays/{code}")
def legacy_pays_detail(code: str):
    return RedirectResponse(f"/countries/{code}", status_code=301)

@app.get("/palmares")
@app.get("/palmares/")
def legacy_palmares():
    return RedirectResponse("/hof/", status_code=301)
