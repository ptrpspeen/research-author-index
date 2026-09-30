#!/usr/bin/env python3
"""Check every filled Q against saved parse_citescore_table.py evidence."""
import argparse
import json
from pathlib import Path
from urllib.parse import urldefrag


def verify(report, evidence):
    entries = {}
    for capture in evidence:
        for category in capture["categories"]:
            key = (urldefrag(capture["quartile_source_url"])[0],
                   capture["quartile_year"], category["quartile_subject"])
            value = (category["citescore_percentile"], category["quartile"])
            if key in entries and entries[key] != value:
                raise ValueError(f"Conflicting saved evidence for {key}")
            entries[key] = value
    checked = 0
    for row in report["scopus"]:
        if not row.get("quartile"):
            continue
        key = (urldefrag(row["quartile_source_url"])[0],
               row["quartile_year"], row["quartile_subject"])
        actual = (row["citescore_percentile"], row["quartile"])
        if entries.get(key) != actual:
            raise ValueError(f"{row.get('scopus_eid', row.get('title'))}: Q tuple does not match saved source/year/category evidence")
        checked += 1
    return {"q_rows_checked": checked, "status": "passed",
            "limits": "Checks correspondence to supplied captures, not their authenticity or category relevance."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Final report JSON")
    parser.add_argument("--evidence-dir", type=Path, required=True,
                        help="Directory containing only parsed CiteScore evidence JSON files")
    args = parser.parse_args()
    try:
        if not args.evidence_dir.is_dir():
            raise ValueError("Evidence directory does not exist")
        evidence = [json.loads(path.read_text(encoding="utf-8"))
                    for path in sorted(args.evidence_dir.glob("*.json"))]
        result = verify(json.loads(args.input.read_text(encoding="utf-8")), evidence)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
