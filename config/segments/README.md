# Segments

`pharma.yaml` and `semiconductor.yaml` have real pipeline data behind them
(run `python run_pipeline.py <segment>`). `textile.yaml` is intentionally
**not** included — it remains a config stub: adding one is just adding a
new YAML file with the same shape (countries / companies / commodities /
policy_types / query terms) and running the pipeline against it. See the
README's "Out of scope" section for why textile wasn't built.

Building semiconductor surfaced one real generalization: `src/connectors/
edgar.py` originally hardcoded "tariffs"/"tariff" as the term searched and
excerpted first, on the assumption that tariffs were always the central
policy lever. For semiconductors, export controls (the China Entity List,
license requirements on advanced chips) are at least as central as tariffs
— so that priority-term list is now a per-segment config field
(`edgar_priority_terms`), not a hardcoded assumption. See CHANGELOG.md.
