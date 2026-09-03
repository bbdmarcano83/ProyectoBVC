import os
import unittest
from unittest.mock import patch

from services.portafolio import _v5_enabled


class V5PortfolioActivationParityTests(unittest.TestCase):
    def test_portfolio_v5_overlay_is_active_by_default(self):
        env = {key: value for key, value in os.environ.items() if key != "SCORING_ENGINE_V5_ENABLED"}
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(_v5_enabled())

    def test_explicit_false_rolls_back_portfolio_v5_overlay(self):
        with patch.dict(os.environ, {"SCORING_ENGINE_V5_ENABLED": "false"}, clear=False):
            self.assertFalse(_v5_enabled())

    def test_explicit_true_keeps_portfolio_v5_overlay_enabled(self):
        with patch.dict(os.environ, {"SCORING_ENGINE_V5_ENABLED": "true"}, clear=False):
            self.assertTrue(_v5_enabled())


if __name__ == "__main__":
    unittest.main()
