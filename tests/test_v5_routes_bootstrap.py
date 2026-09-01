import unittest

import services  # noqa: F401 - instala bootstraps antes de crear FastAPI
from fastapi import FastAPI


class V5RoutesBootstrapTests(unittest.TestCase):
    def test_benchmark_route_is_registered_without_touching_main(self):
        app = FastAPI(title="test")
        paths = {getattr(route, "path", "") for route in app.routes}
        self.assertIn("/api/v5/portfolio-benchmark", paths)

    def test_route_is_get_only(self):
        app = FastAPI(title="test")
        route = next(r for r in app.routes if getattr(r, "path", "") == "/api/v5/portfolio-benchmark")
        self.assertIn("GET", route.methods)
        self.assertNotIn("POST", route.methods)


if __name__ == "__main__":
    unittest.main()
