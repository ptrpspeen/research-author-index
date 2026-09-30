#!/usr/bin/env python3
"""Find Scopus/ThaiJO overlaps without deleting either database's record."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import unquote

from export_excel import validate_payload


def doi_key(value: str) -> str:
    value = unquote(value.strip().casefold())
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value).rstrip("/ ")


def title_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[\w]+", value, flags=re.UNICODE))


def author_tokens(row: dict) -> set[str]:
    return {token for name in row["authors"] for token in re.findall(r"[\w]+", title_key(name))
            if len(token) >= 3}


def reconcile(scopus: list[dict], tci: list[dict]) -> dict:
    matches, review = [], []
    matched_scopus, matched_tci = set(), set()
    doi_index: dict[str, list[int]] = {}
    for ti, item in enumerate(tci):
        if item["doi"]:
            doi_index.setdefault(doi_key(item["doi"]), []).append(ti)
    for si, item in enumerate(scopus):
        doi = doi_key(item["doi"]) if item["doi"] else ""
        for ti in doi_index.get(doi, []) if doi else []:
            if ti in matched_tci:
                review.append({"scopus_eid": item.get("scopus_eid"), "tci_url": tci[ti]["article_url"],
                               "reason": "DOI ซ้ำกับ TCI หลายแถว"})
                continue
            match = {"scopus_eid": item.get("scopus_eid"), "tci_url": tci[ti]["article_url"],
                     "method": "doi", "doi": doi}
            if item["publication_year"] != tci[ti]["publication_year"]:
                match["note"] = "ปีตีพิมพ์ต่างกัน; ตรวจ online first/ปีฉบับ"
            matches.append(match)
            matched_scopus.add(si)
            matched_tci.add(ti)
    for si, source in enumerate(scopus):
        if si in matched_scopus:
            continue
        ranked = []
        for ti, target in enumerate(tci):
            if ti in matched_tci or source["publication_year"] != target["publication_year"]:
                continue
            ratio = SequenceMatcher(None, title_key(source["title"]), title_key(target["title"])).ratio()
            if ratio >= 0.9 and author_tokens(source) & author_tokens(target):
                ranked.append((ratio, ti))
        ranked.sort(reverse=True)
        if not ranked:
            continue
        ratio, ti = ranked[0]
        target = tci[ti]
        entry = {"scopus_eid": source.get("scopus_eid"), "tci_url": target["article_url"],
                 "title_similarity": round(ratio, 3)}
        if len(ranked) > 1 or (source["doi"] and target["doi"] and doi_key(source["doi"]) != doi_key(target["doi"])):
            entry["reason"] = "ชื่อคล้ายแต่ DOI ขัดแย้งหรือมีหลายรายการ"
            review.append(entry)
        elif ratio >= 0.96:
            matches.append({**entry, "method": "title_year_authors"})
            matched_scopus.add(si)
            matched_tci.add(ti)
        else:
            entry["reason"] = "ชื่อคล้ายแต่ยังไม่ถึงเกณฑ์จับคู่อัตโนมัติ"
            review.append(entry)
    return {
        "summary": {"scopus_rows": len(scopus), "tci_rows": len(tci), "matched": len(matches),
                    "needs_review": len(review), "scopus_only": len(scopus) - len(matched_scopus),
                    "tci_only": len(tci) - len(matched_tci)},
        "matches": matches,
        "needs_review": review,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = validate_payload(json.loads(args.input.read_text(encoding="utf-8")))
        result = reconcile(payload["scopus"], payload["tci"])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result["summary"], ensure_ascii=False))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
