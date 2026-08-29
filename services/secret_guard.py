"""Fail-closed guard for legacy secret-protected endpoints."""
from __future__ import annotations

import os
import secrets

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class SecretGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/api/alertas-cierre":
            expected = os.environ.get("ALERTA_SECRET", "").strip()
            supplied = request.query_params.get("key", "")
            if len(expected) < 24:
                return JSONResponse({"detail": "ALERTA_SECRET no configurada"}, status_code=503)
            if not secrets.compare_digest(supplied, expected):
                return JSONResponse({"detail": "No autorizado"}, status_code=401)
        return await call_next(request)


_INSTALLED = False


def install_secret_guard() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    original_init = FastAPI.__init__
    if getattr(original_init, "_caracasbull_secret_guard", False):
        return

    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.add_middleware(SecretGuardMiddleware)

    wrapped_init._caracasbull_secret_guard = True  # type: ignore[attr-defined]
    FastAPI.__init__ = wrapped_init  # type: ignore[assignment]
