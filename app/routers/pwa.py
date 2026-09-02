"""PWA/static-file handlers extracted from legacy main.py."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse


async def favicon_ico():
    return FileResponse("static/logo.png", media_type="image/png")


async def favicon_png():
    return FileResponse("static/logo.png", media_type="image/png")


async def manifest():
    return FileResponse("static/manifest.json", media_type="application/manifest+json")


async def service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript")


def register_pwa_routes(app: FastAPI) -> None:
    app.add_api_route("/favicon.ico", favicon_ico, methods=["GET"])
    app.add_api_route("/favicon.png", favicon_png, methods=["GET"])
    app.add_api_route("/manifest.json", manifest, methods=["GET"])
    app.add_api_route("/sw.js", service_worker, methods=["GET"])
