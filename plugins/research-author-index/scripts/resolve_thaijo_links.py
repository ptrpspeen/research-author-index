#!/usr/bin/env python3
"""Resolve observed ThaiJO detail pages to their public original article URLs."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 2_000_000
TIMEOUT_SECONDS = 20
_DETAIL_PATH = re.compile(r"^/en/articles/[A-Za-z0-9_-]+-\d+/?$")
_ARTICLE_PATH = re.compile(r"^/(?:[^?#]*/)?article/view/\d+$")


def allowed_host(host: str | None) -> bool:
    return bool(host and (host == "tci-thaijo.org" or host.endswith(".tci-thaijo.org")))


def validate_detail_url(value: str) -> tuple[str, str]:
    """Return (canonical input URL, host), rejecting anything outside observed detail pages."""
    try:
        parsed = urlparse(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("malformed detail URL") from exc
    if (parsed.scheme != "https" or host not in ("tci-thaijo.org", "www.tci-thaijo.org") or parsed.username is not None
            or parsed.password is not None or port not in (None, 443)
            or not _DETAIL_PATH.fullmatch(parsed.path) or parsed.query or parsed.fragment):
        raise ValueError("expected a direct HTTPS ThaiJO /en/articles/<slug>-<id> URL")
    return value, host or ""


class OriginalLinkParser(HTMLParser):
    """Collect direct landing links attached to the visible original-article label."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._anchor_href = dict(attrs).get("href")
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href is not None:
            visible = " ".join(" ".join(self._anchor_text).split())
            if visible in ("Open Original Article", "open_in_new Open Original Article", "Open Original Article open_in_new"):
                self.links.append(self._anchor_href)
            self._anchor_href = None
            self._anchor_text = []


def validate_article_url(href: str, detail_url: str) -> str | None:
    candidate = urljoin(detail_url, href)
    try:
        parsed = urlparse(candidate)
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme != "https" or not allowed_host(parsed.hostname)
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443) or not _ARTICLE_PATH.fullmatch(parsed.path)
            or parsed.query or parsed.fragment):
        return None
    return candidate


class DetailRedirectHandler(HTTPRedirectHandler):
    """Allow redirects only within the requested host's ThaiJO detail-page area."""

    def __init__(self, original_host: str, original_path: str) -> None:
        super().__init__()
        self.original_host = original_host
        self.original_path = original_path

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            parsed = urlparse(newurl)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("redirected to malformed URL") from exc
        if (parsed.scheme != "https" or parsed.hostname != self.original_host
                or not allowed_host(parsed.hostname) or port not in (None, 443)
                or parsed.username is not None or parsed.password is not None
                or not _DETAIL_PATH.fullmatch(parsed.path) or parsed.query or parsed.fragment):
            raise ValueError("redirect left the allowed ThaiJO detail-page host/path")
        if parsed.path.rstrip("/") != self.original_path.rstrip("/"):
            raise ValueError("redirect changed the requested article identity")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_html(detail_url: str, opener_factory=build_opener) -> bytes:
    canonical, host = validate_detail_url(detail_url)
    opener = opener_factory(DetailRedirectHandler(host, urlparse(canonical).path))
    request = Request(canonical, headers={"User-Agent": "ResearchAuthorIndex/0.1 (public link resolver)"})
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            final, final_host = validate_detail_url(response.url)
            if final_host != host:
                raise ValueError("redirect changed ThaiJO detail host")
            if urlparse(final).path.rstrip("/") != urlparse(canonical).path.rstrip("/"):
                raise ValueError("response changed the requested article identity")
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("detail page exceeds 2 MB")
            return raw
    except HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise ValueError(f"request failed: {exc.reason}") from exc


def resolve_one(detail_url: str, fetcher=fetch_html) -> dict[str, str]:
    canonical, _ = validate_detail_url(detail_url)
    raw = fetcher(canonical)
    parser = OriginalLinkParser()
    parser.feed(raw.decode("utf-8", "strict"))
    candidates = {url for href in parser.links
                  if (url := validate_article_url(href, canonical)) is not None}
    if len(candidates) != 1:
        raise ValueError(f"expected exactly one unique direct original article URL; found {len(candidates)}")
    return {"detail_url": canonical, "article_url": next(iter(candidates))}


def load_urls(path: Path, expected_count: int) -> list[str]:
    urls = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    if len(urls) != expected_count:
        raise ValueError(f"expected {expected_count} input URLs; found {len(urls)}")
    if len(urls) != len(set(urls)):
        raise ValueError("duplicate input detail URLs")
    for url in urls:
        validate_detail_url(url)
    return urls


def resolve_all(urls: list[str], workers: int, fetcher=fetch_html) -> tuple[list[dict], list[dict]]:
    if not 1 <= workers <= 4:
        raise ValueError("--workers must be between 1 and 4")
    mappings: list[dict] = []
    errors: list[dict] = []
    # executor.map preserves input order; requests have bounded timeout and response size.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(resolve_one, url, fetcher) for url in urls]
        for url, future in zip(urls, futures):
            try:
                mappings.append(future.result())
            except Exception as exc:
                errors.append({"detail_url": url, "error": str(exc)})
    targets: dict[str, list[str]] = {}
    for mapping in mappings:
        targets.setdefault(mapping["article_url"], []).append(mapping["detail_url"])
    for article_url, details in targets.items():
        if len(details) > 1:
            errors.append({"detail_url": details[1],
                           "error": f"duplicate resolved article URL shared by {len(details)} detail pages: {article_url}"})
    return mappings, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urls", type=Path, required=True, help="UTF-8 list of observed ThaiJO detail URLs")
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.urls.resolve() == args.output.resolve():
        parser.error("--urls and --output must be different files")
    if args.expected_count < 0:
        parser.error("--expected-count must be nonnegative")
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")
    started = time.monotonic()
    try:
        urls = load_urls(args.urls, args.expected_count)
        mappings, errors = resolve_all(urls, args.workers)
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    result = {
        "expected_count": args.expected_count,
        "input_count": len(urls),
        "unique_input_count": len(set(urls)),
        "output_count": len(mappings),
        "unique_output_count": len({row["article_url"] for row in mappings}),
        "mappings": mappings,
        "errors": errors,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in
                      ("expected_count", "input_count", "unique_input_count", "output_count",
                       "unique_output_count", "error_count", "elapsed_seconds")
                      if key != "error_count"} | {"error_count": len(errors)}, ensure_ascii=False))
    return 1 if errors or len(mappings) != args.expected_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
