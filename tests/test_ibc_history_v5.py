import unittest

from services.ibc_history_v5 import normalize_auditable_points


class IBCHistoryV5Tests(unittest.TestCase):
    def test_official_bvc_wins_duplicate_date(self):
        points, meta = normalize_auditable_points([
            {"fecha": "30/12/2024", "cierre": "119.000,00", "source_url": "https://datosmacro.expansion.com/bolsa/venezuela"},
            {"date": "2024-12-30", "close": 119380.66, "source_url": "https://www.bolsadecaracas.com/resumen"},
        ])
        self.assertEqual(len(points), 1)
        self.assertAlmostEqual(points[0]["close"], 119380.66)
        self.assertTrue(points[0]["source_official"])
        self.assertEqual(meta["official_points"], 1)

    def test_unknown_source_is_rejected(self):
        points, meta = normalize_auditable_points([
            {"date": "2024-12-30", "close": 100, "source_url": "https://example.com/ibc"},
        ])
        self.assertEqual(points, [])
        self.assertEqual(meta["untrusted_points"], 1)

    def test_legacy_point_remains_readable_but_untrusted(self):
        points, meta = normalize_auditable_points([
            {"date": "2024-12-30", "close": 100},
        ])
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["source_confidence"], 0)
        self.assertEqual(meta["legacy_without_source"], 1)


if __name__ == "__main__":
    unittest.main()
