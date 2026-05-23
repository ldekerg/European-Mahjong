import json
from pathlib import Path
from fastapi import APIRouter, Request
from app.i18n import templates

router = APIRouter()

_ABOUT_PATH = Path(__file__).parent.parent.parent / "data" / "about.json"
_FEDS_PATH  = Path(__file__).parent.parent.parent / "data" / "federations.json"

with open(_ABOUT_PATH, encoding="utf-8") as _f:
    _ABOUT = json.load(_f)

with open(_FEDS_PATH, encoding="utf-8") as _f:
    _FEDERATIONS = json.load(_f)


@router.get("/about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {
        "presidium":         _ABOUT["presidium"],
        "presidium_history": _ABOUT["presidium_history"],
        "board":             _ABOUT["board"],
        "documents":         _ABOUT["documents"],
        "federations":       _FEDERATIONS,
    })
