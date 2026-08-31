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
python run_pipeline.py           # defaults to pharma
python run_pipeline.py semiconductor
```

Each invocation runs one segment's phases in order: connectors -> baseline ->
Policy Agent -> Filing Agent -> graph -> alerts, then **always** rebuilds the
dashboard from every segment that has data on disk (not just the one just
run), then runs Phase 6 eval only if that segment has a golden test set
(`eval/golden_events_<segment>.yaml` — pharma has one, semiconductor doesn't
yet, so its Phase 6 is skipped, not faked). Run both commands above, in
either order, to get the full two-segment dashboard; open `dist/index.html`
in a browser afterward — its Segment dropdown switches between them.

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
python -m eval.run_eval pharma                    # Phase 6  — baseline vs. advanced eval (pharma only)
```

## Expected output

### pharma
- `data/pharma/policy_events.json` — ~12 structured PolicyEvents (from ~66
  unique raw items reviewed — most raw items are filtered out as irrelevant
  noise, which is expected).
- `data/pharma/filing_mentions.json` — ~24 structured FilingMentions (from 8
  companies' 10-Ks; extraction recognizes both sourcing dependencies and
  market/export dependencies — see CHANGELOG.md).
- `data/pharma/graph_links.json` — ~12 links (via shared country: Ireland,
  Germany, Switzerland at this data scope — Germany is fed by two distinct
  policy catalysts, an EU-wide tariff framework and a Germany-specific
  Section 301 probe, resolved via `EU_MEMBERS` bloc matching in
  `src/graph.py`).
- `data/pharma/alert_cards.json` — ~12 Alert Cards, each citing both a policy
  source URL and a filing source URL.
- `eval/eval_results_pharma.json` + console table — baseline ~25% vs.
  advanced 100% accuracy on the 8 golden cases (baseline's exact number can
  vary a few points run-to-run since it's unstructured LLM prose being
  judged by another LLM call; the advanced pipeline's score is deterministic
  because it's read directly from the structured graph, not judged).

### semiconductor
- `data/semiconductor/policy_events.json` — ~22 structured PolicyEvents (US
  export-control policy toward China is the dominant real signal here, not
  tariffs — see `edgar_priority_terms` in `config/segments/semiconductor.yaml`).
- `data/semiconductor/filing_mentions.json` — ~32 structured FilingMentions
  across 6 of 8 companies (2 correctly yield zero — their cached excerpts
  were too generic).
- `data/semiconductor/graph_links.json` — ~35 links, almost entirely China,
  reflecting how concentrated real 2025-2026 semiconductor policy actually is.
- `data/semiconductor/alert_cards.json` — ~34 Alert Cards.
- No `eval/golden_events_semiconductor.yaml` yet — Phase 6 is skipped for
  this segment, by design (see README "Result").

### dashboard (both segments)
- `dist/index.html` — an interactive, client-side-rendered dependency graph
  (hover/click to trace a company's path back to its catalyst; segment,
  time-range, and detail-level controls, clickable stat tiles that jump to
  and expand their section), Alert Cards (sortable by policy-event date),
  and a Gap/Opportunity section — Gaps (FilingMentions with no matching
  PolicyEvent, grouped by company) and Opportunities (PolicyEvents with no
  matching FilingMention, grouped by country). Every segment's data is
  embedded in the same page; the Segment dropdown filters client-side, so no
  separate build per segment is needed.
- `dist/glossary.html` — term definitions for everything on the dashboard.

## Approximate runtime / cost

Per segment:
- Connectors (from cache): instant. From scratch: ~2-3 min (EDGAR fetches 8
  full 10-K documents, several MB each; Federal Register fallback is fast).
- Baseline: 1 LLM call, ~20s.
- Policy Agent: 4 LLM calls (batched), ~1 min.
- Filing Agent: 8 LLM calls (one per company), ~1 min.
- Alerts: 1 LLM call per graph link (~12 for pharma, ~35 for semiconductor),
  ~30s-3 min.
- Eval (pharma only): 8 LLM judge calls, ~30s.
- **Total per segment from a warm cache: ~5-8 minutes, ~30-55 Anthropic API
  calls (`claude-sonnet-5`), well under $1.**
