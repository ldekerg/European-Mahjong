from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from app.i18n import templates

router = APIRouter()


@router.get("/ranking-system")
def ranking_system(request: Request):
    return templates.TemplateResponse(request, "formulas.html", {})


@router.get("/formulas")
def formulas_redirect(request: Request):
    return RedirectResponse(url="/ranking-system", status_code=301)
