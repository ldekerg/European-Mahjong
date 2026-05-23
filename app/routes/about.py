import json
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.params import Depends
from sqlalchemy.orm import Session, joinedload
from app.i18n import templates
from app.database import get_db
from app.models import Referee

router = APIRouter()

_ABOUT_PATH = Path(__file__).parent.parent.parent / "data" / "about.json"
_FEDS_PATH  = Path(__file__).parent.parent.parent / "data" / "federations.json"
_RULES_PATH = Path(__file__).parent.parent.parent / "data" / "rules.json"

with open(_ABOUT_PATH, encoding="utf-8") as _f:
    _ABOUT = json.load(_f)

with open(_FEDS_PATH, encoding="utf-8") as _f:
    _FEDERATIONS = json.load(_f)

with open(_RULES_PATH, encoding="utf-8") as _f:
    _RULES = json.load(_f)


@router.get("/rules")
def rules(request: Request):
    return templates.TemplateResponse(request, "rules.html", {"rules": _RULES})


@router.get("/referees")
def referees(request: Request, db: Session = Depends(get_db)):
    opts = [joinedload(Referee.city), joinedload(Referee.player)]
    mcr = db.query(Referee).options(*opts).filter(Referee.rules == "MCR").order_by(
        Referee.country, Referee.seminar_year, Referee.name
    ).all()
    rcr = db.query(Referee).options(*opts).filter(Referee.rules == "RCR").order_by(
        Referee.country, Referee.seminar_year, Referee.name
    ).all()
    return templates.TemplateResponse(request, "referees.html", {
        "mcr": mcr,
        "rcr": rcr,
    })


@router.get("/about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {
        "presidium":         _ABOUT["presidium"],
        "presidium_history": _ABOUT["presidium_history"],
        "board":             _ABOUT["board"],
        "documents":         _ABOUT["documents"],
        "federations":       _FEDERATIONS,
    })
