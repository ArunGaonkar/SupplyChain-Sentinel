# SupplyChain Sentinel — Pharma Trade & Tariff Causality Agent

Built for the **micro1 Frontier Engineering Challenge 2026** (hackathon, ~8h budget).
Coded with **[Claude Code](https://claude.com/claude-code)** (Anthropic's CLI coding agent) — see
[CHANGELOG.md](CHANGELOG.md) for the phase-by-phase build log and
[trajectories/](trajectories/) for real agent I/O logs captured during the build.

**Segments: pharma, semiconductor, textile, automotive, and steel/aluminum**
(the latter four added post-submission — see [CHANGELOG.md](CHANGELOG.md)).
All five have real pipeline data; the dashboard's Segment dropdown switches
between whichever segments have data on disk (see
[config/segments/README.md](config/segments/README.md) for adding another).

## The problem

**Who this is for:** portfolio managers, business people, and government policy
analysts tracking a supply chain — pharma originally (the hackathon's required
segment, and the one with a measured eval below), now also semiconductor,
textile, automotive, and steel/aluminum.

**The bottleneck:** tariff/policy news, SEC filings, and market signals about
a supply chain are scattered across sources. No one connects *"Country X
changes an import tariff"* to *"Company Y's 10-K already flagged this exact
dependency"* — so causal ripple effects are missed, or found too late, because
finding them requires reading both a government notice AND a company's risk
factors and noticing they're about the same country.

**What this builds:** a two-agent pipeline that reads policy/news events and
SEC filings, finds the causal links between them via a shared entity graph
(country + commodity), and produces cited, explainable **Alert Cards** — plus
a single-prompt **baseline** to prove the improvement is real, not asserted.

- **Portfolio managers** get alerts that cross-reference policy and filing
  evidence against real, cited causal drivers — instead of reading policy news
  and 10-Ks separately and hoping to notice the overlap themselves.
- **Business people** get the entity graph itself: sourcing dependencies
  (country/commodity pairs) that aren't obvious from either source alone.
- **Government policy analysts** get the same causal links read the other
  direction — "if this policy changes, here's who is exposed and why,"
  grounded in a company's own filing language, not speculation.

## Result (measured, not asserted)

Measured on pharma and semiconductor — the two segments with a hand-labeled
golden set. Textile, automotive, and steel/aluminum have real pipeline data
(see REPRODUCTION.md) but no golden set of their own yet, so
`run_pipeline.py <segment>` skips Phase 6 for them rather than fake a number.

| | Baseline (single prompt) | Advanced (this pipeline) | golden cases |
|---|---|---|---|
| **pharma** ([golden set](eval/golden_events_pharma.yaml)) | 10% (1/10) | **100% (10/10)** | 10 |
| **semiconductor** ([golden set](eval/golden_events_semiconductor.yaml)) | 67% (6/9) | **100% (9/9)** | 9 |

Neither run has a single case where the advanced pipeline is wrong and the
baseline is right — 0 regressions on both. Semiconductor's baseline scores
higher because US-China chip export controls are famous enough that a
single-prompt summarizer gets some of the "obvious" cases right on general
knowledge alone; pharma's tariff-driven country dependencies (Ireland,
Switzerland, Germany manufacturing sites) are specific enough that it
doesn't. Either way, the advanced pipeline never misses what baseline
catches, and correctly declines to fabricate a link in every precision test
case (a company with a real disclosed dependency, but no matching policy
event yet — see CHANGELOG.md for why that's a genuine data-coverage gap,
not a filtering bug).

Concretely for pharma: the baseline never once mentions **Ireland** anywhere
in its output — despite being given the exact same raw Federal Register
notice (US tariff cut on EU-origin generics, naming Ireland) and the exact
same companies' 10-K excerpts disclosing Irish manufacturing. It's not that
the information wasn't there; a single unstructured summarization pass just
doesn't reliably cross-reference two different sources at that level of
specificity. The advanced pipeline catches every Ireland link by
construction, because the graph step explicitly checks for shared
country/commodity — see [CHANGELOG.md](CHANGELOG.md) for the full breakdown
of both segments' results.

## Architecture

```
GDELT / Federal Register ──┐
                            ├─> src/connectors/*.py ─> data/<segment>/cache/*.json (raw, cached)
SEC EDGAR ──────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                      ▼
         src/agents/policy_agent.py            src/agents/filing_agent.py
         (raw news/notices -> PolicyEvent)      (raw filing excerpts -> FilingMention)
                    │                                      │
                    └──────────────┬───────────────────────┘
                                   ▼
                          src/graph.py (shared country/commodity -> GraphLink)
                                   ▼
                          src/alerts.py (LLM explains + cites each link -> AlertCard)
                                   ▼
                          src/dashboard.py (Jinja2 -> dist/index.html)

src/baseline.py: ONE direct LLM prompt over the same raw cached text, no
graph, no forced citations — the comparison point
(data/<segment>/baseline_output.json, frozen after Phase 1).

eval/run_eval.py: runs both against eval/golden_events_<segment>.yaml
(pharma, semiconductor).
```

See [REPRODUCTION.md](REPRODUCTION.md) to run it yourself from the committed
cache with zero network calls to GDELT/EDGAR (an `ANTHROPIC_API_KEY` is still
required for the agent/LLM steps themselves).

## Data sources

- **[GDELT DOC 2.0 API](https://api.gdeltproject.org/)** — free, no key. During
  this build its API host was unreachable (connection timeouts from multiple
  independent network paths, matching publicly reported GDELT infrastructure
  outages). `src/connectors/gdelt.py` tries it first and automatically falls
  back to the **[Federal Register API](https://www.federalregister.gov/developers/api/v1)**
  (also free, no key) for real US trade-policy notices. Both code paths are
  implemented — if GDELT is up when you run it, it's used. See CHANGELOG.md.
- **[SEC EDGAR full-text search](https://efts.sec.gov/LATEST/search-index)**
  and filing documents — free, no key, real 10-Ks for 8 seed companies in
  each of the 5 segments (40 filings total, mixed FY2023-2026 depending on
  each company's most recent relevant filing).
- No paid or rate-limited sources (X/Twitter, Reddit) are used.

## What's out of scope (by design, not oversight)

- ~~Textile, semiconductor, automotive, and steel/aluminum segments~~ — all
  four built post-submission with real data; see CHANGELOG.md. No segment
  remains a config-only stub in this build.
- **Market price data (yfinance) and social sentiment** — not pulled.
- **LangGraph or any orchestration framework** — plain Python (dicts) is
  sufficient at this scope; `src/graph.py` has no hidden state machine.
- **A full human-approval backend** (FastAPI + persistence) — the dashboard's
  per-alert checkbox (stored in the browser's `localStorage`, nothing server-
  side) is a stand-in for the human-approval principle: these Alert Cards only
  inform a human decision-maker and never take action themselves, so a full
  approval workflow is a natural next step, not required to prove the concept.
- **A what-if tariff simulator** — not built.
- ~~Gap/Opportunity view~~ — built post-submission (dashboard now has a Gap
  section listing disclosed dependencies with no matching policy event, e.g.
  Lilly's China-API admission from eval-08); see CHANGELOG.md.

## Repo layout

```
config/segments/*.yaml         entity types, seed countries/companies/commodities, one
                                per segment (pharma, semiconductor, textile, automotive,
                                steel_aluminum) — all the same shape
src/models.py                 pydantic schemas (PolicyEvent, FilingMention, GraphLink, AlertCard)
src/connectors/gdelt.py       policy/news pull (GDELT, falls back to Federal Register) + cache
src/connectors/edgar.py       SEC filing pull (full-text search + document fetch) + cache
src/baseline.py               THE baseline: one direct prompt, no structure
src/agents/policy_agent.py    Agent 1: raw policy items -> structured PolicyEvents
src/agents/filing_agent.py    Agent 2: raw filing excerpts -> structured FilingMentions
src/graph.py                  merges both agents' output into a causal graph
src/alerts.py                 graph -> cited, LLM-explained Alert Cards
src/dashboard.py              renders dist/index.html + dist/glossary.html (Jinja2, static, no backend);
                               loads every segment with data and merges them into one page for the
                               dashboard's client-side Segment dropdown
templates/dashboard.html.jinja  the dashboard template — interactive graph, Alert Cards, Gap/Opportunity
templates/glossary.html.jinja   term definitions, standalone page
eval/golden_events_*.yaml     hand-labeled test cases, pharma (10) and semiconductor (9) —
                               see README "Result"
eval/run_eval.py              baseline vs. advanced comparison
data/<segment>/cache/         cached raw pulls per segment (committed, for reproducibility)
data/<segment>/*.json         structured pipeline output per segment
trajectories/                 real agent I/O logs, captured during the build (segment-prefixed filenames)
run_pipeline.py               runs every phase in order for one segment: `python run_pipeline.py <segment>`
REPRODUCTION.md               exact commands, clean-env setup
CHANGELOG.md                  phase-by-phase Improvement Changelog
```
