from fastapi import APIRouter, Request
from app.i18n import templates

router = APIRouter()


@router.get("/formulas")
def formulas(request: Request):
    return templates.TemplateResponse(request, "formulas.html", {})
