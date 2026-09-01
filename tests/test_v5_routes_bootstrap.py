import unittest

import services  # noqa: F401 - instala bootstraps al cargar el paquete
from fastapi import FastAPI
from services.v5_routes_bootstrap import install_v5_routes_bootstrap


class V5RoutesBootstrapTests(unittest.TestCase):
    def _app(self):
        # La suite puede haber envuelto/restaurado FastAPI.__init__ en otros tests.
        # El instalador debe poder verificarse/reaplicarse de forma idempotente.
        install_v5_routes_bootstrap()
        install_v5_routes_bootstrap()
        return FastAPI(title="test")

    def test_benchmark_route_is_registered_without_touching_main(self):
        app = self._app()
        paths = [getattr(route, "path", "") for route in app.routes]
        self.assertIn("/api/v5/portfolio-benchmark", paths)
        self.assertEqual(paths.count("/api/v5/portfolio-benchmark"), 1)

    def test_route_is_get_only(self):
        app = self._app()
        route = next(r for r in app.routes if getattr(r, "path", "") == "/api/v5/portfolio-benchmark")
        self.assertIn("GET", route.methods)
        self.assertNotIn("POST", route.methods)


if __name__ == "__main__":
    unittest.main()
