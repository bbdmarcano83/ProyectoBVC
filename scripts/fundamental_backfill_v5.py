"""CLI de backfill fundamental V5 con revisión explícita.

Ejemplos:
  python scripts/fundamental_backfill_v5.py --symbol MVZ.A --period FY2025 --review-out /tmp/mvz_review.json
  python scripts/fundamental_backfill_v5.py --symbol MVZ.A --period FY2025 --accept /tmp/mvz_selections.json

El primer modo nunca persiste. El segundo sólo persiste si las selecciones pasan
coverage, ecuación contable, FX histórico y fuente registrada.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.fundamental_backfill_manifest_v5 import PILOT_BACKFILL_V5
from services.fundamental_pdf_parser_v5 import fetch_and_parse_official_pdf
from services.fundamental_review_v5 import build_review_package, accept_reviewed_snapshot


def _document(symbol: str, period: str) -> dict:
    issuer = PILOT_BACKFILL_V5.get(symbol)
    if not issuer:
        raise SystemExit(f"Símbolo no incluido en piloto: {symbol}")
    doc = next((d for d in issuer.get("documents", []) if d.get("fiscal_period") == period), None)
    if not doc:
        raise SystemExit(f"Período no registrado: {symbol} {period}")
    if not doc.get("url"):
        raise SystemExit(f"Documento pendiente de discovery: {symbol} {period}")
    return {**doc, "industry_type": issuer.get("industry_type"), "issuer": issuer.get("issuer")}


def build_review(symbol: str, period: str) -> dict:
    doc = _document(symbol, period)
    candidates, parse_meta = fetch_and_parse_official_pdf(symbol, doc["url"])
    review = build_review_package(symbol, candidates, source_url=doc["url"], as_of=doc["as_of"])
    return {"document": doc, "parse": parse_meta, "review": review}


def accept(symbol: str, period: str, selections_path: str) -> dict:
    package = build_review(symbol, period)
    review = package["review"]
    if not review.get("valid"):
        return {"accepted": False, "error": "review_package_invalid", "package": package}
    payload = json.loads(Path(selections_path).read_text(encoding="utf-8"))
    selections = payload.get("selections") if isinstance(payload, dict) else None
    extra_fields = payload.get("extra_fields", {}) if isinstance(payload, dict) else {}
    if not isinstance(selections, dict):
        return {"accepted": False, "error": "selections_required"}
    doc = package["document"]
    result = accept_reviewed_snapshot(
        review,
        selections,
        document_type=doc["document_type"],
        fiscal_period=doc["fiscal_period"],
        audited=bool(doc.get("audited")),
        currency=str(payload.get("currency") or "VES"),
        monetary_basis=str(payload.get("monetary_basis") or "nominal_ves"),
        period_start=payload.get("period_start"),
        published_at=payload.get("published_at"),
        extra_fields=extra_fields,
        hydrate_fx=True,
        require_fx=True,
    )
    return {"document": doc, "parse": package["parse"], "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Caracas Bull V5 fundamental backfill")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--period", required=True)
    parser.add_argument("--review-out")
    parser.add_argument("--accept", help="JSON con selections explícitas")
    args = parser.parse_args()

    symbol = args.symbol.upper().strip()
    if args.accept:
        output = accept(symbol, args.period, args.accept)
    else:
        output = build_review(symbol, args.period)

    text = json.dumps(output, ensure_ascii=False, indent=2, default=str)
    if args.review_out:
        Path(args.review_out).write_text(text, encoding="utf-8")
        print(args.review_out)
    else:
        print(text)
    return 0 if (output.get("review", {}).get("valid") or output.get("result", {}).get("accepted")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
