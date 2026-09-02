from services.bvc_attachment_adapter_v5 import (
    DownloadedArtifact,
    build_evidence_bundle,
    build_ocr_evidence,
    extract_notice_artifact_urls,
    ingest_metadata_from_bundle,
    is_official_bvc_url,
    parse_bvc_wp_notice,
)


def _notice_payload(html: str):
    return {
        "id": 123,
        "link": "https://www.bolsadecaracas.com/post/estado-financiero-cantv/",
        "date_gmt": "2026-08-31T14:30:00",
        "modified_gmt": "2026-08-31T15:00:00",
        "title": {"rendered": "Estado financiero CANTV"},
        "content": {"rendered": html},
    }


def test_bvc_host_validation_is_strict():
    assert is_official_bvc_url("https://www.bolsadecaracas.com/aviso")
    assert is_official_bvc_url("https://market.bolsadecaracas.com/es")
    assert not is_official_bvc_url("http://www.bolsadecaracas.com/aviso")
    assert not is_official_bvc_url("https://bolsadecaracas.com.attacker.invalid/aviso")


def test_notice_extracts_bvc_and_explicit_sharepoint_only():
    html = """
      <a href="/wp-content/uploads/a.pdf">PDF local</a>
      <a href="https://tenant.sharepoint.com/sites/bvc/a.pdf">SharePoint</a>
      <a href="https://evil.example/a.pdf">No</a>
      <img src="/wp-content/uploads/page-1.jpg">
    """
    notice = parse_bvc_wp_notice(_notice_payload(html))
    assert notice["valid"] is True
    assert notice["published_at"] == "2026-08-31T14:30:00Z"
    assert notice["artifact_count"] == 3
    assert all("evil.example" not in url for url in notice["artifact_urls"])


def test_untrusted_notice_fails_closed():
    payload = _notice_payload("<a href='/a.pdf'>x</a>")
    payload["link"] = "https://evil.example/post/1"
    notice = parse_bvc_wp_notice(payload)
    assert notice["valid"] is False
    assert notice["error"] == "untrusted_notice_url"


def test_image_only_bundle_requires_reproducible_ocr():
    html = '<img src="/wp-content/uploads/p1.jpg"><img src="/wp-content/uploads/p2.jpg">'
    notice = parse_bvc_wp_notice(_notice_payload(html))
    urls = notice["artifact_urls"]
    artifacts = [
        DownloadedArtifact(url=urls[0], final_url=urls[0], content_type="image/jpeg", data=b"\xff\xd8\xffpage1"),
        DownloadedArtifact(url=urls[1], final_url=urls[1], content_type="image/jpeg", data=b"\xff\xd8\xffpage2"),
    ]
    blocked = build_evidence_bundle(notice, artifacts)
    assert blocked["valid"] is False
    assert blocked["error"] == "ocr_required_for_image_only_document"

    ocr = build_ocr_evidence(["Activos 100\r\n", "Patrimonio   70"], engine="test-ocr", engine_version="1")
    accepted = build_evidence_bundle(notice, artifacts, ocr=ocr)
    assert accepted["valid"] is True
    assert accepted["image_only"] is True
    assert len(accepted["artifact_set_sha256"]) == 64
    assert len(accepted["ocr"]["ocr_sha256"]) == 64


def test_artifact_not_linked_by_notice_is_rejected():
    notice = parse_bvc_wp_notice(_notice_payload('<a href="/wp-content/uploads/a.pdf">a</a>'))
    artifact = DownloadedArtifact(
        url="https://www.bolsadecaracas.com/wp-content/uploads/not-linked.pdf",
        final_url="https://www.bolsadecaracas.com/wp-content/uploads/not-linked.pdf",
        content_type="application/pdf",
        data=b"%PDF-1.7 fake",
    )
    result = build_evidence_bundle(notice, [artifact])
    assert result["valid"] is False
    assert result["error"] == "artifact_not_linked_by_notice"


def test_pdf_bundle_exports_collector_metadata():
    notice = parse_bvc_wp_notice(_notice_payload('<a href="/wp-content/uploads/a.pdf">a</a>'))
    url = notice["artifact_urls"][0]
    artifact = DownloadedArtifact(
        url=url,
        final_url=url,
        content_type="application/pdf",
        data=b"%PDF-1.7 deterministic bytes",
    )
    bundle = build_evidence_bundle(notice, [artifact])
    assert bundle["valid"] is True
    meta = ingest_metadata_from_bundle(bundle)
    assert meta["valid"] is True
    assert meta["published_at"] == notice["published_at"]
    assert meta["source_document_sha256"] == bundle["artifact_set_sha256"]
    assert meta["provenance"] == "bvc_notice_explicit_attachment_chain"
