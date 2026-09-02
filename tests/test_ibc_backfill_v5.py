import unittest

from services.ibc_backfill_v5 import month_url, parse_datosmacro_history


class IBCBackfillV5Tests(unittest.TestCase):
    def test_month_url_is_deterministic(self):
        self.assertEqual(
            month_url(2026, 8),
            "https://datosmacro.expansion.com/bolsa/venezuela?dr=2026-08",
        )

    def test_parser_extracts_date_level_and_source(self):
        html = """
        <table>
          <tr><td>29/08/2026</td><td>5.625,11</td><td>0</td></tr>
          <tr><td>28/08/2026</td><td>5.625,11</td><td>-0,52%</td></tr>
        </table>
        """
        url = month_url(2026, 8)
        rows = parse_datosmacro_history(html, source_url=url)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["date"], "2026-08-28")
        self.assertAlmostEqual(rows[0]["close"], 5625.11)
        self.assertEqual(rows[0]["source_url"], url)

    def test_unknown_domain_fails_closed(self):
        rows = parse_datosmacro_history(
            "29/08/2026 5.625,11",
            source_url="https://example.com/history",
        )
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
