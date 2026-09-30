# Collect and verify

## Identity and search

Use name variants observed in official profiles/articles, not invented transliterations. If only a Thai name is known, find the English form in ThaiJO or an institutional profile first. Compare full name, affiliation, coauthors and sample topics; request clarification only for unresolved candidates.

- ThaiJO: [Author Search](https://www.tci-thaijo.org/en/authors), Thai full name → evidenced English full name. Try reversed name/surname/observed variants when the full-name search fails or coverage is uncertain. English zero results does not exclude a Thai profile. Exclude other people sharing the surname. Check every publications page and collect direct `Open Original Article` URLs; note duplicates and excluded records against the displayed count.
- Scopus: [Author Search](https://www.scopus.com/pages/search/authors), surname + full first name → surname + initial → affiliation if needed. Confirm Author ID, affiliation and variants. Once confirmed, inspect Documents and plausible split profiles; do not exhaust a fixed list of redundant queries. Never combine split profiles without identity evidence. The CSV importer accepts one target Author ID per invocation; preserve separate imports and reconcile verified profiles before combining.
- Existing tabs may belong to someone else. Compare the AU-ID with the verified target before using any documents. Existing reports must also identify this person. ORCID is optional and must be observed, not inferred from coauthors.

Record actual query, candidate/result count, filters, date and pages checked. Missing access/unknown count is **unknown**, not a query returning zero. An unavailable profile metric stays blank with a reason.

## Scopus collection

Use the verified browser session and documented controls, following [export instructions](scopus-export-computer-use.md). Export all document types unless the user limits scope; label types rather than silently dropping conferences/reviews. Read h-index and its check date from the author profile/search evidence, and save the evidence URL. CSV import checks target Author ID for every row, complete authors, EID and counts. Do not manually retype rows available in the CSV. Only inspect individual records for missing/ambiguous data.

## ThaiJO metadata and Tier

Start with [fast collection](fast-collection.md). For pages/links still missing, use the browser's documented DOM/locator tools for public rendered UI. Inspect each profile page and collect its actual card names and anchor hrefs. Resolve observed detail links with the helper; if it cannot parse a page, open that observed card and read `Open Original Article`, then verify return to the same profile page. Pagination is asynchronous: verify its active page/range and changed card list, not a common title such as `From Editor`. After one validated cycle, repeat in bounded batches (up to 5 cards per call), returning card title + original URL + failures. Missing detail/link or duplicate from another page → **stop the batch immediately**, save verified prior items, re-inspect. Never continue with stale indices or fabricate URL patterns. Use documented locator `waitFor` for readiness instead of counting snapshots. Checkpoint after each batch and reconcile unique URLs with the displayed total. The helper parses public server-rendered JSON only; do not inspect unrelated hidden browser state or guess endpoints. If DOM tools are unavailable, use fresh accessibility state with the same assertions.

Run `collect_thaijo.py` on observed article URLs. Resolve `errors` and check authors before importing the draft. Read publication year from `citation_date` or the article's linked issue, converting verified Buddhist Era years to CE. Use article `citation_volume`, `citation_issue`, `issue_url`. Never apply `current_issue_title` to an older article.

Author profiles can include editorials (`From Editor`) and other contributions. Confirm `document_type` from the source; do not label every entry a research article. Leave an unverified type blank with a note. If the user's scope excludes a type, record each exclusion and reconcile counts; profile totals alone are not research-paper totals.

If the basic CUA `Target` documentation omits DOM methods, check its selected-browser documentation before concluding they are unavailable. When that documentation exposes `tab.playwright`, an observed detail-page link can be awaited/read without another full snapshot:

```javascript
const original = tab.playwright.getByRole('link', {name:'Open Original Article', exact:true});
await original.waitFor({state:'visible', timeoutMs:10000});
const href = await original.getAttribute('href');
```

This is **ThaiJO only**. Validate the detail identity/page transition before recording `href`; on any failure stop, do not read a previous article's link.

For a pagination button whose observed DOM uses `aria-current="true"`, wait for the active attribute instead of immediately reading it and clicking again:

```javascript
await pageButton.click({timeoutMs:5000});
await pageButton.and(tab.playwright.locator('[aria-current="true"]')).waitFor({state:'visible', timeoutMs:10000});
```

Then wait for a card known to occur on the target page **and absent from the previous page**, or confirm the complete card-list fingerprint changed. A repeated editorial title/date is not such a marker. After return/navigation, wait for profile heading and pagination controls before repeating the cycle.

After reload/hydration, publication labels can change language. If a text marker times out, inspect the actual active page/range and fresh card labels before calling pagination broken. Refresh locators from observed labels; do not click an already active page or keep retrying a stale-language marker. Preserve any items collected before the timeout.

If the first click is ignored during page hydration, a timed-out active-state wait plus fresh evidence of the same profile and inactive target button permits **one** click retry. Recheck readiness; a second failure stops the batch. Never retry after it is already active.

For unresolved Tier follow [tier-evidence.md](tier-evidence.md). Collect publisher text, linked documents and badges once per journal; review publication-year evidence separately from current status. A current badge does not finish the historical lookup.

## CiteScore Q

Use the missing-metric queue, then [Scopus Sources](https://www.scopus.com/sources) through Computer Use. Search ISSN/journal once, select the publication year, and read the CiteScore rank **subject and percentile**. Do not use SJR/SNIP as CiteScore Q or choose the highest category for appearance. Select a relevant evidenced subject for each article. Record source URL, year and subject. Scripts map percentile: >=75 Q1, >=50 Q2, >=25 Q3, otherwise Q4.

Use the default **CiteScore** tab and its three-column Category / Rank / Percentile table. Do not open **CiteScore rank & trend** for this task: that separate panel loads a long cross-journal ranking table and its year heading can change before its rows. The default table already contains all categories of this journal.

Year changes are asynchronous. An immediate snapshot can have a new dropdown value but the previous year’s rank table. Explicitly await the **exact rank heading**, then read the table; do not merely claim that a wait happened. The summary card above can remain at the latest year and is not the historical rank year.

```javascript
// After selecting the observed year option:
await tab.playwright.getByRole('heading', {
  name: `CiteScore rank ${targetYear}`, exact: true
}).waitFor({state:'visible', timeoutMs:10000});
// If the observed page has a Loading... indicator, wait for it to disappear.
await tab.playwright.getByText('Loading...', {exact:true})
  .filter({visible:true}).waitFor({state:'hidden', timeoutMs:10000});
const rankYear = await tab.playwright.getByRole('heading', {
  name: `CiteScore rank ${targetYear}`, exact: true
}).innerText();
const rows = await tab.playwright.getByRole('table').filter({visible:true})
  .getByRole('row').all();
// Read each rendered row intact; do not pair the first percentile with another category.
const evidence = {source_url:await tab.url(), rank_heading:rankYear, rows:[]};
for (const row of rows) evidence.rows.push(await row.innerText());
nodeRepl.write(evidence);
```

Save that compact JSON unchanged, then validate and normalize it offline:

```
python3 scripts/parse_citescore_table.py --input observed-table.json --year TARGET_YEAR --output metric-evidence/SOURCE-YEAR.json
```

This rejects an old rank year and preserves category/percentile pairs. Keep parsed captures in a dedicated metric-evidence directory. Select the relevant category object intact from its output when filling report fields; never independently retype the subject and percentile. Preserve the raw capture as evidence. The helper cannot prove that supplied text is authentic, that the source matches the journal/ISSN, or that a category is relevant; verify those in the browser/article context.

Use locators only after confirming those controls in the current DOM. Capture source URL, actual rank heading, and intact category/rank/percentile rows together. Copy parent/child category labels verbatim; do not reconstruct taxonomy from memory. A percentile under Hardware and Architecture cannot be relabeled Software. Select an evidenced row and explain its relevance to the article. If year/table readiness fails, leave Q blank with the actual failed check. Never infer historical unavailability from an old table still loading. Remove superseded missing-Q notes only when evidence resolves that gap; retain unrelated review warnings.

Process up to five source/year groups per batch. After each batch, write a compact audit file with one record per group: source URL, requested/observed year, selected category/rank/percentile, and status (evidenced, unavailable with observed reason, or pending). Conversation updates alone are not a durable checkpoint. Continue subsequent batches until no required groups remain pending or a documented site-wide blocker prevents progress. Completing a batch or exporting a workbook does not complete the remaining queue. Before final export, compare the exact set of (ISSN, publication_year) keys against the original queue; equal counts alone can hide a missing group and an incorrect replacement. Keep requested publication year separate from observed metric year: a 2026 paper using 2025 metrics remains the 2026 queue group. Pass the expected metric year to the evidence parser and explain an allowed substitution in the record notes.

For a current-year paper only, use the latest completed previous year and explain that substitution in notes. Unavailable historical year → blank Q with reason. Reviews can have journal Q; conference papers do not by default. A visible Book Series source is not automatically a journal because its CSV document type says Article; preserve that type, note the observed source type, and leave journal Q unassigned by default. Preflight eligibility counts use CSV document type, so disclose such source-type exceptions separately. Cache reuse requires the same ISSN, journal, year and explicitly selected subject. A cache cannot decide the subject for a new article.
