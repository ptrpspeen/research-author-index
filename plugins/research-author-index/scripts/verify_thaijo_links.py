#!/usr/bin/env python3
"""Compare every TCI row to citation metadata at its direct ThaiJO URL.

Use an existing collect_thaijo.py draft for a cheap offline check or --live to
refresh the public pages. Scopus EID/link matching is done by export_excel.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from collect_thaijo import fetch
from export_excel import validate_payload


def normalized(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", unicodedata.normalize("NFKC", value).casefold()))


def check_one(report: dict, source: dict) -> list[str]:
    problems = []
    if not source.get("title"):
        return ["หน้าต้นทางไม่มี citation_title"]
    similarity = SequenceMatcher(None, normalized(report["title"]), normalized(source["title"])).ratio()
    if similarity < 0.9:
        problems.append(f"ชื่อเรื่องไม่ตรง (similarity {similarity:.2f})")
    if source.get("publication_year") and report["publication_year"] != source["publication_year"]:
        problems.append(f"ปีไม่ตรง ({report['publication_year']} / {source['publication_year']})")
    if report.get("doi") and source.get("doi") and normalized(report["doi"]) != normalized(source["doi"]):
        problems.append("DOI ไม่ตรง")
    if source.get("authors") and len(report["authors"]) != len(source["authors"]):
        problems.append(f"จำนวนผู้แต่งไม่ตรง ({len(report['authors'])} / {len(source['authors'])})")
    elif source.get("authors"):
        names = lambda items: [" ".join(unicodedata.normalize("NFKC", name).casefold().split()) for name in items]
        if names(report["authors"]) != names(source["authors"]):
            problems.append("ชื่อหรือลำดับผู้แต่งไม่ตรงกับ metadata ต้นทาง; ตรวจด้วยคน")
    for field, label in (("volume", "ปีที่/เล่มที่"), ("issue", "ฉบับที่")):
        if report.get(field) and source.get(field) and str(report[field]).strip() != str(source[field]).strip():
            problems.append(f"{label} ไม่ตรง ({report[field]} / {source[field]})")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--metadata-draft", type=Path, help="ผลจาก collect_thaijo.py")
    source.add_argument("--live", action="store_true", help="ดึงหน้า ThaiJO สาธารณะใหม่ทุก URL")
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.delay < 0:
            raise ValueError("--delay ต้องไม่ติดลบ")
        payload = validate_payload(json.loads(args.input.read_text(encoding="utf-8")))
        if args.metadata_draft:
            draft = json.loads(args.metadata_draft.read_text(encoding="utf-8"))
            source_rows = {row["article_url"]: row for row in draft["rows"]}
        else:
            source_rows = {}
        findings = []
        for index, row in enumerate(payload["tci"]):
            try:
                if args.live:
                    if index:
                        time.sleep(args.delay)
                    observed = fetch(row["article_url"])
                else:
                    observed = source_rows.get(row["article_url"])
                    if not observed:
                        raise ValueError("URL ไม่มีใน metadata draft")
                problems = check_one(row, observed)
            except Exception as exc:
                problems = [str(exc)]
            if problems:
                findings.append({"article_url": row["article_url"], "title": row["title"], "problems": problems})
        result = {"checked": len(payload["tci"]), "mismatched": len(findings), "findings": findings}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"checked": result["checked"], "mismatched": result["mismatched"]}, ensure_ascii=False))
        return 1 if findings else 0
    except (ValueError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
