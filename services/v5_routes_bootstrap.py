"""Auto-registro controlado de rutas V5 sin reescribir el monolito main.py.

El bootstrap es reentrante y registra directamente el endpoint con
``add_api_route`` para evitar depender del estado interno de APIRouter durante
reloads/tests. El benchmark Portafolio vs IBC es opt-in: con su feature flag
apagado la ruta ni siquiera se registra, evitando trabajo/snapshots ocultos.
"""
from __future__ import annotations

from fastapi import FastAPI

from services.feature_flags import portfolio_ibc_benchmark_v5_enabled


V5_BENCHMARK_PATH = "/api/v5/portfolio-benchmark"


def install_v5_routes_bootstrap() -> None:
    current_init = FastAPI.__init__
    if getattr(current_init, "_caracasbull_v5_routes_wrapped", False):
        return

    def wrapped_init(self, *args, **kwargs):
        current_init(self, *args, **kwargs)
        if not portfolio_ibc_benchmark_v5_enabled():
            return
        if any(getattr(route, "path", "") == V5_BENCHMARK_PATH for route in self.routes):
            return
        from services.v5_routes import portfolio_benchmark_v5
        self.add_api_route(
            V5_BENCHMARK_PATH,
            portfolio_benchmark_v5,
            methods=["GET"],
        )

    wrapped_init._caracasbull_v5_routes_wrapped = True  # type: ignore[attr-defined]
    FastAPI.__init__ = wrapped_init  # type: ignore[assignment]
