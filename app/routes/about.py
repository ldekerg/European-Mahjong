import json
from pathlib import Path
from fastapi import APIRouter, Request
from app.i18n import templates

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


@router.get("/about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {
        "presidium":         _ABOUT["presidium"],
        "presidium_history": _ABOUT["presidium_history"],
        "board":             _ABOUT["board"],
        "documents":         _ABOUT["documents"],
        "federations":       _FEDERATIONS,
    })
