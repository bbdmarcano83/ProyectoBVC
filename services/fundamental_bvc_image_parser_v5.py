"""Parser reproducible para estados publicados por BVC como imágenes.

La API oficial de WordPress aporta fecha de publicación, identidad estable del
post y los IDs de cada adjunto. Descargamos los originales registrados, fijamos
la huella SHA-256 del conjunto y usamos Tesseract sólo para producir candidatos;
la ecuación contable y la revisión explícita siguen siendo obligatorias.
"""
from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import tempfile

import httpx

from services.fundamental_pdf_parser_v5 import extract_candidates_from_pages
from services.fundamental_sources_v5 import get_source, source_url_allowed

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_POST_IMAGES = 12
BVC_API_ROOT = "https://www.bolsadecaracas.com/wp-json/wp/v2"


class _MediaIdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.media_ids: list[int] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "img":
            return
        classes = str(dict(attrs).get("class") or "").split()
        for name in classes:
            if not name.startswith("wp-image-"):
                continue
            try:
                media_id = int(name.removeprefix("wp-image-"))
            except ValueError:
                continue
            if media_id not in self.media_ids:
                self.media_ids.append(media_id)


def extract_media_ids(html: str) -> list[int]:
    parser = _MediaIdParser()
    parser.feed(str(html or ""))
    return parser.media_ids[:MAX_POST_IMAGES]


def _bundle_sha256(images: list[bytes]) -> str | None:
    if not images:
        return None
    digest = sha256()
    for index, data in enumerate(images):
        digest.update(index.to_bytes(4, "big"))
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _ocr_image(data: bytes, suffix: str = ".jpg") -> tuple[str, str | None]:
    executable = shutil.which("tesseract")
    if not executable:
        return "", "tesseract_not_installed"
    with tempfile.TemporaryDirectory(prefix="bvc-fundamental-") as tmp:
        path = Path(tmp) / f"page{suffix}"
        path.write_bytes(data)
        try:
            proc = subprocess.run(
                [executable, str(path), "stdout", "-l", "eng", "--psm", "6"],
                check=False,
                capture_output=True,
                text=True,
                timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "", f"ocr_error:{type(exc).__name__}"
    if proc.returncode != 0:
        return "", f"ocr_exit:{proc.returncode}"
    return proc.stdout, None


def fetch_and_parse_bvc_post(symbol: str, post_id: int, timeout: float = 30.0) -> tuple[dict, dict]:
    symbol = str(symbol or "").upper().strip()
    if not get_source(symbol):
        return {}, {"valid": False, "reason": "unregistered_symbol"}
    try:
        post_id = int(post_id)
    except (TypeError, ValueError):
        return {}, {"valid": False, "reason": "invalid_bvc_post_id"}
    if post_id <= 0:
        return {}, {"valid": False, "reason": "invalid_bvc_post_id"}

    post_url = f"{BVC_API_ROOT}/posts/{post_id}"
    if not source_url_allowed(symbol, post_url):
        return {}, {"valid": False, "reason": "bvc_host_not_registered_for_issuer"}
    headers = {"User-Agent": "CaracasBull-FundamentalAudit/1.0", "Accept": "application/json"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            post_response = client.get(post_url)
            post_response.raise_for_status()
            if not source_url_allowed(symbol, str(post_response.url)):
                return {}, {"valid": False, "reason": "bvc_post_redirect_host_rejected"}
            post = post_response.json()
            source_url = str(post.get("link") or "")
            if not source_url_allowed(symbol, source_url):
                return {}, {"valid": False, "reason": "bvc_post_link_host_rejected"}
            media_ids = extract_media_ids((post.get("content") or {}).get("rendered") or "")
            if not media_ids:
                return {}, {"valid": False, "reason": "bvc_post_without_image_attachments", "source_url": source_url}

            pages: list[str] = []
            images: list[bytes] = []
            media_urls: list[str] = []
            ocr_errors: list[str] = []
            for media_id in media_ids:
                media_response = client.get(f"{BVC_API_ROOT}/media/{media_id}")
                media_response.raise_for_status()
                media = media_response.json()
                image_url = str(media.get("source_url") or "")
                if not source_url_allowed(symbol, image_url):
                    return {}, {"valid": False, "reason": "bvc_media_host_rejected", "media_id": media_id}
                image_response = client.get(image_url)
                image_response.raise_for_status()
                final_url = str(image_response.url)
                if not source_url_allowed(symbol, final_url):
                    return {}, {"valid": False, "reason": "bvc_media_redirect_host_rejected", "media_id": media_id}
                data = image_response.content
                if not data or len(data) > MAX_IMAGE_BYTES:
                    return {}, {"valid": False, "reason": "bvc_image_empty_or_too_large", "media_id": media_id}
                content_type = str(image_response.headers.get("content-type") or "").lower()
                if not content_type.startswith("image/"):
                    return {}, {"valid": False, "reason": "bvc_attachment_not_image", "media_id": media_id}
                suffix = ".png" if "png" in content_type else ".jpg"
                text, error = _ocr_image(data, suffix)
                if error:
                    ocr_errors.append(f"{media_id}:{error}")
                pages.append(text)
                images.append(data)
                media_urls.append(final_url)
    except Exception as exc:
        return {}, {"valid": False, "reason": f"bvc_download_error:{type(exc).__name__}", "post_id": post_id}

    candidates = extract_candidates_from_pages(pages)
    published = str(post.get("date_gmt") or "").strip()
    if published and not published.endswith("Z"):
        published += "Z"
    return candidates, {
        "valid": bool(candidates) and not ocr_errors,
        "reason": None if candidates and not ocr_errors else ("ocr_errors" if ocr_errors else "no_candidates"),
        "symbol": symbol,
        "post_id": post_id,
        "source_url": source_url,
        "published_at": published or None,
        "pages": len(pages),
        "empty_pages": sum(1 for page in pages if not page.strip()),
        "fields_with_candidates": len(candidates),
        "requires_review": True,
        "media_urls": media_urls,
        "ocr_errors": ocr_errors,
        "source_document_sha256": _bundle_sha256(images),
        "source_document_kind": "bvc_wordpress_image_bundle",
    }
