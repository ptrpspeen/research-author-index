#!/usr/bin/env python3
"""Extract, reuse, and queue verified source metrics by ISSN and year.

This is an offline cache. Evidence must first be read from official Scopus/TCI
pages; the script never guesses a historical Q or Tier.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from export_excel import certified_year_range, is_journal_document, validate_payload
from reconcile_records import title_key


Q_FIELDS = ("citescore_percentile", "quartile", "quartile_year", "quartile_subject", "quartile_source_url")
TIER_FIELDS = ("tier", "tier_period", "tier_source_url", "tier_evidence_basis")


def issn_key(value: str) -> str:
    return re.sub(r"[^0-9X]", "", value.upper())


def q_key(row: dict) -> tuple[str, int]:
    return issn_key(row.get("issn", "")), row["publication_year"]


def collect_cache(payload: dict, strict: bool = True) -> dict:
    q, tier = {}, {}
    ambiguous_q, ambiguous_tier = set(), set()
    for row in payload["scopus"]:
        key = (issn_key(row.get("issn", "")), title_key(row["journal"]), row["publication_year"], row.get("quartile_subject", ""))
        if not key[0] or not row.get("quartile") or key in ambiguous_q:
            continue
        entry = {"issn": key[0], "journal": row["journal"], "publication_year": key[2],
                 **{field: row.get(field) for field in Q_FIELDS}}
        if key in q and q[key] != entry:
            if strict:
                raise ValueError(f"Q หลายค่าใน ISSN/วารสาร/ปีเดียวกัน {key}; แยกสาขาและตรวจด้วยคน")
            q.pop(key)
            ambiguous_q.add(key)
            continue
        q[key] = entry
    for row in payload["tci"]:
        key = (issn_key(row.get("issn", "")), title_key(row["journal"]), row.get("tier_period", ""))
        if not key[0] or not row.get("tier") or key in ambiguous_tier:
            continue
        entry = {"issn": key[0], "journal": row["journal"],
                 **{field: row.get(field) for field in TIER_FIELDS}}
        if key in tier and tier[key] != entry:
            if strict:
                raise ValueError(f"Tier หลายช่วงเวลาใน ISSN/วารสาร {key}; ตรวจด้วยคน")
            tier.pop(key)
            ambiguous_tier.add(key)
            continue
        tier[key] = entry
    return {"scopus": list(q.values()), "tci": list(tier.values())}


def queue(payload: dict, changes: dict | None = None) -> dict:
    scopus_ids = None
    tci_urls = None
    if changes is not None:
        scopus_ids = {item["eid"] for kind in ("added", "changed")
                       for item in changes.get("scopus", {}).get(kind, []) if item.get("metric_lookup")}
        tci_urls = {item["url"] for kind in ("added", "changed")
                    for item in changes.get("tci", {}).get(kind, []) if item.get("metric_lookup")}
    q = Counter(q_key(row) for row in payload["scopus"]
                if (scopus_ids is None or row.get("scopus_eid") in scopus_ids)
                and is_journal_document(row)
                and not row.get("quartile") and issn_key(row.get("issn", "")))
    tier = Counter(issn_key(row.get("issn", "")) for row in payload["tci"]
                   if (tci_urls is None or row.get("article_url") in tci_urls)
                   and not row.get("tier") and issn_key(row.get("issn", "")))
    return {
        "scopus_issn_year_to_check": [
            {"issn": issn, "publication_year": year, "article_count": count}
            for (issn, year), count in sorted(q.items())
        ],
        "tci_issn_to_check": [
            {"issn": issn, "article_count": count} for issn, count in sorted(tier.items())
        ],
    }


def apply_cache(payload: dict, cache: dict) -> tuple[dict, dict]:
    # Revalidate cache evidence when applied. A source/year alone does not
    # determine the relevant subject, and a current Tier is not historical.
    filled = {"scopus": 0, "tci": 0}
    for row in payload["scopus"]:
        if not is_journal_document(row) or not row.get("quartile_subject"):
            continue
        entries = [x for x in cache["scopus"]
                   if issn_key(x.get("issn", "")) == issn_key(row.get("issn", ""))
                   and bool(issn_key(row.get("issn", "")))
                   and title_key(x.get("journal", "")) == title_key(row["journal"])
                   and x.get("publication_year") == row["publication_year"]
                   and x.get("quartile_subject") == row["quartile_subject"]]
        values = {json.dumps({f:x.get(f) for f in Q_FIELDS}, sort_keys=True) for x in entries}
        if len(values) > 1:
            raise ValueError(f"{row['title']}: Q cache ขัดกันในปี/สาขาเดียวกัน")
        if entries and any(row.get(f) is not None and row.get(f) != "" and row[f] != entries[0].get(f) for f in Q_FIELDS):
            raise ValueError(f"{row['title']}: Q เดิมขัดกับ cache; ตรวจแหล่งทางการ")
        if entries and not row.get("quartile"):
            row.update({field: entries[0].get(field) for field in Q_FIELDS})
            filled["scopus"] += 1
    for row in payload["tci"]:
        entries = []
        for x in cache["tci"]:
            years = certified_year_range(x.get("tier_period", ""))
            if (years and years[0] <= row["publication_year"] <= years[1]
                    and bool(issn_key(row.get("issn", "")))
                    and issn_key(x.get("issn", "")) == issn_key(row.get("issn", ""))
                    and title_key(x.get("journal", "")) == title_key(row["journal"])):
                entries.append(x)
        # Different supporting periods for the same Tier are compatible. Prefer
        # an explicit bounded period over a publisher-since assertion.
        if len({x.get("tier") for x in entries}) > 1:
            raise ValueError(f"{row['title']}: Tier cache มีช่วงรับรองทับซ้อนที่ขัดกัน")
        entries.sort(key=lambda x: (x.get("tier_evidence_basis") == "publisher_since",
                                   certified_year_range(x["tier_period"])[1] - certified_year_range(x["tier_period"])[0],
                                   x.get("tier_source_url", "")))
        if entries and row.get("tier") and row["tier"] != entries[0].get("tier"):
            raise ValueError(f"{row['title']}: Tier เดิมขัดกับ cache; ตรวจแหล่งทางการ")
        if entries and not row.get("tier"):
            row.update({field: entries[0].get(field) for field in TIER_FIELDS})
            filled["tci"] += 1
    validate_payload(payload)
    return payload, filled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["extract", "queue", "apply"])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cache", type=Path, help="cache JSON; required for apply")
    parser.add_argument("--changes", type=Path, help="ใช้กับ queue เพื่อค้น metric เฉพาะรายการใหม่/เปลี่ยน")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        valid = validate_payload(raw)
        if args.mode == "extract":
            output = collect_cache(valid)
            summary = {"unique_scopus_metrics": len(output["scopus"]), "unique_tci_metrics": len(output["tci"])}
        elif args.mode == "queue":
            changes = json.loads(args.changes.read_text(encoding="utf-8")) if args.changes else None
            output = queue(valid, changes)
            summary = {"scopus_issn_years": len(output["scopus_issn_year_to_check"]),
                       "tci_issns": len(output["tci_issn_to_check"])}
        else:
            if not args.cache:
                raise ValueError("apply ต้องมี --cache")
            cache = json.loads(args.cache.read_text(encoding="utf-8"))
            output, summary = apply_cache(raw, cache)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False))
    except (ValueError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
