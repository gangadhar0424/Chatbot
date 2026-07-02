"""Standalone FastAPI app for the ai-system-pattern rebuild (parallel track).

Runs entirely separate from backend/app/main.py (which stays untouched as the
comparison baseline) — its own port, its own SQLite file, its own router
module. Run with:

    uvicorn backend.web_app:app --port 8001 --reload

Milestone 6: also serves the plain-HTML/JS web/ frontend as static files —
same origin as the API, so no CORS setup is needed here.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.prd_routes import setup_prd_routes
from app.web_db import Base, engine
import app.web_models  # noqa: F401 — registers IntakeSession with Base.metadata

load_dotenv()

Base.metadata.create_all(bind=engine)

_WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")

app = FastAPI(title="Project-intake chatbot (web rebuild)", version="0.1.0")
app.include_router(setup_prd_routes())


@app.get("/health")
async def health():
    return {"status": "ok"}


# Mounted last so /health and /api/prd/* are matched first.
app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
