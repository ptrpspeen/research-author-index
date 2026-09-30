#!/usr/bin/env python3
"""Validate and normalize compact, visible Scopus rank-table evidence offline.

This does not fetch Scopus or establish the journal's identity. Input must come
from the verified browser UI. Each category stays paired with its own cells.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urldefrag


def parse_evidence(data, expected_year):
    url = data.get("source_url", "")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "www.scopus.com"
            or not re.fullmatch(r"/sourceid/[0-9]+", parsed.path)
            or parsed.query or parsed.fragment not in ("", "tabs=0")):
        raise ValueError("Use the observed Scopus source detail URL (default CiteScore tab)")
    heading = data.get("rank_heading", "").strip()
    if heading != f"CiteScore rank {expected_year}":
        raise ValueError(f"Stale/wrong rank year: expected {expected_year}, got {heading!r}")
    rows = data.get("rows")
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("Missing rank table rows")
    result = []
    seen = set()
    for raw in rows:
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if lines == ["Category", "Rank", "Percentile"]:
            continue
        if len(lines) < 3:
            raise ValueError(f"Incomplete table row: {raw!r}")
        rank = re.fullmatch(r"#([0-9,]+)/([0-9,]+)", lines[-2])
        percentile = re.fullmatch(r"(100|[0-9]{1,2})(?:st|nd|rd|th)", lines[-1])
        if not rank or not percentile:
            raise ValueError(f"Unrecognized rank/percentile cells: {raw!r}")
        position, total = (int(v.replace(",", "")) for v in rank.groups())
        if not 1 <= position <= total:
            raise ValueError("Rank must be within its category total")
        category = ": ".join(lines[:-2])
        if category in seen:
            raise ValueError(f"Duplicate category; inspect visible tables: {category}")
        seen.add(category)
        value = int(percentile.group(1))
        result.append({"quartile_subject": category, "rank": lines[-2],
                       "citescore_percentile": value,
                       "quartile": f"Q{1 if value >= 75 else 2 if value >= 50 else 3 if value >= 25 else 4}"})
    if not result:
        raise ValueError("No category evidence")
    return {"quartile_source_url": urldefrag(url)[0], "observed_source_url": url,
            "quartile_year": expected_year,
            "categories": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = parse_evidence(json.loads(args.input.read_text(encoding="utf-8")), args.year)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        parser.exit(1, f"Error: {error}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"year": args.year, "categories": len(evidence["categories"])}))


if __name__ == "__main__":
    main()
