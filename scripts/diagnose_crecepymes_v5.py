"""Diagnóstico read-only de estados auditados CrecePymes V5.

Descarga únicamente PDFs oficiales ya registrados y muestra candidatos con
página/columna/evidencia. No abre DB, no persiste snapshots y no selecciona
cifras automáticamente.
"""
from __future__ import annotations

import json

from services.fundamental_pdf_parser_v5 import fetch_and_parse_official_pdf

DOCUMENTS = [
    {
        "period": "FY2024/FY2023",
        "url": "https://www.crecepymes.com/documents/SUNAVAL/Informe%20Auditado%20Inversiones%20CrecePymes%202023-2024.pdf",
    },
    {
        "period": "FY2022/FY2021",
        "url": "https://www.crecepymes.com/documents/SUNAVAL/Informe%20de%20Auditoria%20Inversiones%20Crecepymes%2C%20C.A.%202022-2021.pdf",
    },
]

FIELDS = ("total_assets", "total_liabilities", "equity", "net_income", "nav")


def compact(candidate: dict) -> dict:
    return {
        "value": candidate.get("value"),
        "raw": candidate.get("raw"),
        "page": candidate.get("page"),
        "column_index": candidate.get("column_index"),
        "occurrence": candidate.get("occurrence"),
        "alias": candidate.get("alias"),
        "evidence": candidate.get("evidence"),
    }


def main() -> int:
    for doc in DOCUMENTS:
        candidates, meta = fetch_and_parse_official_pdf("ICP.B", doc["url"], timeout=40.0)
        print("=" * 100)
        print(f"DOCUMENT {doc['period']}")
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        if not meta.get("valid"):
            continue
        for field in FIELDS:
            rows = [compact(x) for x in candidates.get(field, [])]
            print(f"--- {field}: {len(rows)} candidates ---")
            print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
