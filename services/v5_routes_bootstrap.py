"""Auto-registro de rutas V5 sin reescribir el monolito main.py.

El bootstrap es deliberadamente reentrante: otras capas/tests pueden envolver o
restaurar ``FastAPI.__init__`` después de nuestra primera instalación. Volver a
instalar el wrapper es seguro porque cada instancia comprueba el path antes de
incluir el router, de modo que nunca se duplica la ruta.
"""
from __future__ import annotations

from fastapi import FastAPI


V5_BENCHMARK_PATH = "/api/v5/portfolio-benchmark"


def install_v5_routes_bootstrap() -> None:
    """Asegura que las futuras instancias FastAPI incluyan las rutas V5.

    No usamos una bandera global ni retornamos por un marker previo: el orden de
    importación puede cambiar ``FastAPI.__init__`` durante una suite o reload.
    Reenvolver es inocuo porque ``wrapped_init`` comprueba las rutas existentes.
    """
    current_init = FastAPI.__init__

    def wrapped_init(self, *args, **kwargs):
        current_init(self, *args, **kwargs)
        # Import lazy para evitar ciclos durante el bootstrap del paquete services.
        from services.v5_routes import get_v5_router

        if not any(getattr(route, "path", "") == V5_BENCHMARK_PATH for route in self.routes):
            self.include_router(get_v5_router())

    wrapped_init._caracasbull_v5_routes_wrapped = True  # type: ignore[attr-defined]
    FastAPI.__init__ = wrapped_init  # type: ignore[assignment]
