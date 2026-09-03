import unittest

import main
from scripts.route_inventory import digest


# Intentional surface expansion: POST /reducir adds safe partial/full portfolio
# sales while preserving every pre-existing route.
EXPECTED_ROUTE_DIGEST = "33f6791e865925baded174d3f9f99b6eb7f82c3f5dbafe4c0ed4dc54ca58d395"


class RouteSurfaceContractTests(unittest.TestCase):
    def test_refactor_preserves_exact_http_surface(self):
        # The modularized app may move handlers across router modules, including
        # duplicate legacy Telegram/Alertas/Chat registrations, but every
        # method/path/name in the approved HTTP surface must remain exact.
        self.assertEqual(digest(main.app), EXPECTED_ROUTE_DIGEST)


if __name__ == "__main__":
    unittest.main()
