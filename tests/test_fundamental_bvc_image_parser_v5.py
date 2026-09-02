import unittest
from unittest.mock import patch

from services.fundamental_bvc_image_parser_v5 import (
    _bundle_sha256,
    _is_certified_bvc_url,
    _ocr_image,
    extract_media_ids,
)


class FundamentalBvcImageParserV5Tests(unittest.TestCase):
    def test_bvc_authority_does_not_require_issuer_host_registration(self):
        self.assertTrue(_is_certified_bvc_url(
            "EFE",
            "https://www.bolsadecaracas.com/wp-json/wp/v2/posts/24445",
        ))
        self.assertFalse(_is_certified_bvc_url(
            "EFE",
            "https://empresaspolar.com/estado-financiero.jpg",
        ))

    def test_extracts_stable_wordpress_media_ids(self):
        html = '''
        <img class="wp-image-29953 size-large" src="a.jpg">
        <img class="size-large wp-image-29954" src="b.jpg">
        <img class="wp-image-29953" src="duplicate.jpg">
        '''
        self.assertEqual(extract_media_ids(html), [29953, 29954])

    def test_bundle_hash_depends_on_order_and_exact_bytes(self):
        self.assertEqual(_bundle_sha256([]), None)
        self.assertNotEqual(_bundle_sha256([b"a", b"b"]), _bundle_sha256([b"b", b"a"]))
        self.assertNotEqual(_bundle_sha256([b"ab"]), _bundle_sha256([b"a", b"b"]))

    @patch("services.fundamental_bvc_image_parser_v5.shutil.which", return_value=None)
    def test_ocr_fails_closed_when_binary_is_absent(self, _which):
        text, error = _ocr_image(b"image")
        self.assertEqual(text, "")
        self.assertEqual(error, "tesseract_not_installed")


if __name__ == "__main__":
    unittest.main()
