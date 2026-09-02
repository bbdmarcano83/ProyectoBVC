import unittest

from services.fundamental_discovery_v5 import _host_allowed, parse_candidate_links


class FundamentalDiscoveryV5Tests(unittest.TestCase):
    def test_host_guard_accepts_same_host_and_subdomain(self):
        self.assertTrue(_host_allowed("https://www.bncenlinea.com/a.pdf", "https://www.bncenlinea.com/bnc/informes-anuales"))
        self.assertTrue(_host_allowed("https://docs.bncenlinea.com/a.pdf", "https://bncenlinea.com/"))

    def test_host_guard_rejects_external_domain(self):
        self.assertFalse(_host_allowed("https://evil.example/a.pdf", "https://www.bncenlinea.com/"))

    def test_parser_keeps_only_relevant_official_links(self):
        html = '''
        <html><body>
          <a href="/docs/estado-financiero-2025.pdf">Estados financieros auditados 2025</a>
          <a href="/contacto">Contacto</a>
          <a href="https://evil.example/estado-financiero.pdf">PDF externo</a>
          <a href="/informes/gestion-2026">Informe de gestión</a>
        </body></html>
        '''
        docs = parse_candidate_links(html, "https://www.bncenlinea.com/bnc/", "https://www.bncenlinea.com/")
        urls = [d["url"] for d in docs]
        self.assertIn("https://www.bncenlinea.com/docs/estado-financiero-2025.pdf", urls)
        self.assertIn("https://www.bncenlinea.com/informes/gestion-2026", urls)
        self.assertNotIn("https://evil.example/estado-financiero.pdf", urls)
        self.assertEqual(len(docs), 2)

    def test_parser_accepts_registered_official_cdn(self):
        html = '<a href="https://d3q4nr72nuserl.cloudfront.net/audited-2025.pdf">Auditado 2025</a>'
        docs = parse_candidate_links(
            html,
            "https://www.bncenlinea.com/bnc/",
            "https://www.bncenlinea.com/",
            symbol="BNC",
        )
        self.assertEqual([d["url"] for d in docs], ["https://d3q4nr72nuserl.cloudfront.net/audited-2025.pdf"])


if __name__ == "__main__":
    unittest.main()
