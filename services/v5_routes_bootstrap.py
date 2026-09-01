"""Auto-registro de rutas V5 sin reescribir el monolito main.py."""
from __future__ import annotations

from fastapi import FastAPI

_INSTALLED = False


def install_v5_routes_bootstrap() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_init = FastAPI.__init__
    if getattr(original_init, "_caracasbull_v5_routes_wrapped", False):
        return

    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        # Import lazy para evitar ciclos durante el bootstrap del paquete services.
        from services.v5_routes import get_v5_router
        self.include_router(get_v5_router())

    wrapped_init._caracasbull_v5_routes_wrapped = True  # type: ignore[attr-defined]
    FastAPI.__init__ = wrapped_init  # type: ignore[assignment]
