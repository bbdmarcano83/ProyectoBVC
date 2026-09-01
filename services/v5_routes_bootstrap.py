"""Auto-registro de rutas V5 sin reescribir el monolito main.py.

La instalación se decide por el estado real de `FastAPI.__init__`, no por una
bandera global. Eso la hace idempotente incluso si otros tests/wrappers cambian
el orden de importación del framework.
"""
from __future__ import annotations

from fastapi import FastAPI


def install_v5_routes_bootstrap() -> None:
    current_init = FastAPI.__init__
    if getattr(current_init, "_caracasbull_v5_routes_wrapped", False):
        return

    def wrapped_init(self, *args, **kwargs):
        current_init(self, *args, **kwargs)
        # Import lazy para evitar ciclos durante el bootstrap del paquete services.
        from services.v5_routes import get_v5_router
        router = get_v5_router()
        # Protección adicional ante una reinstalación accidental del wrapper.
        if not any(getattr(route, "path", "") == "/api/v5/portfolio-benchmark" for route in self.routes):
            self.include_router(router)

    wrapped_init._caracasbull_v5_routes_wrapped = True  # type: ignore[attr-defined]
    FastAPI.__init__ = wrapped_init  # type: ignore[assignment]
