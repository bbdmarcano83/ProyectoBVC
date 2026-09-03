import unittest
from pathlib import Path

from app.routers.scoring import _active_score, _score_bucket_counts


ROOT = Path(__file__).resolve().parents[1]
SCORING_TEMPLATE = ROOT / "templates" / "scoring.html"


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
        self.assertEqual(_score_bucket_counts(rows, v5_active=True), (1, 1, 1, 1))

    def test_legacy_buckets_remain_available_when_v5_is_disabled(self):
        rows = [
            {"accion_label": "Score alto"},
            {"accion_label": "Score medio"},
            {"accion_label": "Score bajo"},
            {"accion_label": "Score mínimo"},
        ]
        self.assertEqual(_score_bucket_counts(rows, v5_active=False), (1, 1, 1, 1))

    def test_scoring_template_has_client_side_filters_without_recomputing_scores(self):
        html = SCORING_TEMPLATE.read_text(encoding="utf-8")
        for marker in (
            'id="scoring-search"',
            'data-filter="confirmed"',
            'data-filter="prepare"',
            'data-filter="market-no-fund"',
            'data-filter="ibc"',
            'data-filter="discard"',
            'id="scoring-visible-count"',
            'id="scoring-clear"',
        ):
            self.assertIn(marker, html)
        self.assertIn('data-sort-v5="{{ r.get(\'philosophy_score_v5\'', html)
        self.assertIn("function applyFilters()", html)
        self.assertNotIn("fetch('/api/scoring", html)

    def test_primary_score_is_visually_clear_without_internal_version_labels(self):
        html = SCORING_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("Puntuación principal", html)
        self.assertIn('class="score-primary"', html)
        self.assertIn("r.get('score_v3', r.total)", html)
        self.assertIn("r.get('philosophy_score_v5'", html)
        self.assertNotIn("Scoring Engine", html)
        self.assertNotIn("Ranking activo", html)
        self.assertNotIn(">V3<", html)
        self.assertNotIn(">V5<", html)

    def test_user_facing_language_is_plain_spanish(self):
        html = SCORING_TEMPLATE.read_text(encoding="utf-8")
        for marker in (
            "Panorama de acciones",
            "Condición del mercado",
            "Participación del mercado",
            "Información financiera",
            "Situación financiera",
            "Cerca de entrada",
            "Calidad del negocio",
            "Valor y margen de seguridad",
            "Rentabilidad del capital",
            "Confianza del análisis",
        ):
            self.assertIn(marker, html)
        for jargon in (">Confidence<", ">Strength<", ">Opportunity<", ">Tier evidencia<", "Filosofía Caracas Bull V5"):
            self.assertNotIn(jargon, html)

    def test_mobile_uses_cards_instead_of_compressed_desktop_table(self):
        html = SCORING_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('id="mobile-ranking"', html)
        self.assertIn('class="mobile-card"', html)
        self.assertIn("toggleMobileCard", html)
        self.assertIn(".desktop-ranking{display:none}", html)
        self.assertIn(".mobile-ranking{display:flex", html)

    def test_semantic_market_states_and_momentum_colors_are_present(self):
        html = SCORING_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("'SIN FUNDAMENTAL' in stage", html)
        self.assertIn("'DESCARTAR' in stage", html)
        self.assertIn("mompos", html)
        self.assertIn("momneg", html)
        self.assertIn("riskhi", html)
        self.assertIn("riskmed", html)
        self.assertIn("risklo", html)


if __name__ == "__main__":
    unittest.main()
