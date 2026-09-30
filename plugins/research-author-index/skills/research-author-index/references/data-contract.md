# JSON contract

Top-level: `researcher:{name,affiliation?,orcid?}`, `retrieved_at:"YYYY-MM-DD"`, `scopus:[]`, `tci:[]`, `audit:{}`. One person per file. Prefer the importer to hand-building rows. `export_excel.py --init --name "TARGET" --output data.json` creates a blank draft, not a previous populated report.

Required for every row: `title`, `publication_year` (CE integer), `document_type`, `authors` (full-name array), `authors_complete` (boolean), `journal`, `article_url`. Use `verification_status:"confirmed"` only after identity/content checks, otherwise `needs_review`. Optional: `issn`, `doi`, `notes`. Omit unknown optional values; do not invent defaults.

| Database | Fields |
|---|---|
| Scopus | `scopus_eid`, `scopus_author_id`, `author_profile_url`, `author_h_index`, `h_index_as_of`, `citations`, `citations_as_of` |
| Q | `citescore_percentile` (integer 0–100), `quartile` (Q1–Q4), `quartile_year`, `quartile_subject`, `quartile_source_url` |
| TCI | `volume`, `issue`, `issue_title`, `issue_url`, `tier` (Tier 1–3), `tier_period`, `tier_source_url`, `tier_evidence_basis`, `current_tier`, `current_tier_checked_at`, `current_tier_source_url` |

Q must match publication year; the current year may use the previous completed year with explanatory notes. Q conversion is automatic and checked against an explicitly provided quartile. Select the relevant subject; never copy across subjects. Historical Tier requires an observed range covering the publication year. `tier_evidence_basis` is `explicit_period` or `publisher_since` (legacy reports may omit it). A continuous publisher since statement is bounded to its observation year and labeled `START – OBSERVATION_YEAR (publisher states since; observed YYYY-MM-DD; no certified expiry)`. A check date alone cannot establish history. Current-only evidence fills the three `current_tier*` fields and leaves historical `tier` blank. See [tier-evidence.md](tier-evidence.md) for captured quotes and review rules.

h-index needs a profile URL/date; citations need a check date. ORCID must pass its checksum and have identity evidence. Unknown count is null, not 0. Authors omitted by an ellipsis are incomplete and require `needs_review`.

Scopus article URLs must be direct `/pages/publications/ID`, `/record/display.uri?eid=EID` or exported `/inward/record.uri?eid=EID` with an **exact** EID match; profiles must exactly match Author ID. The importer canonicalizes supported CSV URLs and leaves the raw file untouched. ThaiJO URLs must be direct `/article/view/`; issue URLs must be from the same journal. Q sources must be Scopus. Tier sources must be TCI or a ThaiJO page/badge for that journal, including About/announcements. Review exact text or open image/PDF evidence; a URL alone is insufficient. `audit.tier_evidence` preserves captured document URLs, quotes, observation dates and claim scope.

## Audit

`audit.searches` entries: `database:"scopus"|"tci"`, `query`, `results` (observed integer), `method`, `pages_checked`, `filters`, `checked_at:"YYYY-MM-DD"`. Log only actual searches. Unknown counts/access failures belong in `audit.blockers` (freeform objects with database, URL, error, date); do not encode them as 0 results. Log skipped query variants with reasons separately in `audit.skipped_searches`.

`audit.<database>_expected_count` is the observed scoped result count, not the imported row count used as a substitute. If exclusions exist, set `<database>_excluded_count` and list every item in `audit.exclusions`: `{database,identifier,reason}`. Exported rows + exclusions must equal the expected count.

The exporter rejects duplicate Scopus EID/URL and duplicate TCI DOI/URL within one sheet. Distinct Scopus EIDs sharing a DOI are retained as observed records, with a conflict warning and `needs_review` notes on every affected row; do not describe that count as unique works. Never use an ambiguous DOI to transfer cached fields between records. Repeated title+year+journal also produces a review warning, since distinct editorial issues can share a title. Do not delete such records without checking stable IDs/issues. Overlaps across databases remain. `reconcile_records.py` reports matches/review candidates without deleting. `verify_thaijo_links.py` compares every TCI URL to saved metadata, including authors, year, DOI and issue. These checks do not prove researcher identity or web collection completeness; retain the observed evidence. The Excel has exactly `Scopus` and `TCI` sheets, with hyperlinks and formula-safe cells.
