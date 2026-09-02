import unittest

from scripts.diagnose_missing_fundamentals_v5 import _stage


class MissingFundamentalsDiagnosticV5Tests(unittest.TestCase):
    def test_classifies_parse_failure(self):
        stage, reason = _stage({"parse": {"valid": False, "error": "bad_pdf"}, "result": {}})
        self.assertEqual(stage, "parse")
        self.assertEqual(reason, "bad_pdf")

    def test_classifies_autoreview_missing_fields(self):
        stage, reason = _stage({
            "parse": {"valid": True},
            "auto_review": {"valid": False, "reason": "missing_required_fields", "missing_required": ["equity", "net_income"]},
            "result": {"accepted": False, "error": "missing_required_fields"},
        })
        self.assertEqual(stage, "auto_review")
        self.assertIn("equity", reason)
        self.assertIn("net_income", reason)

    def test_classifies_accepted_duplicate(self):
        stage, reason = _stage({
            "parse": {"valid": True},
            "auto_review": {"valid": True},
            "result": {"accepted": True, "persisted": False, "duplicate": True},
        })
        self.assertEqual(stage, "accepted_duplicate")
        self.assertIsNone(reason)

    def test_classifies_fx_failure(self):
        stage, reason = _stage({
            "parse": {"valid": True},
            "auto_review": {"valid": True},
            "result": {"accepted": False, "fx": {"valid": False, "flags": ["historical_fx_missing"]}},
        })
        self.assertEqual(stage, "fx")
        self.assertIn("historical_fx_missing", reason)


if __name__ == "__main__":
    unittest.main()
