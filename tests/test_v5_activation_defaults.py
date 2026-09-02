import os
import unittest
from unittest.mock import patch

from services.feature_flags import (
    portfolio_ibc_benchmark_v5_enabled,
    portfolio_v4_enabled,
    scoring_v3_enabled,
    scoring_v5_enabled,
)
from services.scoring import _v5_enabled


class V5ActivationDefaultsTests(unittest.TestCase):
    FLAGS = (
        "SCORING_ENGINE_V3_ENABLED",
        "SCORING_ENGINE_V5_ENABLED",
        "PORTFOLIO_ENGINE_V4_ENABLED",
        "PORTFOLIO_IBC_BENCHMARK_V5_ENABLED",
    )

    def test_validated_analysis_engines_are_active_by_default(self):
        env = {key: value for key, value in os.environ.items() if key not in self.FLAGS}
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(scoring_v3_enabled())
            self.assertTrue(scoring_v5_enabled())
            self.assertTrue(_v5_enabled())
            self.assertTrue(portfolio_v4_enabled())
            self.assertTrue(portfolio_ibc_benchmark_v5_enabled())

    def test_explicit_false_is_immediate_rollback(self):
        with patch.dict(os.environ, {
            "SCORING_ENGINE_V5_ENABLED": "false",
            "PORTFOLIO_IBC_BENCHMARK_V5_ENABLED": "false",
        }, clear=False):
            self.assertFalse(scoring_v5_enabled())
            self.assertFalse(_v5_enabled())
            self.assertFalse(portfolio_ibc_benchmark_v5_enabled())


if __name__ == "__main__":
    unittest.main()
