# Reproduction

## Requirements

- Python 3.11+ (built and tested on 3.12.4)
- An `ANTHROPIC_API_KEY` (required — every agent, the baseline, and the alert
  explainer make real LLM calls; there is no offline/mock LLM mode). No other
  API keys are needed: GDELT/Federal Register and SEC EDGAR are free and
  keyless, and every raw pull from them is already committed under
  `data/cache/`.

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
python run_pipeline.py
```

This runs all phases in order: connectors -> baseline -> Policy Agent ->
Filing Agent -> graph -> alerts -> dashboard -> eval. Then open
`dist/index.html` in a browser.

**Every phase is idempotent and cache-checked**: if `data/cache/...` or a
phase's output file (`data/policy_events.json`, `data/filing_mentions.json`,
`data/graph_links.json`, `data/alert_cards.json`, `data/baseline_output.json`)
already exists, that phase reuses it instead of re-pulling or re-calling the
LLM. On a fresh clone with the committed `data/` and `data/cache/` intact,
a full `python run_pipeline.py` run therefore makes **zero calls to
GDELT/Federal Register/SEC** and reproduces the exact same structured outputs
— only the two free-text LLM steps whose prompts include instructions to
write fresh prose (the baseline, and the alert explainer's phrasing) can
vary slightly token-for-token across reruns, though not in the facts/links
they report, if you delete their output files and force a redo.

To force any single phase to redo its work from scratch (e.g. to verify the
network pulls / LLM calls actually work, not just that caching works):

```bash
# delete just that phase's output, then rerun run_pipeline.py, e.g.:
rm data/policy_events.json      # forces Policy Agent to re-run
rm -rf data/cache/policy_raw    # forces the GDELT/Federal Register pull to re-run
```

## Run phases individually

```bash
python -m src.connectors.gdelt      # Phase 0a — policy/news pull
python -m src.connectors.edgar      # Phase 0b — SEC filing pull
python -m src.baseline              # Phase 1  — baseline summarizer
python -m src.agents.policy_agent   # Phase 2  — Policy Agent
python -m src.agents.filing_agent   # Phase 3  — Filing Agent
python -m src.graph                 # Phase 4a — causal graph
python -m src.alerts                # Phase 4b — Alert Cards
python -m src.dashboard             # Phase 5  — static dashboard
python -m eval.run_eval             # Phase 6  — baseline vs. advanced eval
```

## Expected output

- `data/policy_events.json` — ~12 structured PolicyEvents (from ~66 unique
  raw items reviewed — most raw items are filtered out as irrelevant noise,
  which is expected).
- `data/filing_mentions.json` — ~18 structured FilingMentions (from 8
  companies' 10-Ks; 2 of the 8 companies correctly yield zero mentions
  because their cached excerpts were too generic to support a real claim).
- `data/graph_links.json` — ~6 links (all via shared country at this data
  scope: Ireland and Germany).
- `data/alert_cards.json` — 6 Alert Cards, each citing both a policy source
  URL and a filing source URL.
- `dist/index.html` — the dashboard.
- `eval/eval_results.json` + console table — baseline ~25% vs. advanced 100%
  accuracy on the 8 golden cases (baseline's exact number can vary a few
  points run-to-run since it's unstructured LLM prose being judged by another
  LLM call; the advanced pipeline's score is deterministic because it's
  read directly from the structured graph, not judged).

## Approximate runtime / cost

- Connectors (from cache): instant. From scratch: ~2-3 min (EDGAR fetches 8
  full 10-K documents, several MB each; Federal Register fallback is fast).
- Baseline: 1 LLM call, ~20s.
- Policy Agent: 4 LLM calls (batched), ~1 min.
- Filing Agent: 8 LLM calls (one per company), ~1 min.
- Alerts: 6 LLM calls (one per graph link), ~30s.
- Eval: 8 LLM judge calls, ~30s.
- **Total from a warm cache: ~5 minutes, ~30 Anthropic API calls
  (`claude-sonnet-5`), well under $1.**
