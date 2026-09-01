import os
import unittest

import services  # noqa: F401 - instala bootstraps al cargar el paquete
from fastapi import FastAPI
from services.v5_routes_bootstrap import V5_BENCHMARK_PATH, install_v5_routes_bootstrap


class V5RoutesBootstrapTests(unittest.TestCase):
    FLAG = "PORTFOLIO_IBC_BENCHMARK_V5_ENABLED"

    def tearDown(self):
        os.environ.pop(self.FLAG, None)

    def _app(self, enabled: bool):
        os.environ[self.FLAG] = "true" if enabled else "false"
        # El instalador debe ser idempotente aun si otros tests ya importaron services.
        install_v5_routes_bootstrap()
        install_v5_routes_bootstrap()
        return FastAPI(title="test")

    def test_benchmark_route_is_absent_when_flag_is_disabled(self):
        app = self._app(False)
        paths = [getattr(route, "path", "") for route in app.routes]
        self.assertNotIn(V5_BENCHMARK_PATH, paths)

    def test_benchmark_route_is_registered_once_when_flag_is_enabled(self):
        app = self._app(True)
        paths = [getattr(route, "path", "") for route in app.routes]
        self.assertIn(V5_BENCHMARK_PATH, paths)
        self.assertEqual(paths.count(V5_BENCHMARK_PATH), 1)

    def test_route_is_get_only_when_enabled(self):
        app = self._app(True)
        route = next(r for r in app.routes if getattr(r, "path", "") == V5_BENCHMARK_PATH)
        self.assertIn("GET", route.methods)
        self.assertNotIn("POST", route.methods)


if __name__ == "__main__":
    unittest.main()
