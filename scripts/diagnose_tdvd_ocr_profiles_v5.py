"""Prueba read-only de perfiles OCR para TDV.D sobre originales certificados BVC."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import httpx

from services.fundamental_bvc_image_parser_v5 import BVC_API_ROOT, extract_media_ids
from services.fundamental_pdf_parser_v5 import extract_candidates_from_pages

POST_ID = 32881
KEYWORDS = ("total activo", "total pasivo", "total patrimonio", "utilidad", "pérdida", "perdida")


def _ocr(path: Path, psm: int) -> str:
    proc = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "eng", "--psm", str(psm)],
        check=False, capture_output=True, text=True, timeout=60,
    )
    return proc.stdout if proc.returncode == 0 else ""


def _score(text: str) -> tuple[int, int]:
    low = text.lower()
    keywords = sum(1 for key in KEYWORDS if key in low)
    numeric = len(re.findall(r"\d{1,3}(?:[.,]\d{3}){2,}|\d{7,}", text))
    return keywords, numeric


def _accounting_lines(text: str) -> list[str]:
    return [
        line.strip() for line in text.splitlines()
        if any(key in line.lower() for key in KEYWORDS)
    ]


def _digits_after_label(line: str, label: str) -> str | None:
    low = line.lower()
    pos = low.find(label)
    if pos < 0:
        return None
    tail = line[pos + len(label):]
    groups = re.findall(r"\d+", tail)
    if not groups:
        return None
    # Primer valor de la columna vigente: conservamos sólo dígitos observados.
    # No corregimos, truncamos ni agregamos cifras en este diagnóstico.
    return "".join(groups[:4])


def main() -> int:
    headers = {"User-Agent": "CaracasBull-TDVD-OCR-Audit/1.0"}
    with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
        post = client.get(f"{BVC_API_ROOT}/posts/{POST_ID}").json()
        ids = extract_media_ids((post.get("content") or {}).get("rendered") or "")
        pages = []
        profile_rows = []
        net_income_observations = []
        with tempfile.TemporaryDirectory(prefix="tdvd-ocr-") as tmp:
            tmpdir = Path(tmp)
            for page_no, media_id in enumerate(ids, start=1):
                media = client.get(f"{BVC_API_ROOT}/media/{media_id}").json()
                url = str(media.get("source_url") or "")
                raw = client.get(url).content
                source = tmpdir / f"p{page_no}.jpg"
                source.write_bytes(raw)
                variants = []
                for name, args in (
                    ("gray2x", ["-colorspace", "Gray", "-resize", "200%", "-contrast-stretch", "0x8%", "-sharpen", "0x1"]),
                    ("bw2x", ["-colorspace", "Gray", "-resize", "200%", "-threshold", "68%"]),
                    ("gray3x", ["-colorspace", "Gray", "-resize", "300%", "-contrast-stretch", "0x10%", "-sharpen", "0x1"]),
                ):
                    out = tmpdir / f"p{page_no}-{name}.png"
                    proc = subprocess.run(["convert", str(source), *args, str(out)], check=False, capture_output=True, timeout=60)
                    if proc.returncode != 0:
                        continue
                    for psm in (4, 6, 11):
                        text = _ocr(out, psm)
                        profile = f"{name}-psm{psm}"
                        lines = _accounting_lines(text)
                        variants.append({"profile": profile, "text": text, "score": _score(text), "lines": lines})
                        for line in lines:
                            if "utilidad (pérdida) neta" in line.lower() or "utilidad (perdida) neta" in line.lower():
                                digits = _digits_after_label(line, "neta")
                                if digits:
                                    net_income_observations.append({
                                        "profile": profile,
                                        "page": page_no,
                                        "digits": digits,
                                        "line": line,
                                    })
                variants.sort(key=lambda row: row["score"], reverse=True)
                best = variants[0] if variants else {"profile": None, "text": "", "score": (0, 0), "lines": []}
                pages.append(best["text"])
                profile_rows.append({
                    "page": page_no,
                    "media_id": media_id,
                    "best_profile": best["profile"],
                    "score": best["score"],
                    "accounting_lines": best["lines"],
                    "all_profile_lines": [
                        {"profile": row["profile"], "score": row["score"], "accounting_lines": row["lines"]}
                        for row in variants
                    ],
                })
    candidates = extract_candidates_from_pages(pages)
    counts = Counter(row["digits"] for row in net_income_observations)
    consensus_digits = None
    consensus_votes = 0
    if counts:
        consensus_digits, consensus_votes = counts.most_common(1)[0]
    out = {
        "post_id": POST_ID,
        "profiles": profile_rows,
        "net_income_consensus": {
            "observations": net_income_observations,
            "counts": dict(counts),
            "consensus_digits": consensus_digits,
            "consensus_votes": consensus_votes,
            "valid": bool(consensus_digits and consensus_votes >= 2),
        },
        "candidates": {
            field: [
                {"value": row.get("value"), "page": row.get("page"), "column_index": row.get("column_index"), "alias": row.get("alias"), "evidence": row.get("evidence")}
                for row in rows
            ]
            for field, rows in candidates.items()
            if field in {"total_assets", "total_liabilities", "equity", "net_income"}
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
