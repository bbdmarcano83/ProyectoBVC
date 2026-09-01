import unittest

from services.fundamentals_v5 import _growth


class FundamentalGrowthV5Tests(unittest.TestCase):
    def test_cagr_uses_actual_elapsed_years_not_observation_count(self):
        # 100 -> 133.1 over ~3 years is ~10% CAGR, not 33.1%.
        out = _growth(
            [100.0, 133.1],
            ["2022-12-31", "2025-12-31"],
        )
        self.assertIsNotNone(out)
        self.assertAlmostEqual(out, 10.0, delta=0.03)

    def test_missing_intermediate_years_do_not_distort_cagr(self):
        out = _growth(
            [100.0, 110.0, 146.41],
            ["2021-12-31", "2022-12-31", "2025-12-31"],
        )
        self.assertIsNotNone(out)
        self.assertAlmostEqual(out, 10.0, delta=0.03)

    def test_legacy_series_without_dates_keeps_compatibility(self):
        out = _growth([100.0, 121.0])
        self.assertAlmostEqual(out, 21.0, places=6)

    def test_invalid_dates_fall_back_without_inventing_time_span(self):
        out = _growth([100.0, 121.0], ["bad-date", "also-bad"])
        self.assertAlmostEqual(out, 21.0, places=6)

    def test_zero_start_is_not_a_valid_growth_base(self):
        self.assertIsNone(_growth([0.0, 100.0], ["2022-12-31", "2025-12-31"]))


if __name__ == "__main__":
    unittest.main()
