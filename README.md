# SupplyChain Sentinel — Pharma Trade & Tariff Causality Agent

Built for the **micro1 Frontier Engineering Challenge 2026** (hackathon, ~8h budget).
Coded with **[Claude Code](https://claude.com/claude-code)** (Anthropic's CLI coding agent) — see
[CHANGELOG.md](CHANGELOG.md) for the phase-by-phase build log and
[trajectories/](trajectories/) for real agent I/O logs captured during the build.

**Segment: pharma only.** `config/segments/` supports other segments as a config
stub (see [config/segments/README.md](config/segments/README.md)); only pharma
is implemented this round.

## The problem

**Who this is for:** portfolio managers, business people, and government policy
analysts tracking the pharmaceutical supply chain.

**The bottleneck:** tariff/policy news, SEC filings, and market signals about
pharma supply chains are scattered across sources. No one connects *"Country X
changes an API import tariff"* to *"Company Y's 10-K already flagged this exact
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

On 8 hand-labeled golden test cases ([eval/golden_events_pharma.yaml](eval/golden_events_pharma.yaml)),
run via `python -m eval.run_eval`:

| | Baseline (single prompt) | Advanced (this pipeline) |
|---|---|---|
| Accuracy vs. golden labels | 25% (2/8) | **100% (8/8)** |
| Cases where it caught a real link the other missed | 0 | **6** |

The baseline never once mentions **Ireland** anywhere in its output — despite
being given the exact same raw Federal Register notice (US tariff cut on
EU-origin generics, naming Ireland) and the exact same four companies' 10-K
excerpts disclosing Irish manufacturing. It's not that the information wasn't
there; a single unstructured summarization pass just doesn't reliably
cross-reference two different sources at that level of specificity. The
advanced pipeline catches all four Ireland links (plus two Germany links) by
construction, because the graph step explicitly checks for shared
country/commodity — see [CHANGELOG.md](CHANGELOG.md) for the full breakdown,
including the two negative (precision) test cases.

## Architecture

```
GDELT / Federal Register ──┐
                            ├─> src/connectors/*.py ─> data/cache/*.json (raw, cached)
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
graph, no forced citations — the comparison point (data/baseline_output.json,
frozen after Phase 1).

eval/run_eval.py: runs both against eval/golden_events_pharma.yaml.
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
  and filing documents — free, no key, real 10-Ks (FY2025, filed Feb 2026) for
  8 seed pharma companies.
- No paid or rate-limited sources (X/Twitter, Reddit) are used.

## What's out of scope (by design, not oversight)

- **Textile and semiconductor segments** — config stub only
  ([config/segments/README.md](config/segments/README.md)).
- **Market price data (yfinance) and social sentiment** — not pulled.
- **LangGraph or any orchestration framework** — plain Python (dicts) is
  sufficient at this scope; `src/graph.py` has no hidden state machine.
- **A full human-approval backend** (FastAPI + persistence) — the dashboard's
  per-alert checkbox (stored in the browser's `localStorage`, nothing server-
  side) is a stand-in for the human-approval principle: these Alert Cards only
  inform a human decision-maker and never take action themselves, so a full
  approval workflow is a natural next step, not required to prove the concept.
- **Gap/Opportunity view and a what-if tariff simulator** — not built; see the
  "hot take" in CHANGELOG.md for a related real finding (eval-08) that a
  Gap view would have made more visible.

## Repo layout

```
config/segments/pharma.yaml   entity types, seed countries/companies/commodities
src/models.py                 pydantic schemas (PolicyEvent, FilingMention, GraphLink, AlertCard)
src/connectors/gdelt.py       policy/news pull (GDELT, falls back to Federal Register) + cache
src/connectors/edgar.py       SEC filing pull (full-text search + document fetch) + cache
src/baseline.py               THE baseline: one direct prompt, no structure
src/agents/policy_agent.py    Agent 1: raw policy items -> structured PolicyEvents
src/agents/filing_agent.py    Agent 2: raw filing excerpts -> structured FilingMentions
src/graph.py                  merges both agents' output into a causal graph
src/alerts.py                 graph -> cited, LLM-explained Alert Cards
src/dashboard.py              renders dist/index.html (Jinja2, static, no backend)
eval/golden_events_pharma.yaml  8 hand-labeled test cases
eval/run_eval.py              baseline vs. advanced comparison
data/cache/                   cached raw pulls (committed, for reproducibility)
trajectories/                 real agent I/O logs, captured during the build
run_pipeline.py               runs every phase in order
REPRODUCTION.md               exact commands, clean-env setup
CHANGELOG.md                  phase-by-phase Improvement Changelog
```
