import unittest
from pathlib import Path


class PortfolioBenchmarkUiV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = Path("templates/portafolio.html").read_text(encoding="utf-8")

    def test_ui_marks_terminal_date_mismatch_as_provisional(self):
        self.assertIn("terminal_dates_aligned", self.template)
        self.assertIn("PROVISIONAL · cartera", self.template)
        self.assertIn("Alpha provisional", self.template)
        self.assertIn("ibc_as_of", self.template)
        self.assertIn("valuation_as_of", self.template)

    def test_ui_has_comparable_close_state(self):
        self.assertIn("Cierre comparable", self.template)

    def test_disabled_endpoint_message_is_explicit(self):
        self.assertIn("Benchmark V5 deshabilitado", self.template)


if __name__ == "__main__":
    unittest.main()
