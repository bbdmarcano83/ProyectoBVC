import asyncio
from unittest import TestCase
from unittest.mock import patch

from scripts import v5_ingest_cgq_safe as target


class CgqSafeIngestTests(TestCase):
    def test_exact_validated_snapshot_is_frozen_before_live_download(self):
        existing = {
            "document_id": 11,
            "snapshot_id": 12,
            "sha256": "a" * 64,
            "validation_score": 100.0,
        }
        with (
            patch.object(target, "_existing_validated_snapshot", return_value=existing),
            patch.object(target, "fetch_and_parse_official_pdf") as download,
        ):
            report = asyncio.run(target.main_async())

        self.assertTrue(report["ok"])
        self.assertTrue(report["accepted"])
        self.assertTrue(report["duplicate"])
        self.assertEqual(report["fiscal_period"], "FY2025")
        self.assertEqual(report["sha256"], "a" * 64)
        download.assert_not_called()
