# Scopus: UI export and bounded recovery

Use the user's browser with accessibility/screenshot controls or its documented Playwright DOM/locators and downloads. No private endpoint calls, network interception or copying login state. First complete the mandatory visible Scopus/login step in [SKILL.md](../SKILL.md), using connected Chrome or Codex Browser as specified there. Discover surfaces once when necessary, then reuse that verified browser/tab.

Before exporting, read the selected browser's API documentation once. Basic accessibility/Target documentation may omit its Playwright download methods; absence there does not establish that capture is unavailable. Reuse the selected browser binding when requesting its documentation. Concurrent researcher runs must use separate owned tabs and record their own export job/filename.

1. On Documents confirm the observed target `AU-ID(...)`, result count **N**, filters and page range. A foreign AU-ID must not be reused. If zero, verify profile/filters before accepting zero.
2. Read selection state **before clicking**. Checked/`Value:1` → do not toggle it. Otherwise select the whole result set using the visible `All` → `Select all` option (not `Select this page`). Read new state after changes; use only indices from the latest state.
3. Open Export → CSV. The modal heading `Export N documents to CSV` proves the actual selection count. If smaller than intended, close and fix selection before exporting.
4. Select unchecked `Citation information` and `Serial identifiers (e.g. ISSN)`. Verify the output includes Author full names, Author(s) ID, Title, Year, Source title, Cited by, DOI, Link, ISSN, Document Type, Publication Stage and EID. Never toggle already checked fields.
5. Export once. Check download status or the existing job in Exports Dashboard; an in-progress job is not failure. Do other work while queued; don't create duplicate jobs. For an existing completed job, read its current Download CSV control and capture that download as below.
6. Preserve the captured file, verify timestamp/headers and import it with `--expected-count N`. Preserve all page CSVs if exported in batches. Exact totals plus unique EIDs must match the scope before claiming completeness. A downloaded file still needs importer validation.

## Capture the download

When the current browser documentation exposes `tab.playwright.waitForEvent("download")`, start the wait **before** clicking the observed download control. Use the actual accessible name from the current DOM, scoped to the matching job when multiple jobs exist. The tested dashboard name was `Download CSV Download`; names may change. Example with an already verified `downloadButton` locator:

```javascript
const pending = tab.playwright.waitForEvent('download', {timeoutMs:20000});
await downloadButton.click({timeoutMs:10000});
const file = await pending;
const path = await file.path({timeoutMs:20000});
```

Copy the returned local path into the workspace and validate the CSV; never print signed download URLs or tokens. If a first Export action downloads immediately, arm the wait before that action too. When the job is queued, a download timeout alone does not mean generation failed: inspect the existing dashboard job. Do not re-export to recover a download. If this API is unavailable, use the normal download UI and locate the exact observed filename.

The newest file in shared Downloads may belong to another researcher. Match the returned path or exact observed job filename/ID to this export, then validate Author ID, EIDs and modal count. Count alone cannot distinguish jobs with equal sizes. Do not replace a missing export with a coauthor's CSV. Current CSV links may use `/inward/record.uri?eid=...`; the importer checks the exact EID and canonicalizes them without editing the raw CSV.

## Recovery

- Unclear/stale checkbox: refresh state, inspect a screenshot for overlays, dismiss them and retry the observed selection once. If whole-set selection fails, increase Display and export each page using `Select this page`; record page ranges, modal counts and filenames.
- Profile/Documents redirects: recheck login first; if absent/uncertain, return to the mandatory login gate and pause. Once login is verified, retain the observed Author ID and count, and try visible document/advanced-search UI with `AU-ID(ID)` once. Do not invent a deep URL or repeatedly reopen a redirect loop. If query UI is still inaccessible, record the URL/error and continue ThaiJO.
- State says disabled but screenshot disagrees: use the current screenshot through Computer Use once, then verify result.
- Login/subscription/CAPTCHA: keep the required page visible and report the specific user action. Missing/uncertain login pauses the whole workflow under the mandatory gate; never bypass authentication or CAPTCHA. Verified login does not itself prove subscription access. A redirect/API error is not evidence of zero works.
- Preview or `Check access` with a signed-in account: connect institutional access using the visible UI. If Scopus then shows `Sign in`/`Personalize your experience`, ask the user to finish personal Elsevier sign-in and verify again; an institutional logo alone does not meet the login gate.
- `ERR_BLOCKED_BY_CLIENT` after normal download: record generation and download as separate outcomes. A supported download event on the same completed job may recover it; do not disable browser protections or expose/replay its signed URL. Stop after one relevant recovery if still blocked.
- Same failure after one relevant recovery **with login verified**: save URL, AU-ID, expected count, state/error and screenshot when useful. Mark Scopus incomplete, continue the other database, and identify the user action needed. Do not produce a complete-looking empty sheet. If normal UI exposes records, collect accessible metadata and label coverage; do not invent inaccessible fields.

Use state diffs, not full snapshots on every click. Batch independent field entry when UI is stable; never batch a selection toggle and Export without checking the intervening state/count.
