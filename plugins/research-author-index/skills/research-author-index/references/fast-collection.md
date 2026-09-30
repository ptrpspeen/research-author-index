# ThaiJO: public links in bounded script calls

Complete the visible Scopus login gate first. Verify the ThaiJO researcher, profile URL, names and displayed count in the browser. These helpers use standard-library HTTP on public ThaiJO pages; they do not require a browser session, API key or external scraping service.

## Profile links

Run once on the exact observed `/en/authors/...` URL. Pass a verified full name and the UI count:

```sh
python3 scripts/collect_thaijo_profile.py --profile OBSERVED_PROFILE_URL --author-name "VERIFIED FULL NAME" --expected-count N --output profile-links.json --urls-output profile-urls.txt
```

It parses public server-rendered JSON without executing JavaScript. Identity, totals, IDs, direct URLs and duplicates are checked. Read only its compact summary. `complete_profile:false` means more collection is required even with exit code 0. For example, 20 returned out of 53 leaves 33; a last-page payload of 13 alone is also incomplete. Never turn `article_ids` into invented detail URLs or guess pagination endpoints.

Save the returned IDs/URLs. Use the browser to gather the remaining pages' observed card hrefs, checking active page/range and a changed card list. Skip only IDs/URLs already saved. If the profile parser fails, preserve prior evidence and use the browser fallback in collection.md; do not repeatedly probe payloads or lower the expected count.

## Detail links

Put observed `/en/articles/...` card URLs in a UTF-8 text file, one per line, then resolve their `Open Original Article` links in one call:

```sh
python3 scripts/resolve_thaijo_links.py --urls detail-urls.txt --expected-count M --output resolved-links.json --workers 4
```

`M` is this input batch's observed count, not the whole profile count. The helper preserves input order, checks exact detail paths/labels and valid original landing URLs, caps concurrency/time/response size, saves partial successes, and exits nonzero on errors or duplicate targets. Read its summary/errors only. Recover failed items in the browser once; never treat a partial result as complete or silently deduplicate distinct records.

Merge direct URLs from the profile and resolved details, keeping their source IDs, page provenance and duplicate/exclusion reasons. Reconcile unique records against the observed full profile count before metadata collection. Then pass the merged landing URLs to `collect_thaijo.py` per SKILL.md. Public-page scraping does not replace per-article authors/year/type checks or historical Tier evidence.

Use only capabilities actually documented by the current runtime. API interception and Firecrawl are not part of this tested path; no saving or correctness claim applies to them.
