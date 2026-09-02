"""BVC WordPress/SharePoint attachment adapter for Caracas Bull V5.

This module does not invent accounting figures. It converts BVC publication
metadata plus its linked artifacts into a deterministic evidence bundle that
can be handed to the existing fundamental parser/collector.

Security/integrity rules:
- the notice must originate from an official BVC HTTPS host;
- external attachments (for example SharePoint) are accepted only when they
  are explicitly linked by that verified BVC notice;
- every downloaded artifact is SHA-256 fingerprinted;
- image-only documents require reproducible OCR evidence before they may pass;
- the bundle is fail-closed when publication time, evidence or OCR is missing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import httpx


BVC_HOSTS = {"bolsadecaracas.com", "www.bolsadecaracas.com", "market.bolsadecaracas.com"}
_ALLOWED_EXTERNAL_SUFFIXES = ("sharepoint.com", "1drv.ms", "onedrive.live.com")
_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/tiff"}
_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
MAX_ARTIFACT_BYTES = 30 * 1024 * 1024
WP_BASE = "https://www.bolsadecaracas.com/wp-json/wp/v2"


def _hostname(url: str) -> str:
    return (urlparse(str(url or "")).hostname or "").lower().strip(".")


def is_official_bvc_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = _hostname(url)
    return parsed.scheme == "https" and (host in BVC_HOSTS or host.endswith(".bolsadecaracas.com"))


def _is_allowed_external_attachment(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = _hostname(url)
    if parsed.scheme != "https" or not host:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_EXTERNAL_SUFFIXES)


def _iso_datetime(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _EvidenceHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag.lower() == "a" and data.get("href"):
            self.links.append(str(data["href"]))
        if tag.lower() in {"img", "source"}:
            for key in ("src", "data-src", "srcset"):
                value = data.get(key)
                if value:
                    self.images.append(str(value).split(",", 1)[0].split()[0])
                    break


def extract_notice_artifact_urls(html: str, notice_url: str) -> list[str]:
    """Return stable, de-duplicated URLs explicitly present in the BVC notice."""
    if not is_official_bvc_url(notice_url):
        return []
    parser = _EvidenceHTMLParser()
    parser.feed(str(html or ""))
    out: list[str] = []
    seen: set[str] = set()
    for raw in [*parser.links, *parser.images]:
        url = urljoin(notice_url, raw)
        if url in seen or not url.startswith("https://"):
            continue
        if not (is_official_bvc_url(url) or _is_allowed_external_attachment(url)):
            continue
        seen.add(url)
        out.append(url)
    return out


def parse_bvc_wp_notice(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize one WordPress REST post/page payload without guessing fields."""
    payload = dict(payload or {})
    link = str(payload.get("link") or "").strip()
    if not is_official_bvc_url(link):
        return {"valid": False, "error": "untrusted_notice_url"}

    date_gmt = _iso_datetime(payload.get("date_gmt"))
    modified_gmt = _iso_datetime(payload.get("modified_gmt"))
    published_at = date_gmt or _iso_datetime(payload.get("date"))
    content = payload.get("content") or {}
    html = content.get("rendered") if isinstance(content, dict) else str(content or "")
    title_raw = payload.get("title") or {}
    title = title_raw.get("rendered") if isinstance(title_raw, dict) else str(title_raw or "")
    urls = extract_notice_artifact_urls(str(html or ""), link)
    return {
        "valid": bool(published_at),
        "error": None if published_at else "missing_published_at",
        "notice_id": payload.get("id"),
        "notice_url": link,
        "published_at": published_at,
        "modified_at": modified_gmt,
        "title": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(title or ""))).strip(),
        "artifact_urls": urls,
        "artifact_count": len(urls),
    }


def _wp_detail_path(subtype: str, item_id: int) -> str | None:
    subtype = str(subtype or "").strip().lower()
    collection = {"post": "posts", "page": "pages"}.get(subtype)
    if not collection or int(item_id) <= 0:
        return None
    return f"{WP_BASE}/{collection}/{int(item_id)}"


async def discover_bvc_wp_notices(query: str, *, timeout: float = 15.0, per_page: int = 20) -> dict[str, Any]:
    """Search the official BVC WordPress REST API and normalize matching notices.

    The search endpoint is used only to discover post/page IDs. Each detail is
    then fetched from the same official REST origin and validated again through
    `parse_bvc_wp_notice` before being returned.
    """
    term = str(query or "").strip()
    if not term:
        return {"ok": False, "error": "empty_query", "query": term, "notices": []}
    headers = {
        "User-Agent": "CaracasBull-FundamentalAudit/1.0 (+bvc-wordpress-evidence)",
        "Accept": "application/json",
    }
    notices: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=headers) as client:
            response = await client.get(
                f"{WP_BASE}/search",
                params={"search": term, "per_page": max(1, min(100, int(per_page))), "type": "post"},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                return {"ok": False, "error": "unexpected_search_payload", "query": term, "notices": []}
            for item in payload:
                if not isinstance(item, dict):
                    continue
                try:
                    item_id = int(item.get("id") or 0)
                except (TypeError, ValueError):
                    continue
                subtype = str(item.get("subtype") or "post")
                detail_url = _wp_detail_path(subtype, item_id)
                if not detail_url:
                    continue
                try:
                    detail = await client.get(detail_url)
                    detail.raise_for_status()
                    normalized = parse_bvc_wp_notice(detail.json())
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}:{item_id}")
                    continue
                if normalized.get("valid"):
                    normalized["search_title"] = item.get("title")
                    normalized["search_subtype"] = subtype
                    notices.append(normalized)
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "query": term, "notices": [], "errors": errors[:10]}

    notices.sort(key=lambda n: str(n.get("published_at") or ""), reverse=True)
    return {
        "ok": True,
        "error": None,
        "query": term,
        "count": len(notices),
        "notices": notices,
        "errors": errors[:10],
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(bytes(data or b"")).hexdigest()


def _normalize_ocr_text(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def build_ocr_evidence(page_texts: Iterable[str], *, engine: str, engine_version: str) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for index, raw in enumerate(page_texts, start=1):
        normalized = _normalize_ocr_text(raw)
        pages.append({
            "page": index,
            "text": normalized,
            "text_sha256": sha256_bytes(normalized.encode("utf-8")),
            "chars": len(normalized),
        })
    canonical = json.dumps(pages, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "engine": str(engine or "").strip(),
        "engine_version": str(engine_version or "").strip(),
        "page_count": len(pages),
        "pages": pages,
        "ocr_sha256": sha256_bytes(canonical),
        "valid": bool(pages and str(engine or "").strip() and str(engine_version or "").strip()),
    }


def _sniff_kind(content_type: str, data: bytes, url: str) -> str:
    ctype = str(content_type or "").split(";", 1)[0].strip().lower()
    head = bytes(data or b"")[:16]
    path = urlparse(url).path.lower()
    if ctype in _PDF_CONTENT_TYPES or head.startswith(b"%PDF-") or path.endswith(".pdf"):
        return "pdf"
    if ctype in _IMAGE_CONTENT_TYPES or head.startswith((b"\x89PNG", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*")):
        return "image"
    return "unknown"


@dataclass(frozen=True)
class DownloadedArtifact:
    url: str
    final_url: str
    content_type: str
    data: bytes


async def download_notice_artifacts(notice: dict[str, Any], *, timeout: float = 20.0) -> dict[str, Any]:
    """Download only artifacts explicitly authorized by a normalized BVC notice."""
    if not notice.get("valid") or not is_official_bvc_url(str(notice.get("notice_url") or "")):
        return {"ok": False, "error": "invalid_notice", "artifacts": []}
    urls = [str(u) for u in (notice.get("artifact_urls") or [])]
    if not urls:
        return {"ok": False, "error": "notice_has_no_artifacts", "artifacts": []}
    headers = {
        "User-Agent": "CaracasBull-FundamentalAudit/1.0 (+bvc-attachment-download)",
        "Accept": "application/pdf,image/*,application/octet-stream;q=0.9,*/*;q=0.4",
    }
    out: list[DownloadedArtifact] = []
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for url in urls:
            if not (is_official_bvc_url(url) or _is_allowed_external_attachment(url)):
                errors.append(f"untrusted_original:{url}")
                continue
            try:
                response = await client.get(url)
                response.raise_for_status()
                data = response.content
            except Exception as exc:
                errors.append(f"{type(exc).__name__}:{url}")
                continue
            final_url = str(response.url)
            if not (is_official_bvc_url(final_url) or _is_allowed_external_attachment(final_url)):
                errors.append(f"untrusted_redirect:{final_url}")
                continue
            if not data or len(data) > MAX_ARTIFACT_BYTES:
                errors.append(f"artifact_empty_or_too_large:{url}")
                continue
            out.append(DownloadedArtifact(
                url=url,
                final_url=final_url,
                content_type=str(response.headers.get("content-type") or ""),
                data=data,
            ))
    return {
        "ok": bool(out),
        "error": None if out else (errors[0].split(":", 1)[0] if errors else "download_failed"),
        "artifacts": out,
        "errors": errors[:10],
    }


def build_evidence_bundle(
    notice: dict[str, Any],
    artifacts: Iterable[DownloadedArtifact],
    *,
    ocr: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not notice.get("valid") or not is_official_bvc_url(str(notice.get("notice_url") or "")):
        return {"valid": False, "error": "invalid_notice", "artifacts": []}
    if not notice.get("published_at"):
        return {"valid": False, "error": "missing_published_at", "artifacts": []}

    allowed = set(str(u) for u in notice.get("artifact_urls") or [])
    rows: list[dict[str, Any]] = []
    image_count = 0
    for position, artifact in enumerate(artifacts, start=1):
        if artifact.url not in allowed:
            return {"valid": False, "error": "artifact_not_linked_by_notice", "artifacts": rows}
        final_host_ok = is_official_bvc_url(artifact.final_url) or _is_allowed_external_attachment(artifact.final_url)
        if not final_host_ok:
            return {"valid": False, "error": "untrusted_redirect_target", "artifacts": rows}
        if not artifact.data:
            return {"valid": False, "error": "empty_artifact", "artifacts": rows}
        kind = _sniff_kind(artifact.content_type, artifact.data, artifact.final_url)
        if kind == "unknown":
            return {"valid": False, "error": "unsupported_artifact_type", "artifacts": rows}
        image_count += int(kind == "image")
        rows.append({
            "position": position,
            "url": artifact.url,
            "final_url": artifact.final_url,
            "content_type": str(artifact.content_type or ""),
            "kind": kind,
            "bytes": len(artifact.data),
            "sha256": sha256_bytes(artifact.data),
        })

    if not rows:
        return {"valid": False, "error": "no_artifacts", "artifacts": []}

    image_only = image_count == len(rows)
    if image_only and not (ocr and ocr.get("valid") and int(ocr.get("page_count") or 0) >= image_count):
        return {
            "valid": False,
            "error": "ocr_required_for_image_only_document",
            "artifacts": rows,
            "image_only": True,
        }

    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    bundle_sha = sha256_bytes(canonical)
    return {
        "valid": True,
        "error": None,
        "notice_url": notice.get("notice_url"),
        "notice_id": notice.get("notice_id"),
        "published_at": notice.get("published_at"),
        "modified_at": notice.get("modified_at"),
        "artifacts": rows,
        "artifact_count": len(rows),
        "image_only": image_only,
        "artifact_set_sha256": bundle_sha,
        "ocr": ocr if image_only else (ocr or None),
        "provenance": "bvc_notice_explicit_attachment_chain",
    }


def ingest_metadata_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if not bundle.get("valid"):
        return {"valid": False, "error": bundle.get("error") or "invalid_bundle"}
    return {
        "valid": True,
        "published_at": bundle.get("published_at"),
        "source_document_sha256": bundle.get("artifact_set_sha256"),
        "bvc_notice_url": bundle.get("notice_url"),
        "bvc_notice_id": bundle.get("notice_id"),
        "bvc_artifact_count": bundle.get("artifact_count"),
        "bvc_image_only": bool(bundle.get("image_only")),
        "bvc_artifacts": bundle.get("artifacts"),
        "ocr_evidence": bundle.get("ocr"),
        "provenance": bundle.get("provenance"),
    }
