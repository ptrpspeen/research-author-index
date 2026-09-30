"""Offline tests for cautious extraction from observed ThaiJO profile payloads."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from collect_thaijo_profile import (  # noqa: E402
    DevalueReader, collect, main, parse_payload, validate_article_url,
)

URL = "https://www.tci-thaijo.org/en/authors/social05-40777"
LANDINGS = [f"https://so05.tci-thaijo.org/index.php/journal/article/view/{n}" for n in (10, 11)]


def synthetic_payload(total=2, page=1, per_page=2, urls=None):
    urls = urls or [f"https://so05.tci-thaijo.org/index.php/journal/article/view/{i + 10}" for i in range(total)]
    page_count = min(per_page, max(0, total - (page - 1) * per_page))
    vals = [None] * (500 + total + page_count * 5)
    vals[0] = ["ShallowReactive", 1]
    vals[1] = {"data": 2}
    vals[2] = ["ShallowReactive", 3]
    vals[3] = {"author-social05-40777": 4, "author-articles-social05-40777": 14}
    vals[4] = {"id": 5, "full_names": 6, "article_count": 9, "article_ids": 10, "orcid": 13}
    vals[5] = "social05-40777"
    vals[6] = {"en_US": 7, "th_TH": 8}
    vals[7], vals[8] = "Thara Angskun", "ธรา อั่งสกุล"
    vals[9] = total
    vals[10] = list(range(300, 300 + total))
    for i in range(total):
        vals[300 + i] = f"life01-{i + 1}"
    vals[13] = "https://orcid.org/0000-0003-3677-8327"
    vals[14] = {"hits": 15, "total": 16, "page": 17, "per_page": 18}
    start = (page - 1) * per_page
    page_count = min(per_page, max(0, total - start))
    vals[15] = list(range(40, 40 + page_count))
    vals[16], vals[17], vals[18] = total, page, per_page
    for i in range(page_count):
        hit_ref = 40 + i
        id_ref, title_map_ref, title_ref, url_ref = 100 + i * 4, 101 + i * 4, 102 + i * 4, 103 + i * 4
        vals[hit_ref] = {"id": id_ref, "titles": title_map_ref, "article_url": url_ref}
        vals[id_ref] = f"life01-{start + i + 1}"
        vals[title_map_ref] = {"en_US": title_ref}
        vals[title_ref] = f"Complete observed title {start + i + 1}"
        vals[url_ref] = urls[start + i]
    return vals


class CollectorTests(unittest.TestCase):
    def test_malformed_hit_url_and_missing_results_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "string"):
            validate_article_url(None)
        payload = synthetic_payload()
        del payload[14]["hits"]
        with self.assertRaisesRegex(ValueError, "reference"):
            collect(payload, URL, ["Thara Angskun"], 2)

    def test_selectively_resolves_wrapper_references_and_numeric_slots(self):
        payload = synthetic_payload()
        reader = DevalueReader(payload)
        root = reader.object(0)
        data = reader.object(root["data"])
        results = reader.object(data["author-articles-social05-40777"])
        profile = reader.object(data["author-social05-40777"])
        self.assertEqual(reader.scalar(results["page"]), 1)
        self.assertEqual(reader.scalar(profile["article_count"]), 2)

    def test_collect_returns_actual_landing_urls_and_marks_page_partial(self):
        result = collect(synthetic_payload(total=5, per_page=2), URL, ["  THARA Angskun "], 5)
        self.assertEqual([hit["article_url"] for hit in result["hits"]], LANDINGS)
        self.assertFalse(result["complete_profile"])
        self.assertEqual(result["remaining_count"], 3)

    def test_single_page_profile_can_be_complete(self):
        result = collect(synthetic_payload(total=2), URL, ["Thara Angskun"], 2)
        self.assertTrue(result["complete_profile"])
        self.assertEqual(result["remaining_count"], 0)

    def test_last_page_of_larger_profile_is_still_partial(self):
        result = collect(synthetic_payload(total=53, page=3, per_page=20), URL, ["Thara Angskun"], 53)
        self.assertEqual(len(result["hits"]), 13)
        self.assertFalse(result["complete_profile"])
        self.assertEqual(result["remaining_count"], 40)

    def test_rejects_wrong_url_identity_alias_or_expected_count(self):
        for args in (
            (synthetic_payload(), "https://www.tci-thaijo.org/en/authors/other-1", ["Thara Angskun"], 2),
            (synthetic_payload(), URL, ["Unverified Person"], 2),
            (synthetic_payload(), URL, ["Thara Angskun"], 3),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                collect(*args)
        with self.assertRaisesRegex(ValueError, "observed HTTPS"):
            collect(synthetic_payload(), "https://evil.tci-thaijo.org/en/authors/social05-40777",
                    ["Thara Angskun"], 2)
        with self.assertRaisesRegex(ValueError, "bad devalue scalar"):
            reader = DevalueReader(synthetic_payload())
            reader.scalar(True)

    def test_rejects_duplicate_ids_url_and_invalid_landing(self):
        payload = synthetic_payload()
        payload[10] = [300, 300]
        with self.assertRaisesRegex(ValueError, "duplicates"):
            collect(payload, URL, ["Thara Angskun"], 2)
        payload = synthetic_payload(urls=[LANDINGS[0], LANDINGS[0]])
        with self.assertRaisesRegex(ValueError, "duplicate returned article URL"):
            collect(payload, URL, ["Thara Angskun"], 2)
        for bad in (LANDINGS[0] + "/GALLEY/0", "http://so05.tci-thaijo.org/index.php/x/article/view/1",
                    "https://example.org/index.php/x/article/view/1"):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                validate_article_url(bad)

    def test_rejects_cycles_bad_references_and_malformed_scripts(self):
        with self.assertRaisesRegex(ValueError, "cycle"):
            DevalueReader([["Ref", 0]]).raw(0)
        with self.assertRaisesRegex(ValueError, "bad devalue"):
            DevalueReader([["Ref", True]]).raw(0)
        with self.assertRaisesRegex(ValueError, "unsupported devalue wrapper"):
            DevalueReader([["Date", 0]]).raw(0)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            parse_payload(b"<html></html>")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            parse_payload(b'<script id="__NUXT_DATA__" type="application/json">[]</script>'
                          b'<script id="__NUXT_DATA__" type="application/json">[]</script>')
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            parse_payload(b'<script id="__NUXT_DATA__" type="application/json">bad</script>')

    def test_cli_rejects_output_path_collision_before_fetching(self):
        with tempfile.TemporaryDirectory() as directory:
            same = str(Path(directory) / "output.json")
            with self.assertRaises(SystemExit):
                main(["--profile", URL, "--author-name", "Thara Angskun", "--expected-count", "2",
                      "--output", same, "--urls-output", same])

    def test_real_captured_fixture_is_parsed_without_packaging_it(self):
        fixture = ROOT.parents[0] / "profile-payload.json"
        if not fixture.exists():
            self.skipTest("local capture fixture is unavailable")
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        result = collect(payload, URL, ["Thara Angskun"], 53)
        self.assertEqual((result["profile_count"], result["result_total"], len(result["hits"])), (53, 53, 20))
        self.assertFalse(result["complete_profile"])
        self.assertEqual(result["remaining_count"], 33)


if __name__ == "__main__":
    unittest.main()
