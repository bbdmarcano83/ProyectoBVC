import unittest

from app.routers.scoring import _active_score, _score_bucket_counts


class V5ScoringUiParityTests(unittest.TestCase):
    def test_active_score_prefers_v5_and_preserves_v3_as_fallback(self):
        self.assertEqual(
            _active_score({"philosophy_score_v5": 82, "total": 82, "score_v3": 40}),
            82,
        )
        self.assertEqual(_active_score({"total": 61, "score_v3": 61}), 61)

    def test_v5_dashboard_buckets_use_active_score_not_legacy_label(self):
        rows = [
            {"philosophy_score_v5": 80, "accion_label": "Score mínimo"},
            {"philosophy_score_v5": 70, "accion_label": "Score alto"},
            {"philosophy_score_v5": 45, "accion_label": "Score alto"},
            {"philosophy_score_v5": 20, "accion_label": "Score alto"},
        ]
        self.assertEqual(
            _score_bucket_counts(rows, v5_active=True),
            (1, 1, 1, 1),
        )

    def test_legacy_buckets_remain_available_when_v5_is_disabled(self):
        rows = [
            {"accion_label": "Score alto"},
            {"accion_label": "Score medio"},
            {"accion_label": "Score bajo"},
            {"accion_label": "Score mínimo"},
        ]
        self.assertEqual(
            _score_bucket_counts(rows, v5_active=False),
            (1, 1, 1, 1),
        )


if __name__ == "__main__":
    unittest.main()
