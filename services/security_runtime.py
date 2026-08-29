"""Security runtime compatible con el monolito actual.

Se instala antes de construir la instancia FastAPI mediante services.auth.
No usa persistencia; los contadores de rate-limit son deliberadamente locales.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
IS_PROD = APP_ENV in {"production", "prod"}


class _RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        cutoff = now - window
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


_LIMITER = _RateLimiter()


def _client_ip(request: Request) -> str:
    # En Render el proxy envía X-Forwarded-For. Tomamos sólo el primer hop.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _same_origin(request: Request) -> bool:
    host = request.headers.get("host", "").lower()
    origin = request.headers.get("origin", "").strip()
    referer = request.headers.get("referer", "").strip()
    source = origin or referer
    if not source:
        # Clientes no-browser / formularios antiguos: SameSite=Lax sigue siendo
        # barrera; en producción sólo se aplica bloqueo si hay cookie de sesión.
        return not IS_PROD
    try:
        return urlparse(source).netloc.lower() == host
    except Exception:
        return False


def _csrf_exempt(path: str) -> bool:
    p = path.lower()
    if "webhook" in p or "ipn" in p:
        return True
    return p in {"/api/alertas-cierre", "/health", "/healthz"}


def _limit_for(path: str) -> tuple[int, int] | None:
    p = path.lower()
    if p in {"/login", "/registro"}:
        return (10, 60)
    if "webhook" in p or "ipn" in p:
        return (90, 60)
    if p.startswith("/api/"):
        return (180, 60)
    return None


class RuntimeSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()
        ip = _client_ip(request)

        limit = _limit_for(path)
        if limit:
            max_hits, window = limit
            if not _LIMITER.allow(f"{ip}:{path}", max_hits, window):
                return JSONResponse({"detail": "Demasiadas solicitudes"}, status_code=429)

        if method in {"POST", "PUT", "PATCH", "DELETE"} and not _csrf_exempt(path):
            # Sólo exigimos same-origin cuando existe sesión; webhooks y APIs
            # servidor-a-servidor quedan fuera y deben autenticar por firma/clave.
            if request.cookies.get("access_token") and not _same_origin(request):
                return JSONResponse({"detail": "Origen no permitido"}, status_code=403)

        started = time.monotonic()
        response = await call_next(request)
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if IS_PROD:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        # Endurece la cookie creada por main.py sin obligar a reescribir rutas.
        if IS_PROD:
            raw = response.headers.get("set-cookie")
            if raw and "access_token=" in raw.lower() and "secure" not in raw.lower():
                response.headers["set-cookie"] = raw + "; Secure"

        if path.startswith("/api/") or path in {"/login", "/registro"}:
            print(f"[audit] {method} {path} status={response.status_code} ms={elapsed_ms} ip={ip}")
        return response


_INSTALLED = False


def install_fastapi_security_bootstrap() -> None:
    """Instala middleware en futuras instancias FastAPI de este proceso."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_init = FastAPI.__init__
    if getattr(original_init, "_caracasbull_security_wrapped", False):
        return

    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.add_middleware(RuntimeSecurityMiddleware)

    wrapped_init._caracasbull_security_wrapped = True  # type: ignore[attr-defined]
    FastAPI.__init__ = wrapped_init  # type: ignore[assignment]
