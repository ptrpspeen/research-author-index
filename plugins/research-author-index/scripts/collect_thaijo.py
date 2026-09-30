#!/usr/bin/env python3
"""Collect citation metadata from *known* public ThaiJO article URLs.

The script never searches for or guesses URLs. Review the generated rows before
adding TCI tiers or exporting a workbook.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class CitationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, list[str]] = {}
        self.issue_links: list[tuple[str, str]] = []
        self._issue_href: str | None = None
        self._issue_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag == "meta":
            name = data.get("name") or ""
            value = data.get("content") or ""
            if name.startswith("citation_") and value.strip():
                self.meta.setdefault(name, []).append(value.strip())
        elif tag == "a" and "/issue/view/" in (data.get("href") or ""):
            self._issue_href = data["href"]
            self._issue_text = []

    def handle_data(self, data: str) -> None:
        if self._issue_href is not None:
            self._issue_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._issue_href is not None:
            title = " ".join(" ".join(self._issue_text).split())
            self.issue_links.append((self._issue_href, title))
            self._issue_href = None
            self._issue_text = []


def allowed(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return (
        parsed.scheme == "https"
        and (host == "tci-thaijo.org" or host.endswith(".tci-thaijo.org"))
        and "/article/view/" in parsed.path
        and not parsed.username
    )


def first(meta: dict[str, list[str]], name: str) -> str:
    return (meta.get(name) or [""])[0]


def matches_issue_title(title: str, volume: str, issue: str, year: int | None) -> bool:
    if not title or not volume or not issue or not year:
        return False
    volume_pattern = rf"(?:vol(?:ume)?\.?|ปีที่|เล่มที่)\s*{re.escape(volume)}(?!\d)"
    issue_pattern = rf"(?:no\.?|issue|ฉบับที่)\s*{re.escape(issue)}(?!\d)"
    year_pattern = rf"(?<!\d)(?:{year}|{year + 543})(?!\d)"
    return bool(re.search(volume_pattern, title, re.IGNORECASE)
                and re.search(issue_pattern, title, re.IGNORECASE)
                and re.search(year_pattern, title))


def fetch(url: str) -> dict:
    if not allowed(url):
        raise ValueError("expected a direct HTTPS ThaiJO article URL")
    request = Request(url, headers={"User-Agent": "ResearchAuthorIndex/0.1 (metadata review)"})
    with urlopen(request, timeout=25) as response:
        if not allowed(response.url):
            raise ValueError("redirected outside a direct ThaiJO article page")
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("article page exceeds 2 MB")
    parser = CitationParser()
    parser.feed(raw.decode("utf-8", "replace"))
    meta = parser.meta
    date = first(meta, "citation_date") or first(meta, "citation_publication_date")
    year = re.match(r"^((?:19|20)\d{2})", date)
    publication_year = int(year.group(1)) if year else None
    volume = first(meta, "citation_volume")
    issue = first(meta, "citation_issue")
    authors = meta.get("citation_author", [])
    doi = first(meta, "citation_doi")
    issue_url, issue_title = "", ""
    for href, title in parser.issue_links:
        candidate = urljoin(url, href)
        parsed_issue = urlparse(candidate)
        if (parsed_issue.scheme == "https" and parsed_issue.hostname == urlparse(url).hostname
                and "/issue/view/" in parsed_issue.path
                and matches_issue_title(title, volume, issue, publication_year)):
            issue_url, issue_title = candidate, title
            break
    return {
        "title": first(meta, "citation_title"),
        "publication_year": publication_year,
        "authors": authors,
        "authors_complete": bool(authors),
        "journal": first(meta, "citation_journal_title"),
        "volume": volume,
        "issue": issue,
        "issue_title": issue_title,
        "issue_url": issue_url,
        "issn": first(meta, "citation_issn"),
        "doi": doi,
        "article_url": url,
        "verification_status": "needs_review",
        "notes": "ThaiJO citation metadata; ตรวจชื่อผู้วิจัย ปีฉบับวารสาร และ Tier ก่อนยืนยัน",
    }


def collection_summary(rows: list[dict], errors: list[dict]) -> dict:
    years = [r["publication_year"] for r in rows if type(r.get("publication_year")) is int]
    return {"rows": len(rows), "fetch_errors": len(errors),
            "publication_year_range": [min(years), max(years)] if years else None,
            "missing_fields": {field: sum(row.get(field) in (None, "", []) for row in rows)
                               for field in ("title", "publication_year", "authors", "journal", "volume", "issue", "issn", "doi", "issue_url", "issue_title", "document_type", "tier", "tier_period", "tier_source_url")}}


def review_draft(draft: dict, names: list[str]) -> dict:
    normalize = lambda name: " ".join(unicodedata.normalize("NFKC", name).casefold().split())
    rows, errors = draft["rows"], draft.get("errors", [])
    summary = collection_summary(rows, errors)
    summary["unique_urls"] = len({r["article_url"] for r in rows})
    summary["needs_review"] = sum(r.get("verification_status") == "needs_review" for r in rows)
    summary["missing_metadata_rows"] = [
        {"row": i, "article_url": r["article_url"],
         "fields": [f for f in ("title", "publication_year", "authors", "journal", "volume", "issue")
                    if r.get(f) in (None, "", [])]}
        for i, r in enumerate(rows, 1)
        if any(r.get(f) in (None, "", []) for f in ("title", "publication_year", "authors", "journal", "volume", "issue"))]
    if names:
        aliases = {normalize(n) for n in names}
        unmatched = [{"row": i, "article_url": r["article_url"], "authors": r.get("authors", [])}
                     for i, r in enumerate(rows, 1)
                     if not any(normalize(a) in aliases for a in r.get("authors", []))]
        summary["target_name_matches"] = len(rows) - len(unmatched)
        summary["unmatched_target_names"] = unmatched
        summary["name_check_scope"] = "Exact verified aliases after Unicode/whitespace normalization; not proof of identity or coverage"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--urls", type=Path, help="UTF-8 text file; one observed article URL per line")
    mode.add_argument("--review-draft", type=Path, help="Offline: summarize an existing draft, no network")
    parser.add_argument("--author-name", action="append", default=[], help="Verified full-name alias; repeat for Thai/English variants")
    parser.add_argument("--output", type=Path, help="JSON output for manual review; required for collection")
    parser.add_argument("--delay", type=float, default=0.3, help="seconds between requests")
    args = parser.parse_args()
    if args.delay < 0:
        parser.error("--delay must be nonnegative")
    if args.review_draft:
        result = review_draft(json.loads(args.review_draft.read_text(encoding="utf-8")), args.author_name)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result["fetch_errors"] else 0
    if not args.output:
        parser.error("--urls requires --output")
    urls = [line.strip() for line in args.urls.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    if len(urls) != len(set(urls)):
        parser.error("duplicate URLs in input")
    rows, errors = [], []
    for index, url in enumerate(urls):
        if index:
            time.sleep(args.delay)
        try:
            rows.append(fetch(url))
        except Exception as exc:
            errors.append({"article_url": url, "error": str(exc)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"rows": rows, "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**review_draft({"rows": rows, "errors": errors}, args.author_name), "output": str(args.output)}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
