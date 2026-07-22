from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.get("/train")
async def train(request: Request, source: str, level: str, direction: str):
    return templates.TemplateResponse(
        request,
        "train.html",
        {"source": source, "level": level, "direction": direction},
    )


@router.get("/words")
async def words_page(request: Request):
    return templates.TemplateResponse(request, "words.html")


@router.get("/stats")
async def stats_page(request: Request):
    return templates.TemplateResponse(request, "stats.html")
