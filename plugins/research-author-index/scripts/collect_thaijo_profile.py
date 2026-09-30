#!/usr/bin/env python3
"""Collect the directly linked article records exposed by an observed ThaiJO profile."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 4 * 1024 * 1024
TIMEOUT_SECONDS = 20
PROFILE_PATH = re.compile(r"^/en/authors/([A-Za-z0-9_-]+-\d+)/?$")
ARTICLE_PATH = re.compile(r"^/(?:[^?#]*/)?article/view/\d+$")
WRAPPERS = {"ShallowReactive", "Reactive", "Ref", "ShallowRef"}


def allowed_host(host: str | None) -> bool:
    return bool(host and (host == "tci-thaijo.org" or host.endswith(".tci-thaijo.org")))


def validate_profile_url(url: str) -> tuple[str, str, str]:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("malformed profile URL") from exc
    match = PROFILE_PATH.fullmatch(parsed.path)
    if (parsed.scheme != "https" or parsed.hostname not in {"tci-thaijo.org", "www.tci-thaijo.org"} or parsed.username is not None
            or parsed.password is not None or port not in (None, 443) or not match
            or parsed.query or parsed.fragment):
        raise ValueError("expected an observed HTTPS ThaiJO /en/authors/<profile-id> URL")
    return url, parsed.hostname or "", match.group(1)


class ProfileRedirectHandler(HTTPRedirectHandler):
    def __init__(self, host: str, profile_id: str) -> None:
        super().__init__()
        self.host, self.profile_id = host, profile_id

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _, host, profile_id = validate_profile_url(newurl)
        if host != self.host or profile_id != self.profile_id:
            raise ValueError("redirect changed profile host or profile ID")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_html(url: str, opener_factory=build_opener) -> bytes:
    canonical, host, profile_id = validate_profile_url(url)
    opener = opener_factory(ProfileRedirectHandler(host, profile_id))
    try:
        with opener.open(Request(canonical, headers={"User-Agent": "ResearchAuthorIndex/0.1 (public profile collector)"}), timeout=TIMEOUT_SECONDS) as response:
            _, final_host, final_id = validate_profile_url(response.url)
            if final_host != host or final_id != profile_id:
                raise ValueError("redirect changed profile host or profile ID")
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("profile page exceeds 4 MB")
            return raw
    except HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise ValueError(f"request failed: {exc.reason}") from exc


class NuxtPayloadParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_payload = False
        self.payloads: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("id") == "__NUXT_DATA__":
            if self.in_payload:
                raise ValueError("nested Nuxt payload script")
            if attrs.get("type") != "application/json":
                raise ValueError("Nuxt payload script is not application/json")
            self.in_payload = True
            self.parts = []

    def handle_data(self, data):
        if self.in_payload:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.in_payload:
            self.payloads.append("".join(self.parts))
            self.in_payload = False


def parse_payload(html: bytes) -> list:
    parser = NuxtPayloadParser()
    parser.feed(html.decode("utf-8", "strict"))
    if len(parser.payloads) != 1:
        raise ValueError(f"expected exactly one __NUXT_DATA__ JSON script; found {len(parser.payloads)}")
    try:
        data = json.loads(parser.payloads[0])
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON in __NUXT_DATA__") from exc
    if not isinstance(data, list):
        raise ValueError("expected flattened Nuxt/devalue list")
    return data


class DevalueReader:
    """Resolve only the small object/list/reference subset needed by profile results."""
    def __init__(self, values: list):
        self.values = values
        self.active: set[int] = set()

    def raw(self, index: int):
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.values):
            raise ValueError("bad devalue reference index")
        if index in self.active:
            raise ValueError("cycle in devalue references")
        self.active.add(index)
        added = []
        try:
            value = self.values[index]
            while isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and value[0] in WRAPPERS:
                ref = value[1]
                if isinstance(ref, bool) or not isinstance(ref, int) or not 0 <= ref < len(self.values):
                    raise ValueError("bad devalue wrapper reference")
                if ref in self.active:
                    raise ValueError("cycle in devalue references")
                self.active.add(ref)
                added.append(ref)
                value = self.values[ref]
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                raise ValueError(f"unsupported devalue wrapper: {value[0]}")
            return value
        finally:
            for ref in added:
                self.active.discard(ref)
            self.active.discard(index)

    def object(self, ref: int) -> dict:
        value = self.raw(ref)
        if not isinstance(value, dict):
            raise ValueError("expected devalue object")
        return value

    def array(self, ref: int) -> list:
        value = self.raw(ref)
        if not isinstance(value, list):
            raise ValueError("expected devalue array")
        return value

    def scalar(self, ref):
        if isinstance(ref, bool) or not isinstance(ref, int):
            raise ValueError("bad devalue scalar reference")
        value = self.raw(ref)
        if isinstance(value, (dict, list)):
            return value
        return value

def _strict_int(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _canonical_alias(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def validate_article_url(url: str) -> str:
    if not isinstance(url, str):
        raise ValueError("article URL must be a string")
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("malformed article URL") from exc
    if (parsed.scheme != "https" or not allowed_host(parsed.hostname) or parsed.username is not None
            or parsed.password is not None or port not in (None, 443) or not ARTICLE_PATH.fullmatch(parsed.path)
            or parsed.query or parsed.fragment):
        raise ValueError("expected direct HTTPS ThaiJO article landing URL")
    return url


def collect(payload: list, profile_url: str, aliases: list[str], expected_count: int) -> dict:
    _, _, profile_id = validate_profile_url(profile_url)
    if expected_count < 0:
        raise ValueError("expected count must be nonnegative")
    reader = DevalueReader(payload)
    root = reader.object(0)
    if not isinstance(root, dict) or "data" not in root:
        raise ValueError("Nuxt root has no data object")
    data = reader.object(root["data"])
    profile_key = "author-" + profile_id
    results_key = "author-articles-" + profile_id
    if profile_key not in data or results_key not in data:
        raise ValueError("payload does not contain the exact profile and article result keys")
    profile = reader.object(data[profile_key])
    results = reader.object(data[results_key])
    def field(obj, key, required=True):
        if key not in obj:
            if required:
                raise ValueError(f"missing required field {key}")
            return None
        return reader.scalar(obj[key])
    if field(profile, "id") != profile_id:
        raise ValueError("profile ID does not match observed URL")
    names_raw = field(profile, "full_names")
    if not isinstance(names_raw, dict):
        raise ValueError("profile full_names is missing or malformed")
    full_names = {lang: reader.scalar(ref) for lang, ref in names_raw.items()}
    known_names = {_canonical_alias(name) for name in full_names.values() if isinstance(name, str)}
    requested = {_canonical_alias(alias) for alias in aliases}
    if not requested or not requested.issubset(known_names):
        raise ValueError("every --author-name must exactly match a normalized profile full name")
    profile_count = _strict_int(field(profile, "article_count"), "profile article_count")
    total = _strict_int(field(results, "total"), "result total")
    page = _strict_int(field(results, "page"), "result page")
    per_page = _strict_int(field(results, "per_page"), "result per_page")
    if min(profile_count, total) < 0 or page < 1 or per_page < 1:
        raise ValueError("invalid observed article counts or pagination")
    if profile_count != expected_count or total != expected_count:
        raise ValueError("profile count and result total must both equal --expected-count")
    article_ids = [reader.scalar(ref) for ref in reader.array(profile.get("article_ids"))]
    hits = reader.array(results.get("hits"))
    if (len(article_ids) != profile_count
            or not all(isinstance(article_id, str) and article_id for article_id in article_ids)
            or len(set(article_ids)) != len(article_ids)):
        raise ValueError("profile article_ids count mismatch or duplicates")
    offset = (page - 1) * per_page
    if total and offset >= total:
        raise ValueError("requested result page starts beyond observed total")
    expected_hits = min(per_page, max(0, total - offset))
    if len(hits) != expected_hits:
        raise ValueError(f"result hit count mismatch: expected {expected_hits}, found {len(hits)}")
    output_hits = []
    seen_ids, seen_urls = set(), set()
    for hit_ref in hits:
        hit = reader.object(hit_ref)
        hit_id = field(hit, "id")
        if not isinstance(hit_id, str) or hit_id not in article_ids:
            raise ValueError("returned hit ID is missing or absent from profile article_ids")
        if hit_id in seen_ids:
            raise ValueError("duplicate returned hit ID")
        seen_ids.add(hit_id)
        titles_raw = field(hit, "titles")
        if not isinstance(titles_raw, dict):
            raise ValueError("returned hit is missing a complete title")
        titles = {lang: reader.scalar(ref) for lang, ref in titles_raw.items()}
        if not any(isinstance(t, str) and t.strip() for t in titles.values()):
            raise ValueError("returned hit is missing a complete title")
        url = validate_article_url(field(hit, "article_url"))
        if url in seen_urls:
            raise ValueError("duplicate returned article URL")
        seen_urls.add(url)
        output_hits.append({"id": hit_id, "titles": titles, "article_url": url})
    returned_count = len(seen_ids)
    complete = returned_count == total
    return {"profile": {"id": profile_id, "full_names": full_names, "orcid": field(profile, "orcid", required=False)},
            "expected_count": expected_count, "profile_count": profile_count, "result_total": total,
            "page": page, "per_page": per_page, "hits": output_hits,
            "complete_profile": complete, "remaining_count": max(0, total - returned_count)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="observed ThaiJO author profile URL")
    parser.add_argument("--author-name", action="append", required=True, help="verified profile alias; repeatable")
    parser.add_argument("--expected-count", type=int, required=True, help="count observed in the ThaiJO UI")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--urls-output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.resolve() == args.urls_output.resolve():
        parser.error("--output and --urls-output must be different files")
    try:
        raw = fetch_html(args.profile)
        result = collect(parse_payload(raw), args.profile, args.author_name, args.expected_count)
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.urls_output.parent.mkdir(parents=True, exist_ok=True)
    args.urls_output.write_text("".join(hit["article_url"] + "\n" for hit in result["hits"]), encoding="utf-8")
    print(json.dumps({"profile_id": result["profile"]["id"], "profile_count": result["profile_count"],
                      "result_total": result["result_total"], "page": result["page"],
                      "per_page": result["per_page"], "returned": len(result["hits"]),
                      "complete_profile": result["complete_profile"],
                      "remaining_count": result["remaining_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
