"""Auto-registro de rutas V5 sin reescribir el monolito main.py.

El bootstrap es reentrante y registra directamente el endpoint con
``add_api_route`` para evitar depender del estado interno de APIRouter durante
reloads/tests. La ruta no se duplica porque se comprueba el path antes de crearla.
"""
from __future__ import annotations

from fastapi import FastAPI


V5_BENCHMARK_PATH = "/api/v5/portfolio-benchmark"


def install_v5_routes_bootstrap() -> None:
    current_init = FastAPI.__init__

    def wrapped_init(self, *args, **kwargs):
        current_init(self, *args, **kwargs)
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
