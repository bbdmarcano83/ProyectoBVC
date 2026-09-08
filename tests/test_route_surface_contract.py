import unittest

import main
from scripts.route_inventory import digest


# Intentional surface expansion: POST /portafolio/historial-inicial lets an
# imported position obtain audited historical-USD metrics without replacing
# its acquisition FX with today's rate.
EXPECTED_ROUTE_DIGEST = "d16f4c4ae98799161186ba1859ec4510536bf94bdaa4ad5141d6096090dd0a2a"


class RouteSurfaceContractTests(unittest.TestCase):
    def test_refactor_preserves_exact_http_surface(self):
        # The modularized app may move handlers across router modules, including
        # duplicate legacy Telegram/Alertas/Chat registrations, but every
        # method/path/name in the approved HTTP surface must remain exact.
        self.assertEqual(digest(main.app), EXPECTED_ROUTE_DIGEST)


if __name__ == "__main__":
    unittest.main()
