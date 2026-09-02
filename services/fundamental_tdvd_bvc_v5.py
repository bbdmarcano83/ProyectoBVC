"""Parser específico, fail-closed, para el bundle BVC certificado de TDV.D FY2025.

No contiene cifras financieras codificadas. Reprocesa las imágenes oficiales con
varios perfiles OCR, exige consenso entre familias distintas y valida la ecuación
contable antes de producir candidatos para el review V5.
"""
from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unicodedata

import httpx
from PIL import Image, ImageFilter, ImageOps

from services.fundamental_bvc_image_parser_v5 import (
    _is_certified_bvc_url,
    fetch_and_parse_bvc_post,
)

TDVD_CERTIFIED_POST_ID = 32881
# Familias realmente distintas de preprocesamiento. El consenso exige al menos
# dos familias, no dos pasadas del mismo bitmap.
_FAMILIES = (
    "gray2x",
    "gray2x_soft",
    "bw2x_160",
    "bw2x_173",
    "bw2x_190",
    "gray3x",
)
_REQUIRED_FIELDS = ("total_assets", "total_liabilities", "equity", "net_income")


def _norm(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\bu\s+tilidad\b", "utilidad", value, flags=re.I)
    return " ".join(re.sub(r"[^a-zA-Z0-9]+", " ", value.lower()).split())


def _tail_for_field(line: str, field: str) -> str | None:
    raw = str(line or "")
    if field == "total_assets":
        match = re.search(r"total\s+activo(?!\s+(?:no\s+)?corriente)", raw, flags=re.I)
    elif field == "total_liabilities":
        match = re.search(r"total\s+pasivo(?!\s+(?:no\s+)?corriente)", raw, flags=re.I)
    elif field == "equity":
        match = re.search(r"total\s+patrimonio(?!\s+y\s+pasivo)", raw, flags=re.I)
    elif field == "net_income":
        normalized = _norm(raw)
        if "utilidad perdida neta" not in normalized:
            return None
        match = re.search(r"neta", raw, flags=re.I)
    else:
        return None
    if not match:
        return None
    return raw[match.end():]


def _extract_current_integer(tail: str) -> int | None:
    """Extrae sólo el primer importe FY2025 con una forma OCR permitida.

    Los patrones están anclados al inicio y terminan antes de la columna
    comparativa. Un grupo de cuatro dígitos queda rechazado; nunca se busca una
    cifra posterior en la misma fila.
    """
    text = str(tail or "")
    patterns = (
        r"^\s*(\()?\s*(\d{1,3}(?:\s*[.,]\s*\d{3}){3})(\))?(?![.,\d])",
        r"^\s*(\()?\s*(\d{1,3}\s*[.,]\s*\d{3}\s*[.,]\s*\d{6})(\))?(?![.,\d])",
        r"^\s*(\()?\s*(\d{1,3}\s+[.,]?\s*\d{3}\s*[.,]\s*\d{3})(\))?(?![.,\d])",
        r"^\s*(\()?\s*(\d{1,3}(?:\s*[.,]\s*\d{3}){2})(\))?(?![.,\d])",
        r"^\s*(\()?\s*(\d{9,12})(\))?(?![.,\d])",
    )
    for pattern in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        digits = re.sub(r"\D", "", match.group(2))
        if not (9 <= len(digits) <= 12):
            continue
        value = int(digits)
        return -value if bool(match.group(1) and match.group(3)) else value
    return None


def _line_field(line: str) -> tuple[str | None, int | None]:
    for field in _REQUIRED_FIELDS:
        tail = _tail_for_field(line, field)
        if tail is None:
            continue
        return field, _extract_current_integer(tail)
    return None, None


def _profile_image(data: bytes, family: str, path: Path) -> None:
    with Image.open(BytesIO(data)) as image:
        image = image.convert("L")
        if family == "gray2x":
            image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
            image = ImageOps.autocontrast(image, cutoff=8)
            image = image.filter(ImageFilter.SHARPEN)
        elif family == "gray2x_soft":
            image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
            image = ImageOps.autocontrast(image, cutoff=3)
        elif family.startswith("bw2x_"):
            threshold = int(family.rsplit("_", 1)[1])
            image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
            image = ImageOps.autocontrast(image, cutoff=5)
            image = image.point(lambda p: 255 if p >= threshold else 0)
        elif family == "gray3x":
            image = image.resize((image.width * 3, image.height * 3), Image.Resampling.LANCZOS)
            image = ImageOps.autocontrast(image, cutoff=10)
            image = image.filter(ImageFilter.SHARPEN)
        else:
            raise ValueError("unknown_ocr_family")
        image.save(path, format="PNG")


def _ocr_psm4(path: Path) -> str:
    executable = shutil.which("tesseract")
    if not executable:
        return ""
    proc = subprocess.run(
        [executable, str(path), "stdout", "-l", "eng", "--psm", "4"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.stdout if proc.returncode == 0 else ""


def _consensus(observations: list[dict]) -> dict:
    by_value: dict[int, list[dict]] = defaultdict(list)
    for row in observations:
        value = row.get("value")
        if isinstance(value, int):
            by_value[value].append(row)
    ranked = sorted(
        by_value.items(),
        key=lambda item: (-len({r.get("family") for r in item[1]}), -len(item[1]), abs(item[0])),
    )
    if not ranked:
        return {"valid": False, "reason": "no_numeric_observations"}
    best_value, best_rows = ranked[0]
    best_families = {r.get("family") for r in best_rows}
    if len(best_families) < 2:
        return {"valid": False, "reason": "insufficient_independent_ocr_families", "observations": observations}
    if len(ranked) > 1:
        second_families = {r.get("family") for r in ranked[1][1]}
        if len(second_families) == len(best_families):
            return {"valid": False, "reason": "ocr_consensus_tie", "observations": observations}
    return {
        "valid": True,
        "value": best_value,
        "families": sorted(best_families),
        "votes": len(best_rows),
        "page": best_rows[0].get("page"),
        "evidence": [r.get("line") for r in best_rows],
        "observations": observations,
    }


def fetch_and_parse_tdvd_certified_bvc_post(post_id: int = TDVD_CERTIFIED_POST_ID, timeout: float = 30.0) -> tuple[dict, dict]:
    try:
        post_id = int(post_id)
    except (TypeError, ValueError):
        return {}, {"valid": False, "reason": "invalid_tdvd_post_id"}
    if post_id != TDVD_CERTIFIED_POST_ID:
        return {}, {"valid": False, "reason": "unexpected_tdvd_certified_post"}

    _, base_meta = fetch_and_parse_bvc_post("TDV.D", post_id, timeout=timeout)
    if not base_meta.get("valid"):
        return {}, {**base_meta, "reason": base_meta.get("reason") or "base_bvc_parse_invalid"}
    media_urls = list(base_meta.get("media_urls") or [])
    if len(media_urls) != 3:
        return {}, {**base_meta, "valid": False, "reason": "tdvd_expected_three_bvc_pages"}

    observations: dict[str, list[dict]] = defaultdict(list)
    headers = {"User-Agent": "CaracasBull-TDVD-Certified-OCR/1.0"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client, tempfile.TemporaryDirectory(prefix="tdvd-certified-") as tmp:
            tmpdir = Path(tmp)
            for page_no, url in enumerate(media_urls, start=1):
                if not _is_certified_bvc_url("TDV.D", url):
                    return {}, {**base_meta, "valid": False, "reason": "tdvd_media_not_bvc_certified"}
                response = client.get(url)
                response.raise_for_status()
                if not _is_certified_bvc_url("TDV.D", str(response.url)):
                    return {}, {**base_meta, "valid": False, "reason": "tdvd_media_redirect_not_bvc_certified"}
                data = response.content
                if not data:
                    return {}, {**base_meta, "valid": False, "reason": "tdvd_empty_media"}
                for family in _FAMILIES:
                    out = tmpdir / f"p{page_no}-{family}.png"
                    _profile_image(data, family, out)
                    text = _ocr_psm4(out)
                    for line in text.splitlines():
                        field, value = _line_field(line)
                        if field and value is not None:
                            observations[field].append({
                                "family": family,
                                "page": page_no,
                                "value": value,
                                "line": line.strip(),
                            })
    except Exception as exc:
        return {}, {**base_meta, "valid": False, "reason": f"tdvd_consensus_ocr_error:{type(exc).__name__}"}

    consensus = {field: _consensus(observations.get(field, [])) for field in _REQUIRED_FIELDS}
    invalid = [field for field, result in consensus.items() if not result.get("valid")]
    if invalid:
        return {}, {
            **base_meta,
            "valid": False,
            "reason": "tdvd_ocr_consensus_incomplete",
            "missing_consensus": invalid,
            "ocr_consensus": consensus,
        }

    assets = int(consensus["total_assets"]["value"])
    liabilities = int(consensus["total_liabilities"]["value"])
    equity = int(consensus["equity"]["value"])
    if assets != liabilities + equity:
        return {}, {
            **base_meta,
            "valid": False,
            "reason": "tdvd_accounting_equation_mismatch",
            "ocr_consensus": consensus,
            "equation": {"assets": assets, "liabilities": liabilities, "equity": equity},
        }

    aliases = {
        "total_assets": "total activo",
        "total_liabilities": "total pasivo",
        "equity": "total patrimonio",
        "net_income": "utilidad (pérdida) neta",
    }
    candidates = {}
    for field in _REQUIRED_FIELDS:
        row = consensus[field]
        candidates[field] = [{
            "value": float(row["value"]),
            "raw": row["evidence"][0],
            "page": row["page"],
            "alias": aliases[field],
            "evidence": " | ".join(row["evidence"]),
            "column_index": 0,
            "occurrence": 0,
            "context_quality": "accounting_row",
            "page_years": [],
            "derived_from": [],
        }]

    return candidates, {
        **base_meta,
        "valid": True,
        "reason": None,
        "ocr_profile": "tdvd_psm4_multi_family_consensus_v2",
        "ocr_consensus": consensus,
        "accounting_equation_error": 0,
    }
