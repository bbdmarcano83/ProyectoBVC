import unittest

from services.fundamental_secondary_discovery_v5 import _same_curated_source, _tier_b


class FundamentalSecondaryDiscoveryV5Tests(unittest.TestCase):
    def test_curated_secondary_is_tier_b(self):
        evidence = _tier_b(
            "GMC.B",
            "https://www.accionavalores.com/assets/PROSPECTO-GRUPO-MANTRA.pdf",
        )
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.get("evidence_tier"), "B_SECONDARY")
        self.assertFalse(evidence.get("certified"))

    def test_unregistered_https_is_not_tier_b(self):
        self.assertIsNone(_tier_b("GMC.B", "https://example.com/report.pdf"))

    def test_cross_host_redirect_is_rejected(self):
        root = "https://www.accionavalores.com/assets/PROSPECTO-GRUPO-MANTRA.pdf"
        self.assertFalse(_same_curated_source("GMC.B", root, "https://example.com/report.pdf"))

    def test_curated_same_host_path_is_allowed(self):
        root = "https://es.marketscreener.com/cotizacion/accion/CERAMICA-CARABOBO-S-A-C-A-45418390/noticia/"
        candidate = "https://es.marketscreener.com/cotizacion/accion/CERAMICA-CARABOBO-S-A-C-A-45418390/noticia/estados-financieros.pdf"
        self.assertTrue(_same_curated_source("CCR", root, candidate))

    def test_other_symbols_cannot_reuse_curated_host(self):
        root = "https://www.accionavalores.com/assets/PROSPECTO-GRUPO-MANTRA.pdf"
        self.assertFalse(_same_curated_source("CCR", root, root))


if __name__ == "__main__":
    unittest.main()
