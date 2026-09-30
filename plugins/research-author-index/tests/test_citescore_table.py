import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from parse_citescore_table import parse_evidence
from verify_citescore_evidence import verify


class CiteScoreEvidenceTests(unittest.TestCase):
    def fixture(self):
        return {"source_url": "https://www.scopus.com/sourceid/12264",
                "rank_heading": "CiteScore rank 2024",
                "rows": ["Category\nRank\nPercentile",
                         "Computer Science\nHardware and Architecture\n \n#5/224\n \n97th",
                         "Computer Science\nSoftware\n \n#22/490\n \n95th"]}

    def test_preserves_actual_category_percentile_pairs(self):
        rows = parse_evidence(self.fixture(), 2024)["categories"]
        self.assertEqual(rows[0]["quartile_subject"], "Computer Science: Hardware and Architecture")
        self.assertEqual(rows[0]["citescore_percentile"], 97)
        self.assertEqual(rows[1]["quartile_subject"], "Computer Science: Software")
        self.assertEqual(rows[1]["citescore_percentile"], 95)

    def test_rejects_previous_year_even_with_selected_year_claim(self):
        data = self.fixture()
        data.update(rank_heading="CiteScore rank 2025", selected_year=2024)
        with self.assertRaisesRegex(ValueError, "Stale/wrong rank year"):
            parse_evidence(data, 2024)

    def test_accepts_observed_default_tab_fragment(self):
        data = self.fixture()
        data["source_url"] += "#tabs=0"
        result = parse_evidence(data, 2024)
        self.assertEqual(result["observed_source_url"], data["source_url"])
        self.assertEqual(result["quartile_source_url"], "https://www.scopus.com/sourceid/12264")

    def test_rejects_incomplete_or_ambiguous_rows(self):
        for extra in ("Software\n95th", self.fixture()["rows"][1]):
            data = self.fixture()
            data["rows"].append(extra)
            with self.assertRaises(ValueError):
                parse_evidence(data, 2024)

    def test_rejects_non_scopus_evidence(self):
        data = self.fixture()
        data["source_url"] = "https://www.scopus.com.example.org/sourceid/12264"
        with self.assertRaises(ValueError):
            parse_evidence(data, 2024)

    def test_rejects_batch_overwrite_even_when_quartile_still_matches(self):
        capture = parse_evidence(self.fixture(), 2024)
        software = capture["categories"][1]
        row = {"scopus_eid": "example", "quartile_source_url": capture["quartile_source_url"],
               "quartile_year": 2024, **software}
        self.assertEqual(verify({"scopus": [row]}, [capture])["q_rows_checked"], 1)
        row["citescore_percentile"] = 97  # Still Q1, but belongs to another category.
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify({"scopus": [row]}, [capture])

    def test_rejects_missing_capture(self):
        capture = parse_evidence(self.fixture(), 2024)
        row = {"scopus_eid": "example", "quartile_source_url": capture["quartile_source_url"],
               "quartile_year": 2024, **capture["categories"][1]}
        with self.assertRaises(ValueError):
            verify({"scopus": [row]}, [])

    def test_rejects_conflicting_captures(self):
        one = parse_evidence(self.fixture(), 2024)
        two = parse_evidence(self.fixture(), 2024)
        two["categories"][1]["citescore_percentile"] = 97
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            verify({"scopus": []}, [one, two])


if __name__ == "__main__":
    unittest.main()
