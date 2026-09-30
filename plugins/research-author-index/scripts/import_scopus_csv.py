#!/usr/bin/env python3
"""Import a Scopus Documents CSV into the two-database report JSON.

The Scopus UI exports a complete author list, stable EID, DOI and link in one
file. Existing Q annotations are kept only when their source and year agree.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

from export_excel import annotate_scopus_doi_conflicts, check_orcid, scopus_link_eid, validate_payload


REQUIRED = {
    "Author full names", "Author(s) ID", "Title", "Year", "Source title",
    "Cited by", "DOI", "Link", "ISSN", "Document Type", "Publication Stage", "EID",
}
AUTHOR_WITH_ID = re.compile(r"^(.+?)\s+\((\d+)\)$")
EID = re.compile(r"^2-s2\.0-(\d+)$")


def parse_authors(raw: str, ids_raw: str, author_id: str) -> list[str]:
    parts = [item.strip() for item in raw.split(";") if item.strip()]
    ids = [item.strip() for item in ids_raw.split(";") if item.strip()]
    parsed = [AUTHOR_WITH_ID.fullmatch(part) for part in parts]
    if not parts or any(match is None for match in parsed):
        raise ValueError("Author full names ต้องมีชื่อเต็มและ Author ID ทุกคน")
    found_ids = [match.group(2) for match in parsed if match]
    if found_ids != ids:
        raise ValueError("Author full names และ Author(s) ID ไม่ตรงกัน")
    if author_id not in found_ids:
        raise ValueError(f"Scopus Author ID {author_id} ไม่อยู่ในรายชื่อผู้แต่ง")
    return [match.group(1).strip() for match in parsed if match]


def normalize_url(raw: str, eid: str) -> str:
    match = EID.fullmatch(eid)
    if not match:
        raise ValueError(f"EID ไม่ถูกต้อง: {eid}")
    expected = f"/pages/publications/{match.group(1)}"
    if scopus_link_eid(raw.strip()) != eid:
        raise ValueError(f"Link ไม่ตรงกับ EID {eid}: {raw}")
    return "https://www.scopus.com" + expected


def csv_record(raw: dict, author_id: str, profile_url: str, h_index: int | None, today: str) -> dict:
    eid = raw["EID"].strip()
    year = int(raw["Year"])
    citations = int(raw["Cited by"].strip()) if raw["Cited by"].strip() else None
    document_type = raw["Document Type"].strip().title()
    stage = raw["Publication Stage"].strip()
    if stage.casefold() == "article in press":
        document_type = "Article in Press"
    row = {
        "title": raw["Title"].strip(),
        "publication_year": year,
        "document_type": document_type,
        "authors": parse_authors(raw["Author full names"], raw["Author(s) ID"], author_id),
        "authors_complete": True,
        "journal": raw["Source title"].strip(),
        "issn": raw["ISSN"].strip(),
        "doi": raw["DOI"].strip(),
        "scopus_eid": eid,
        "scopus_author_id": author_id,
        "author_profile_url": profile_url,
        "citations": citations,
        "citations_as_of": today,
        "article_url": normalize_url(raw["Link"], eid),
        "verification_status": "confirmed",
    }
    if h_index is not None:
        row.update(author_h_index=h_index, h_index_as_of=today)
    if citations is None:
        row["notes"] = "CSV ไม่ระบุจำนวนอ้างอิง; เว้นว่าง ไม่ใช่ศูนย์"
    return row


def load_csv_records(paths: list[Path], author_id: str, profile_url: str,
                     h_index: int | None, retrieved_at: str, expected_count: int | None) -> list[dict]:
    raw_rows = []
    for csv_path in paths:
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED - set(reader.fieldnames or ())
            if missing:
                raise ValueError(f"{csv_path}: CSV ขาดคอลัมน์: " + ", ".join(sorted(missing)))
            raw_rows.extend(reader)
    if not raw_rows and expected_count != 0:
        raise ValueError("CSV ไม่มีรายการ")
    if expected_count is not None and len(raw_rows) != expected_count:
        raise ValueError(f"CSV มี {len(raw_rows)} แถว แต่โปรไฟล์/ตัวกรองคาด {expected_count}")
    fresh = []
    seen = set()
    for number, raw in enumerate(raw_rows, 2):
        try:
            row = csv_record(raw, author_id, profile_url, h_index, retrieved_at)
        except (ValueError, KeyError) as exc:
            raise ValueError(f"CSV บรรทัด {number}: {exc}") from exc
        if row["scopus_eid"] in seen:
            raise ValueError(f"CSV มี EID ซ้ำ: {row['scopus_eid']}")
        seen.add(row["scopus_eid"])
        fresh.append(row)
    return annotate_scopus_doi_conflicts(fresh)


def merge_previous(fresh: list[dict], previous: list[dict]) -> list[dict]:
    by_eid = {row.get("scopus_eid"): row for row in previous}
    if len(by_eid) != len(previous):
        raise ValueError("JSON เดิมมี EID ว่างหรือซ้ำ")
    removed = set(by_eid) - {row["scopus_eid"] for row in fresh}
    if removed:
        raise ValueError("CSV ใหม่ไม่มี EID จาก JSON เดิม; ตรวจตัวกรอง/โปรไฟล์ก่อนลบ: " + ", ".join(sorted(removed)))
    for row in fresh:
        old = by_eid.get(row["scopus_eid"])
        if not old:
            continue
        for field in ("title", "publication_year", "journal", "issn", "doi"):
            if str(old.get(field, "")).strip() != str(row.get(field, "")).strip():
                raise ValueError(f"{row['scopus_eid']}: {field} เปลี่ยนจาก JSON เดิม; ตรวจด้วยคนก่อน")
        for field in (
            "quartile", "citescore_percentile", "quartile_year", "quartile_subject",
            "quartile_source_url", "notes",
        ):
            if field in old:
                if field == "notes":
                    if row.get("notes") and old[field]:
                        row[field] = "; ".join(dict.fromkeys((old[field], row["notes"])))
                    elif old[field]:
                        row[field] = old[field]
                else:
                    row[field] = old[field]
    return fresh


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True, action="append",
                        help="Scopus CSV; ระบุซ้ำได้เมื่อส่งออกหลายชุด")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base", type=Path, help="JSON เดิม: คง TCI และ Q ที่ตรวจแล้ว")
    parser.add_argument("--name", help="ชื่อผู้วิจัย; จำเป็นเมื่อไม่มี --base")
    parser.add_argument("--affiliation", default="")
    parser.add_argument("--author-id", required=True, help="Scopus Author ID ที่ยืนยันจากโปรไฟล์")
    parser.add_argument("--profile-url", help="ลิงก์โปรไฟล์; ค่าเริ่มต้นสร้างจาก Author ID")
    parser.add_argument("--h-index", type=int, help="h-index ที่อ่านจากโปรไฟล์ ณ วันที่นำเข้า")
    parser.add_argument("--orcid", help="ORCID ที่ยืนยันแล้วเท่านั้น")
    parser.add_argument("--expected-count", required=True, type=int, help="จำนวน Documents บนโปรไฟล์หลังตัวกรอง")
    parser.add_argument("--scopus-filters", default="ไม่บันทึก; ยังไม่ยืนยันตัวกรอง")
    parser.add_argument("--retrieved-at", default=date.today().isoformat())
    args = parser.parse_args()
    try:
        if not args.author_id.isdigit() or (args.h_index is not None and args.h_index < 0):
            raise ValueError("Author ID และ h-index ต้องเป็นจำนวนเต็มไม่ติดลบ")
        profile_url = args.profile_url or f"https://www.scopus.com/authid/detail.uri?authorId={args.author_id}"
        if args.base:
            payload = json.loads(args.base.read_text(encoding="utf-8"))
        else:
            if not args.name:
                raise ValueError("ต้องระบุ --name เมื่อไม่มี --base")
            payload = {
                "researcher": {"name": args.name, "affiliation": args.affiliation},
                "retrieved_at": args.retrieved_at,
                "scopus": [], "tci": [],
            }
        if args.orcid:
            payload["researcher"]["orcid"] = check_orcid(args.orcid, "--orcid")
        fresh = load_csv_records(args.csv, args.author_id, profile_url, args.h_index,
                                 args.retrieved_at, args.expected_count)
        payload["scopus"] = merge_previous(fresh, payload.get("scopus", []))
        payload["retrieved_at"] = args.retrieved_at
        audit = payload.setdefault("audit", {})
        if args.expected_count is not None:
            audit["scopus_expected_count"] = args.expected_count
            audit["scopus_excluded_count"] = 0
        searches = audit.setdefault("searches", [])
        entry = {
            "database": "scopus",
            "query": f"AU-ID({args.author_id})",
            "method": "Documents CSV export",
            "results": len(fresh),
            "pages_checked": "CSV เทียบจำนวนกับ UI",
            "filters": args.scopus_filters,
            "checked_at": args.retrieved_at,
        }
        if not any(item.get("database") == "scopus" and item.get("query") == entry["query"]
                   and item.get("method") == entry["method"] for item in searches):
            searches.append(entry)
        validate_payload(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Imported {len(fresh)} Scopus records -> {args.output}")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
