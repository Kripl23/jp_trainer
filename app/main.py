from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import db
from app.logs import logger
from app.routers import pages, stats, training, words

BASE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.get_db()
    logger.info("jp_trainer started")
    yield
    await db.close_db()
    logger.info("jp_trainer stopped")


app = FastAPI(title="JP Trainer", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

app.include_router(pages.router)
app.include_router(training.router, prefix="/api")
app.include_router(words.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
