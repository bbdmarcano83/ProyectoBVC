"""FastAPI application construction for Caracas Bull."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    app = FastAPI(title="Caracas Bull")
    app.mount("/static", StaticFiles(directory="static"), name="static")
    return app
