# Reproduction

## Requirements

- Python 3.11+ (built and tested on 3.12.4)
- An `ANTHROPIC_API_KEY` (required — every agent, the baseline, and the alert
  explainer make real LLM calls; there is no offline/mock LLM mode). No other
  API keys are needed: GDELT/Federal Register and SEC EDGAR are free and
  keyless, and every raw pull from them is already committed under
  `data/<segment>/cache/`.

## Setup (clean environment)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\pip install -r requirements.txt
# macOS/Linux:
.venv/bin/pip install -r requirements.txt
```

Create a `.env` file at the repo root (gitignored) containing:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Run everything

```bash
python run_pipeline.py                # defaults to pharma
python run_pipeline.py semiconductor
python run_pipeline.py textile
python run_pipeline.py automotive
python run_pipeline.py steel_aluminum
```

Each invocation runs one segment's phases in order: connectors -> baseline ->
Policy Agent -> Filing Agent -> graph -> alerts, then **always** rebuilds the
dashboard from every segment that has data on disk (not just the one just
run), then runs Phase 6 eval only if that segment has a golden test set
(`eval/golden_events_<segment>.yaml` — pharma and semiconductor have one,
textile/automotive/steel_aluminum don't yet, so their Phase 6 is skipped,
not faked). Run all five commands above, in any order, to get the full
five-segment dashboard; open `dist/index.html` in a browser afterward — its
Segment dropdown switches between them.

**Every phase is idempotent and cache-checked**: if a segment's
`data/<segment>/cache/...` or a phase's output file
(`data/<segment>/policy_events.json`, `filing_mentions.json`,
`graph_links.json`, `alert_cards.json`, `baseline_output.json`) already
exists, that phase reuses it instead of re-pulling or re-calling the LLM. On
a fresh clone with the committed `data/` intact, a full `python
run_pipeline.py <segment>` run therefore makes **zero calls to GDELT/Federal
Register/SEC** and reproduces the exact same structured outputs — only the
two free-text LLM steps whose prompts include instructions to write fresh
prose (the baseline, and the alert explainer's phrasing) can vary slightly
token-for-token across reruns, though not in the facts/links they report, if
you delete their output files and force a redo.

To force any single phase to redo its work from scratch (e.g. to verify the
network pulls / LLM calls actually work, not just that caching works):

```bash
# delete just that phase's output, then rerun run_pipeline.py <segment>, e.g.:
rm data/pharma/policy_events.json      # forces Policy Agent to re-run
rm -rf data/pharma/cache/policy_raw    # forces the GDELT/Federal Register pull to re-run
```

## Run phases individually

Every script below takes an optional segment argument (default `pharma`):

```bash
python -m src.connectors.gdelt semiconductor      # Phase 0a — policy/news pull
python -m src.connectors.edgar semiconductor      # Phase 0b — SEC filing pull
python -m src.baseline semiconductor              # Phase 1  — baseline summarizer
python -m src.agents.policy_agent semiconductor   # Phase 2  — Policy Agent
python -m src.agents.filing_agent semiconductor   # Phase 3  — Filing Agent
python -m src.graph semiconductor                 # Phase 4a — causal graph
python -m src.alerts semiconductor                # Phase 4b — Alert Cards
python -m src.dashboard                           # Phase 5  — dashboard (all segments, no argument)
python -m eval.run_eval pharma                    # Phase 6  — baseline vs. advanced eval (pharma, semiconductor)
python -m eval.run_eval semiconductor
```

## Expected output

Actual counts from the committed data (each segment: 8 seed companies, one
10-K each):

| segment | policy events | filing mentions | graph links | alert cards | golden cases | advanced vs. baseline |
|---|---|---|---|---|---|---|
| pharma | 12 | 29 | 12 | 12 | 10 | 100% vs. 10% |
| semiconductor | 22 | 49 | 49 | 49 | 9 | 100% vs. ~60-67% |
| textile | 20 | 37 | 8 | 8 | — | no golden set |
| automotive | 25 | 54 | 13 | 13 | — | no golden set |
| steel_aluminum | 21 | 35 | 32 | 32 | — | no golden set |

Notes on what shapes these numbers, per segment:
- **pharma**: links via shared country (Ireland, Germany, Switzerland,
  United Kingdom at this data scope) — Germany is fed by two distinct
  policy catalysts, an EU-wide tariff framework and a Germany-specific
  Section 301 probe, resolved via `EU_MEMBERS` bloc matching in
  `src/graph.py`. Filing extraction recognizes both sourcing and
  market/export dependencies (see CHANGELOG.md).
- **semiconductor**: almost entirely China — US export-control policy
  toward China is the dominant real signal here, not tariffs (see
  `edgar_priority_terms` in `config/segments/semiconductor.yaml`). 49
  graph links from 22 events × 49 mentions because 7 distinct China
  catalysts each independently match most of the same 7 companies.
- **textile**: lower link count than its event/mention totals suggest —
  the policy pull is more concentrated on China/Bangladesh/Haiti than the
  companies' Vietnam/Cambodia/India-heavy sourcing footprints (a real,
  documented data-pull gap — see CHANGELOG.md "textile" note, not a
  filtering failure).
- **eval**: baseline's exact number can vary a few points run-to-run since
  it's unstructured LLM prose being judged by another LLM call; the
  advanced pipeline's score is deterministic because it's read directly
  from the structured graph, not judged.

`dist/index.html` — an interactive, client-side-rendered dependency graph
(hover/click to trace a company's path back to its catalyst; segment,
time-range, and detail-level controls, clickable stat tiles and a side nav
that jump to and expand their section, a back-to-top button), Alert Cards
(sortable by policy-event date), and a Gap/Opportunity section — Gaps
(FilingMentions with no matching PolicyEvent, grouped by company) and
Opportunities (PolicyEvents with no matching FilingMention, grouped by
country). Every segment's data is embedded in the same page, with every
cross-referenced id segment-prefixed (see CHANGELOG.md — a real bug where
two segments legitimately pulled the same cross-industry government notice,
producing a genuine cross-segment id collision); the Segment dropdown
filters client-side, so no separate build per segment is needed.

`dist/glossary.html` — term definitions for everything on the dashboard.

## Approximate runtime / cost

Per segment:
- Connectors (from cache): instant. From scratch: ~2-3 min (EDGAR fetches 8
  full 10-K documents, several MB each; Federal Register fallback is fast).
- Baseline: 1 LLM call, ~20s.
- Policy Agent: 3-5 LLM calls (batched), ~1 min.
- Filing Agent: 8 LLM calls (one per company), ~1 min.
- Alerts: 1 LLM call per graph link (8-49 depending on the segment — see
  table above), ~30s-4 min.
- Eval (pharma, semiconductor only): 1 LLM judge call per golden case, ~30s.
- **Total per segment from a warm cache: ~5-10 minutes, ~15-65 Anthropic API
  calls (`claude-sonnet-5`) depending on the segment, well under $1.**
