"""Offline tests for the public ThaiJO detail-link resolver."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from resolve_thaijo_links import (  # noqa: E402
    DetailRedirectHandler,
    OriginalLinkParser,
    load_urls,
    main,
    resolve_all,
    resolve_one,
    validate_article_url,
    validate_detail_url,
)


DETAIL = "https://www.tci-thaijo.org/en/articles/physical01-18234"
LANDING = "https://so01.tci-thaijo.org/index.php/physics/article/view/12345"


class ResolverTests(unittest.TestCase):
    def test_cli_cannot_overwrite_source_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "urls.txt"
            path.write_text(DETAIL + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["--urls", str(path), "--expected-count", "1", "--output", str(path)])
            self.assertEqual(path.read_text(), DETAIL + "\n")

    def test_parser_finds_visible_label_with_nested_icon_text(self):
        parser = OriginalLinkParser()
        parser.feed('<a href="' + LANDING + '">Open Original Article <span>open_in_new</span></a>')
        self.assertEqual(parser.links, [LANDING])

    def test_parser_ignores_other_label(self):
        parser = OriginalLinkParser()
        parser.feed('<a href="' + LANDING + '">Download PDF</a>')
        self.assertEqual(parser.links, [])

    def test_label_must_not_be_an_arbitrary_substring(self):
        parser = OriginalLinkParser()
        parser.feed('<a href="' + LANDING + '">Not Open Original Article</a>')
        self.assertEqual(parser.links, [])

    def test_article_url_accepts_direct_landing_only(self):
        self.assertEqual(validate_article_url(LANDING, DETAIL), LANDING)
        self.assertIsNone(validate_article_url(LANDING + "/GALLEY/0", DETAIL))
        self.assertIsNone(validate_article_url("http://so01.tci-thaijo.org/index.php/x/article/view/1", DETAIL))
        self.assertIsNone(validate_article_url("https://example.org/x/article/view/1", DETAIL))
        self.assertIsNone(validate_article_url(LANDING + "?download=1", DETAIL))

    def test_input_validation_rejects_unobserved_or_unsafe_urls(self):
        accepted = validate_detail_url(DETAIL)
        self.assertEqual(accepted, (DETAIL, "www.tci-thaijo.org"))
        invalid = [
            "http://www.tci-thaijo.org/en/articles/physical01-18234",
            "https://evil-tci-thaijo.org/en/articles/physical01-18234",
            "https://so01.tci-thaijo.org/en/articles/physical01-18234",
            "https://user@www.tci-thaijo.org/en/articles/physical01-18234",
            "https://www.tci-thaijo.org/en/article/view/18234",
            DETAIL + "?next=https://example.org",
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_detail_url(url)

    def test_redirect_handler_rejects_host_scheme_and_path_escape(self):
        handler = DetailRedirectHandler("www.tci-thaijo.org", "/en/articles/physical01-18234")
        allowed = "https://www.tci-thaijo.org/en/articles/physical01-18234"
        request = Request(DETAIL)
        self.assertIsNotNone(handler.redirect_request(request, None, 302, "Found", {}, allowed))
        for url in (
            "http://www.tci-thaijo.org/en/articles/physical01-18234",
            "https://elsewhere.tci-thaijo.org/en/articles/physical01-18234",
            "https://www.tci-thaijo.org/article/view/123",
            "https://www.tci-thaijo.org/en/articles/physical01-99999",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "Found", {}, url)

    def test_resolve_requires_exactly_one_unique_valid_direct_target(self):
        html = f'<a href="{LANDING}">Open Original Article</a>'
        self.assertEqual(resolve_one(DETAIL, lambda _: html.encode()),
                         {"detail_url": DETAIL, "article_url": LANDING})
        duplicate_same_target = html + html
        self.assertEqual(resolve_one(DETAIL, lambda _: duplicate_same_target.encode())["article_url"], LANDING)
        two_targets = html + '<a href="https://so01.tci-thaijo.org/index.php/physics/article/view/99">Open Original Article</a>'
        with self.assertRaisesRegex(ValueError, "found 2"):
            resolve_one(DETAIL, lambda _: two_targets.encode())
        pdf_only = '<a href="' + LANDING + '/GALLEY/0">Open Original Article</a>'
        with self.assertRaisesRegex(ValueError, "found 0"):
            resolve_one(DETAIL, lambda _: pdf_only.encode())

    def test_load_urls_rejects_count_and_duplicate_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "urls.txt"
            path.write_text(DETAIL + "\n", encoding="utf-8")
            self.assertEqual(load_urls(path, 1), [DETAIL])
            with self.assertRaisesRegex(ValueError, "expected 2"):
                load_urls(path, 2)
            path.write_text(DETAIL + "\n" + DETAIL + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_urls(path, 2)

    def test_parallel_resolution_preserves_order_and_reports_duplicate_targets(self):
        second = "https://www.tci-thaijo.org/en/articles/physical01-18235"
        html = f'<a href="{LANDING}">Open Original Article</a>'.encode()
        mappings, errors = resolve_all([DETAIL, second], 2, lambda _: html)
        self.assertEqual([row["detail_url"] for row in mappings], [DETAIL, second])
        self.assertEqual(len({row["article_url"] for row in mappings}), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("duplicate resolved article URL", errors[0]["error"])

    def test_cli_writes_partial_output_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "urls.txt"
            output_path = Path(directory) / "nested" / "result.json"
            missing = "https://www.tci-thaijo.org/en/articles/physical01-18235"
            input_path.write_text(DETAIL + "\n" + missing + "\n", encoding="utf-8")
            # Patch the module-level resolver used by resolve_all; no network is attempted.
            import resolve_thaijo_links
            original = resolve_thaijo_links.resolve_all
            try:
                fetcher = lambda url: (
                    f'<a href="{LANDING}">Open Original Article</a>'.encode()
                    if url == DETAIL else b'<html><body>unavailable</body></html>')
                resolve_thaijo_links.resolve_all = lambda urls, workers: original(urls, workers, fetcher)
                status = main(["--urls", str(input_path), "--expected-count", "2",
                               "--output", str(output_path), "--workers", "2"])
            finally:
                resolve_thaijo_links.resolve_all = original
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(status, 1)
            self.assertEqual(payload["expected_count"], 2)
            self.assertEqual(payload["input_count"], 2)
            self.assertEqual(payload["unique_input_count"], 2)
            self.assertEqual(payload["output_count"], 1)
            self.assertEqual(payload["mappings"][0]["article_url"], LANDING)
            self.assertEqual(payload["errors"][0]["detail_url"], missing)


if __name__ == "__main__":
    unittest.main()
