# Import, review and export

Run from the plugin root (scripts are not inside the skill folder). Use absolute workspace paths for outputs when cwd differs. Placeholders below must be replaced by observed values; omit unknown optional metrics.

## Import

Use previous JSON/XLSX only after checking its researcher metadata. JSON retains audit history; Excel cannot. If none matches, create a new report. Ask for a missing previous file only when the user explicitly requests an update.

New report:

```
python3 scripts/incremental_update.py --name "TARGET NAME" --affiliation "VERIFIED AFFILIATION" --scopus-csv scopus.csv --author-id OBSERVED_ID --expected-count OBSERVED_N --tci-draft thaijo-draft.json --tci-query "ACTUAL QUERY" --tci-pages-checked "ACTUAL PAGES" --tci-expected-count OBSERVED_TCI_N --output updated.json --changes changes.json
```

Add `--previous previous.json` or `previous.xlsx` for an update; keep `--name` consistent with its verified researcher. Add `--h-index`, `--orcid` only when observed. `--scopus-filters` records the actual filters; unknown filters must not be described as none. Use `--scopus-csv` repeatedly for page exports. You may omit a database's input, but then it is **not refreshed**, not zero. Fresh input must cover the complete scoped set. Do not export a partial final report without the user's acceptance.

`--orcid` accepts the observed bare identifier or its canonical `https://orcid.org/ID` URL; both are normalized and checksum-checked. Preserve raw Scopus CSV unchanged and let the importer normalize supported exported link forms.

Read stdout summary, then only relevant `changes.json` entries. EID→DOI and URL→DOI match records. Added ThaiJO rows and changed metadata require review. Missing old rows stop the import; inspect filters/pages/profile before `--accept-removed`. Never use that flag merely to make a command pass. Scopus CSV identifies the target author in each row; ThaiJO authors still need identity review.

Valid Q is kept for the same record/source/year; Tier only within its certification range. The importer already reuses valid cache entries: **do not extract/apply again**. New articles need an explicitly verified Q subject before reuse. Source/subject/period conflicts require evidence, not silent overwrites.

## Missing metrics and final checks

```
python3 scripts/metric_cache.py queue --input updated.json --output metric-queue.json
```

On an update add `--changes changes.json` to focus on new/changed rows; unchanged missing metrics still remain unresolved. Inspect only the queue. Query metrics only for collected records: no Scopus rows means no Scopus Q work, even if Sources is accessible. Verify new evidence per collection.md. If applying TCI badges, continue with `with-tier.json` as INPUT below.

A generated queue is still pending work. Attempt the required source/year/category checks and distinguish evidenced, unavailable after checking, and not yet attempted. Do not label an unattempted lookup as blocked or end the research run merely because record counts and workbook validation pass. A documented site-wide failure can justify stopping the affected queue without repeating the same failure for every row.

```
python3 scripts/reconcile_records.py --input INPUT --output matches.json
python3 scripts/verify_thaijo_links.py --input INPUT --metadata-draft thaijo-draft.json --output link-check.json
python3 scripts/export_excel.py --input INPUT --check --summary-only
```

Run independent checks together if the tools permit, but inspect every exit code. Skip the ThaiJO check only when there are no TCI rows. Otherwise use the matching saved metadata or `--live` to refresh public pages. Inspect matches needing review and full `--check` warnings when nonzero; resolve discrepancies or record missing evidence. No need to reopen all unchanged source pages.

After assigning Q, verify the final report against saved parsed captures (one source/year file in a dedicated directory). This catches batch updates that overwrite one category’s percentile with another value even when both map to the same Q:

```
python3 scripts/verify_citescore_evidence.py --input INPUT --evidence-dir metric-evidence
```

Every filled Q must match its source URL, metric year, exact subject, percentile and quartile. Keep/reuse the corresponding parsed captures for cached metrics; if unavailable, collect the missing evidence or leave the value unverified. Run this after the last report edit, before final export. Passing format checks alone does not verify Q evidence.

Use the preflight's exact metric counts in summaries. Q missing means missing among eligible Article/Review rows, not all blank Q cells: conference papers, editorials and books are separately not applicable by default. After any continuation, rebuild a compact final summary from the current preflight and metric audit. Keep one authoritative set of counts; replace obsolete pending/disputed claims instead of appending contradictory progress copies. Link the full report JSON rather than embedding all records again.

```
python3 scripts/export_excel.py --input INPUT --output report.xlsx
```

Verify sheets `Scopus`,`TCI`, row counts and direct hyperlinks. Missing Q/Tier after an attempted check may remain with its observed reason; pending checks keep the work unfinished, and identity ambiguity cannot pass. Deliver Excel plus JSON and explain counts, unresolved fields and any unrefreshed database. The script verifies structure and internal consistency, not the truth of web evidence.

The exporter refuses an empty Scopus sheet unless audit records a verified zero (expected count 0 plus an actual zero-result Scopus search). If Scopus is blocked, preserve the draft. Only after the user accepts that partial scope may you add `--allow-partial`; the workbook is then labeled partial. Never add this flag just to make export pass.
