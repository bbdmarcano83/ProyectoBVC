import unittest

from services.fx_history_v5 import _full_year_fallback, VERIFIED_ANNUAL_FX_FALLBACK


class FxHistoryFallbackV5Tests(unittest.TestCase):
    def test_full_year_2022_has_verified_fallback(self):
        row = _full_year_fallback("2022-01-01", "2022-12-31", "FY2022")
        self.assertEqual(row, VERIFIED_ANNUAL_FX_FALLBACK[2022])
        self.assertEqual(row["close"], 17.489)
        self.assertEqual(row["average"], 6.7632)

    def test_full_year_2023_has_verified_fallback(self):
        row = _full_year_fallback("2023-01-01", "2023-12-31", "FY2023")
        self.assertEqual(row["close"], 35.959)
        self.assertEqual(row["average"], 28.780)

    def test_quarter_never_uses_annual_fallback(self):
        self.assertIsNone(_full_year_fallback("2023-10-01", "2023-12-31", "Q4-2023"))

    def test_partial_year_never_uses_annual_fallback(self):
        self.assertIsNone(_full_year_fallback("2023-01-01", "2023-09-30", "FY2023"))

    def test_unknown_year_fails_closed(self):
        self.assertIsNone(_full_year_fallback("2021-01-01", "2021-12-31", "FY2021"))


if __name__ == "__main__":
    unittest.main()
