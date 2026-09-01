"""Auditoría read-only de documentos fundamentales V5 persistidos.

Reporta cobertura de fingerprint SHA-256 del PDF, published_at, versiones por
período e identidades económicas repetidas. No modifica Neon. `published_at`
desconocido es una brecha informativa, no un error: el loader de backtest ya
falla cerrado ante esa brecha.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any

from database import DB_PERSISTENCE_MODE, FundamentalDocument, FundamentalSnapshot, SessionLocal
from services.fundamental_backfill_manifest_v5 import PILOT_BACKFILL_V5
from services.fundamental_identity_v5 import economic_signature


def _metadata(raw: Any) -> tuple[dict, bool]:
    if isinstance(raw, dict):
        return dict(raw), True
    try:
        parsed = json.loads(str(raw or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}, False
    return (parsed, True) if isinstance(parsed, dict) else ({}, False)


def _payload(raw: Any) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sha256(value: Any) -> str | None:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        return None
    return digest


def audit_documents() -> dict:
    expected: dict[str, set[str]] = {
        symbol: {str(doc.get("fiscal_period") or "") for doc in issuer.get("documents", []) if doc.get("fiscal_period")}
        for symbol, issuer in PILOT_BACKFILL_V5.items()
    }
    pilot_symbols = set(expected)

    with SessionLocal() as db:
        rows = db.query(FundamentalDocument).filter(FundamentalDocument.simbolo.in_(sorted(pilot_symbols))).order_by(
            FundamentalDocument.simbolo.asc(),
            FundamentalDocument.fiscal_period.asc(),
            FundamentalDocument.id.asc(),
        ).all()
        doc_ids = [int(row.id) for row in rows]
        snaps = db.query(FundamentalSnapshot).filter(
            FundamentalSnapshot.document_id.in_(doc_ids)
        ).all() if doc_ids else []
        snap_by_doc = {int(s.document_id): s for s in snaps}

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    economic_groups: dict[tuple[str, str, str, str], list[int]] = defaultdict(list)
    invalid_metadata = 0
    malformed_sha = 0
    docs_with_sha = 0
    docs_with_published_at = 0

    for row in rows:
        meta, metadata_valid = _metadata(row.metadata_json)
        if not metadata_valid:
            invalid_metadata += 1
        raw_sha = meta.get("source_document_sha256")
        sha = _sha256(raw_sha)
        if raw_sha not in (None, "") and sha is None:
            malformed_sha += 1
        if sha:
            docs_with_sha += 1
        if str(row.published_at or "").strip():
            docs_with_published_at += 1

        snap = snap_by_doc.get(int(row.id))
        sig = economic_signature(row.source_url, row.as_of, _payload(snap.data_json) if snap else {})
        economic_groups[(str(row.simbolo).upper(), str(row.source_url), str(row.as_of), sig)].append(int(row.id))

        grouped[(str(row.simbolo).upper(), str(row.fiscal_period or ""))].append({
            "id": int(row.id),
            "as_of": row.as_of,
            "source_url": row.source_url,
            "document_hash": row.document_hash,
            "economic_signature_v5": sig,
            "source_document_sha256": sha,
            "published_at": row.published_at,
            "audited": bool(row.audited),
            "metadata_valid": metadata_valid,
        })

    repeated_economic_groups = {
        key: ids for key, ids in economic_groups.items() if len(ids) > 1
    }
    economic_duplicate_versions = sum(len(ids) - 1 for ids in repeated_economic_groups.values())

    periods: list[dict] = []
    expected_periods = present_periods = periods_with_sha = periods_with_published_at = 0
    duplicate_period_versions = 0
    periods_with_economic_duplicates = 0
    for symbol in sorted(expected):
        for fiscal_period in sorted(expected[symbol]):
            expected_periods += 1
            versions = grouped.get((symbol, fiscal_period), [])
            has_sha = any(item.get("source_document_sha256") for item in versions)
            has_published_at = any(item.get("published_at") for item in versions)
            if versions:
                present_periods += 1
            if has_sha:
                periods_with_sha += 1
            if has_published_at:
                periods_with_published_at += 1
            if len(versions) > 1:
                duplicate_period_versions += 1

            sig_counts: dict[str, int] = defaultdict(int)
            for item in versions:
                sig_counts[str(item.get("economic_signature_v5") or "")] += 1
            economic_duplicate = any(count > 1 for sig, count in sig_counts.items() if sig)
            if economic_duplicate:
                periods_with_economic_duplicates += 1

            periods.append({
                "symbol": symbol,
                "fiscal_period": fiscal_period,
                "present": bool(versions),
                "version_count": len(versions),
                "economic_identity_count": len({item.get("economic_signature_v5") for item in versions if item.get("economic_signature_v5")}),
                "has_economic_duplicate_versions": economic_duplicate,
                "has_source_document_sha256": has_sha,
                "has_published_at": has_published_at,
                "versions": versions,
            })

    by_symbol = {}
    for symbol in sorted(expected):
        subset = [item for item in periods if item["symbol"] == symbol]
        by_symbol[symbol] = {
            "expected_periods": len(subset),
            "present_periods": sum(1 for item in subset if item["present"]),
            "sha_periods": sum(1 for item in subset if item["has_source_document_sha256"]),
            "published_at_periods": sum(1 for item in subset if item["has_published_at"]),
            "periods_with_economic_duplicates": sum(1 for item in subset if item["has_economic_duplicate_versions"]),
        }

    duplicate_group_details = [
        {
            "symbol": key[0],
            "source_url": key[1],
            "as_of": key[2],
            "economic_signature_v5": key[3],
            "document_ids": ids,
            "redundant_versions": len(ids) - 1,
        }
        for key, ids in sorted(repeated_economic_groups.items())
    ]

    return {
        "database_mode": DB_PERSISTENCE_MODE,
        "read_only": True,
        "documents_total_for_pilots": len(rows),
        "expected_manifest_periods": expected_periods,
        "present_manifest_periods": present_periods,
        "periods_with_source_document_sha256": periods_with_sha,
        "periods_with_published_at": periods_with_published_at,
        "documents_with_source_document_sha256": docs_with_sha,
        "documents_with_published_at": docs_with_published_at,
        "invalid_metadata_json": invalid_metadata,
        "malformed_source_document_sha256": malformed_sha,
        "periods_with_multiple_versions": duplicate_period_versions,
        "periods_with_economic_duplicate_versions": periods_with_economic_duplicates,
        "economic_identity_groups": len(economic_groups),
        "economic_duplicate_versions": economic_duplicate_versions,
        "economic_duplicate_groups": duplicate_group_details,
        "published_at_policy": "missing is allowed live but excluded by no-lookahead backtests",
        "by_symbol": by_symbol,
        "periods": periods,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit persisted V5 fundamental documents")
    parser.add_argument("--strict", action="store_true", help="Fail on objective audit-integrity defects")
    parser.add_argument(
        "--require-any-sha",
        action="store_true",
        help="Fail if no persisted pilot period has a source PDF SHA-256",
    )
    args = parser.parse_args()

    report = audit_documents()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    failures: list[str] = []
    if args.strict:
        if report["invalid_metadata_json"]:
            failures.append("invalid_metadata_json")
        if report["malformed_source_document_sha256"]:
            failures.append("malformed_source_document_sha256")
    if args.require_any_sha and report["periods_with_source_document_sha256"] < 1:
        failures.append("no_persisted_source_document_sha256")

    if failures:
        print(json.dumps({"audit_failures": failures}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
