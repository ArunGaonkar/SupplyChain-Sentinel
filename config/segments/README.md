# Segments

All five segments here — `pharma.yaml`, `semiconductor.yaml`, `textile.yaml`,
`automotive.yaml`, `steel_aluminum.yaml` — have real pipeline data behind
them (run `python run_pipeline.py <segment>`). None is a config-only stub in
this build. Adding another segment is just adding a new YAML file with the
same shape (countries / companies / commodities / policy_types / query
terms) and running the pipeline against it.

Building the four post-submission segments surfaced two real, generalizable
fixes (both documented in CHANGELOG.md):

- `src/connectors/edgar.py` originally hardcoded "tariffs"/"tariff" as the
  term searched and excerpted first, on the assumption that tariffs are
  always the central policy lever. Export controls matter as much as
  tariffs for semiconductors; now a per-segment config field
  (`edgar_priority_terms`), not a hardcoded assumption.
- `_search_best_filing`'s EDGAR full-text search can match ANY document in a
  10-K submission, including exhibits (equity-plan terms, subsidiary lists,
  financing agreements) that can outscore the actual 10-K body on a narrow
  term match — three of the eventual 40 company pulls across all five
  segments landed on an exhibit with zero operational content before this
  was caught and fixed to prefer the primary document.

Building textile also surfaced a data-pull lesson (not a code bug): the
first-pass GDELT/Federal Register query terms for a segment can be too
generic to surface the country-specific notices that actually matter (e.g.
"textile tariff" didn't surface Vietnam- or Bangladesh-specific notices,
even though Vietnam and Bangladesh are the dominant real sourcing countries
for the seed companies) — worth testing candidate query terms against the
Federal Register API directly before committing to a segment's config, the
same way the entity list itself should be sanity-checked.
