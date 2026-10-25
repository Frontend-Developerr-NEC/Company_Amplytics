import os, secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import db
from web.routers import pages, api


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(
    title="Amplytics",
    version="0.2.0",
    description="Household electricity target tracking, baseline projection, and ML estimates.",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("AMPLYTICS_SECRET", secrets.token_urlsafe(32)),
    session_cookie="amplitics_session",
    max_age=60 * 60 * 24 * 30,
)

app.mount("/static", StaticFiles(directory="web/static"), name="static")
app.include_router(pages.router)
app.include_router(api.router, prefix="/api")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}