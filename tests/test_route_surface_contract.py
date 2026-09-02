import unittest

import main
from scripts.route_inventory import digest


EXPECTED_ROUTE_DIGEST = "320f805508f4c2be6210ed8a40e77e610b1b2a5b1dfd5653c20226a2c5302079"


class RouteSurfaceContractTests(unittest.TestCase):
    def test_refactor_preserves_exact_http_surface(self):
        # Structural extraction may move handlers across modules; every legacy
        # method/path/name, including Watchlist, Admin and PWA, remains exact.
        self.assertEqual(digest(main.app), EXPECTED_ROUTE_DIGEST)


if __name__ == "__main__":
    unittest.main()
