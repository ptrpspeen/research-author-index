# Changelog

## 0.1.7 — 2026-09-30

First GitHub release.

- Collect Tier evidence from observed journal links: About, indexing/history, announcements and relevant PDF/images, in addition to TCI badges.
- Save source captures, SHA-256 hashes, text excerpts, provenance and pending links for review.
- Require reviewed claims bound to captured text or visually inspected documents; validate journal identity, year bounds and conflicting Tier claims.
- Separate publication-year Tier from dated current Tier in Excel and JSON.
- Label continuous publisher “since” statements separately from explicit certification periods; never invent an expiry date.
- Preserve evidence basis through cache reuse, incremental updates and Excel round-trips; support legacy Excel Tier headers.
- Keep the mandatory visible Scopus login check, UI CSV Export workflow and CiteScore evidence validation.

Validation at release: 87 offline tests, 86 passed and one optional captured-profile fixture test skipped. A targeted Luna low offline forward test passed four evidence-application runs. This is not a claim of fully autonomous end-to-end research coverage.
