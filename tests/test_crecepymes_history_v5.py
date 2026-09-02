import unittest

from services.crecepymes_history_v5 import CRECEPYMES_HISTORICAL_PILOTS
from services.fundamental_store_v5 import validate_snapshot


class CrecePymesHistoryV5Tests(unittest.TestCase):
    def test_only_independently_verified_primary_years_are_present(self):
        self.assertEqual(
            [row["fiscal_period"] for row in CRECEPYMES_HISTORICAL_PILOTS],
            ["FY2024", "FY2022"],
        )
        self.assertNotIn(
            "FY2023",
            [row["fiscal_period"] for row in CRECEPYMES_HISTORICAL_PILOTS],
        )

    def test_each_year_is_audited_and_uses_its_own_closing_monetary_basis(self):
        self.assertTrue(all(row["audited"] for row in CRECEPYMES_HISTORICAL_PILOTS))
        self.assertTrue(
            all(
                row["data"]["monetary_basis"] == "constant_ves_end_period"
                for row in CRECEPYMES_HISTORICAL_PILOTS
            )
        )
        self.assertEqual(
            [row["as_of"] for row in CRECEPYMES_HISTORICAL_PILOTS],
            ["2024-12-31", "2022-12-31"],
        )

    def test_balance_equation_and_fail_closed_validator(self):
        for row in CRECEPYMES_HISTORICAL_PILOTS:
            data = row["data"]
            self.assertEqual(
                data["total_assets"],
                data["total_liabilities"] + data["equity"],
                row["fiscal_period"],
            )
            out = validate_snapshot("ICP.B", data, row["source_url"], row["as_of"])
            self.assertTrue(out["valid"], f"{row['fiscal_period']}: {out}")
            self.assertGreaterEqual(out["score"], 70.0, row["fiscal_period"])

    def test_primary_net_income_values_are_preserved(self):
        rows = {
            row["fiscal_period"]: row["data"]["net_income"]
            for row in CRECEPYMES_HISTORICAL_PILOTS
        }
        self.assertEqual(rows["FY2024"], 4452134.0)
        self.assertEqual(rows["FY2022"], 2862084.0)


if __name__ == "__main__":
    unittest.main()
