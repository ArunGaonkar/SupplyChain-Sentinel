# Improvement Changelog

One entry per phase/iteration: what was tried, the evidence, and the
decision/learning. Includes things tried and removed, per the hackathon's own
rules for this document.

## Post-submission — Dashboard v2 (catalyst graph, Gap view, interactivity, filters)

Requested after initial submission: a clearer graph, a Gap/Opportunity view
(previously explicitly out of scope), and dashboard controls.

**Bug found and fixed (the important one):** adding a `headline` field to
`PolicyEvent` required re-running the Policy Agent, which surfaced a real
extraction bug, not just LLM non-determinism. The Ireland-linked policy
notice's actual text only ever says "products of the European Union" — it
never names Ireland, or any specific member state, anywhere. The *first*
agent run had labeled it `country: "Ireland"`; re-running it (before the fix
below) relabeled the same document `country: "Germany"`. Both were the model
guessing a plausible-sounding member state because the schema only allows
one `country` per event — neither guess is actually grounded in the source
text. Caught by re-fetching the raw notice and confirming neither country is
named. Fixed two ways: (1) the Policy Agent's prompt now instructs it to
record `"European Union"` rather than invent a member state when the source
text is bloc-wide and doesn't name one; (2) `src/graph.py` gained an
`EU_MEMBERS` set so a `"European Union"` policy event still correctly
matches a `FilingMention` naming any specific member country (Ireland,
Germany, ...), resolving `GraphLink.shared_country` to that specific country
rather than the literal string "European Union". Net effect: Germany is now
correctly shown fed by **two** distinct, real catalysts (the EU tariff
framework AND the separate Section 301 Germany pricing probe) instead of one
— which is also a more informative answer to "why does the graph only show
two countries, aren't there other dependencies" than any UI change alone
would have been. Link count went from 6 to 8.

**Decision:** every `PolicyEvent` now carries a short LLM-generated
`headline` (e.g. "US-EU Framework Tariff Cut on Generic Drugs") instead of
citations reading as `"Ireland — tariff_decrease"`. Used as the graph's
leftmost "catalyst" node label and as the Alert Card citation text — same
fix, two places, because the underlying problem (policy source not
identified in a way a non-expert recognizes) was the same in both.

**Decision:** the dependency graph moved from server-rendered static SVG to
client-side JS rendering `data-*`-driven from an embedded JSON blob, because
a time-range filter and a detail-level toggle both change which nodes exist
and how the graph should re-layout — trying to pre-bake every combination as
static SVG doesn't scale, and re-deriving layout in JS on every state change
is the same amount of code either way.

**Bug found and fixed (interactivity):** the first hover/click-highlight
implementation did a plain BFS over the whole graph from the clicked node.
For a company node this correctly reached its country and catalyst nodes —
but ALSO reached every *other* company sharing that same country hub (e.g.
clicking ABBV would highlight BMY, LLY, VTRS too, since they're all in the
same connected component through the shared "Ireland" node). Fixed by
tagging every rendered edge with the specific underlying `GraphLink` id(s)
that produced it, and highlighting only edges/nodes reachable through edges
that share a link id with the clicked node — so clicking a company traces
that company's own path back to its catalyst(s) without lighting up
unrelated siblings that merely pass through the same country.

**Added, not previously built:** a Gap/Opportunity section (the "hot take"
future-work item from the original CHANGELOG entry) listing FilingMentions
with no matching PolicyEvent — 12 of them, including Lilly's own
China-API-dependency admission from eval-08. Time-range dropdown (presets:
All time / Last 90 days / Last 30 days / Since 2026-01-01), defaulting to
All time specifically because a hard floor at 2026-01-01 would silently hide
the Ireland tariff event (dated 2025-09-25) that drives most of the Alert
Cards — that's correct, intentional filtering behavior when a user picks it,
not something that should happen by default. Segment dropdown with only
"Pharma" enabled (Textile/Semiconductor shown disabled) as a stub for future
segments, per the original scope decision to not build those out.

## Phase 0 — Scaffolding + data snapshot

**Tried:** GDELT DOC 2.0 API directly, as specified.
**Evidence:** every request to `api.gdeltproject.org` timed out — tested from
three independent network paths (direct `curl`, `requests` with the sandbox
disabled, and Anthropic's own `WebFetch` infrastructure, which got a hard
`ECONNREFUSED`). A `WebSearch` turned up a LinkedIn post from GDELT's own
maintainer acknowledging "multiple GDELT infrastructure outages." Not an
environment quirk — the service was genuinely down.
**Decision:** `src/connectors/gdelt.py` tries GDELT first, and only on
failure falls back to the Federal Register API (also free, keyless). Both
code paths are real and implemented; if GDELT is reachable when you run it,
GDELT is used and the fallback is skipped silently. Given the actual result —
Federal Register surfaced the real, current (April 2025 - Aug 2026) Section
232 pharma tariff proclamation and several bilateral tariff notices — this
substitution produced *better* data for this specific segment than generic
news search likely would have, not a worse one.

**Tried:** Federal Register's default `order=newest` sort.
**Evidence:** top results were noise unrelated to pharma (an "Organic Soybean
Meal From India" antidumping case, a general regulatory-agenda index).
**Decision:** switched to `order=relevance`, which surfaced the actual pharma
tariff proclamation as the #1 result for the same query.

**Tried:** SEC EDGAR full-text search filtered by `ciks`/`entityName` with
query term "tariff" (singular).
**Evidence:** returned 0 hits for every seed company, even ones later
confirmed to discuss tariffs extensively. Testing showed "tariffs" (plural)
returned real hits (18 for Pfizer) while "tariff" (singular) mostly didn't —
a quirk of how the underlying search indexes the term.
**Decision:** filing search now prioritizes "tariffs"/"tariff" together, and
company CIKs are resolved via SEC's official `company_tickers.json` rather
than name-matching.

**Tried (first pass):** a single sequential fill for excerpt extraction —
whichever keyword's mentions appeared first got the fixed-size excerpt
budget.
**Evidence:** "tariffs" appears dozens of times as generic forward-looking-
statement boilerplate in every 10-K, so it ate all 6 excerpt slots before any
country-specific sentence (e.g. Viatris's actual manufacturing-locations
disclosure) got a chance.
**Decision (removed and replaced):** rewrote `_extract_excerpts` in
`src/connectors/edgar.py` with a reserved slot budget per category (2 tariff
slots, 6 country slots round-robined across countries so one heavily-
mentioned country can't crowd out others, 2 "other" slots) — this is what
actually surfaced the India/China/Ireland/Germany sourcing disclosures that
make the rest of the pipeline work.

**Bug found and fixed:** the first extraction pass also pulled hidden inline-
XBRL tag-soup (`<div style="display:none"><ix:header>...`) into the "prose"
because `BeautifulSoup.get_text()` doesn't know that block is invisible.
"India"/"China" excerpts came back as `us-gaap:ForeignCountryMember ... ` —
garbage, not English. Fixed by decomposing `style="display:none"` elements
and `ix:`/`xbrli:`-namespaced tags before extracting text.

## Phase 1 — Baseline

One direct prompt over all cached raw text (deduped policy items + filing
excerpts, ~111K chars), no schema, no forced citations. Saved to
`data/baseline_output.json`. On inspection it's a genuinely well-written,
information-dense summary — the point isn't that the baseline is bad prose,
it's that it doesn't reliably cross-reference two different sources at the
country-specific level (see Phase 6).

## Phase 2 — Policy Agent

Batched extraction (18 raw items/call, 4 calls) over 66 deduplicated raw
policy items. Result: 12 relevant, structured `PolicyEvent`s — the other 54
items (82%) were correctly filtered out as noise from the broad keyword pull
(general antidumping cases, unrelated regulatory notices). This filtering
judgment is the actual value of an agent step here, not just reformatting.

## Phase 3 — Filing Agent

One call per company (8 calls) over its cached excerpts. Result: 18
structured `FilingMention`s. Two companies (Merck, Johnson & Johnson)
correctly yielded **zero** mentions — their cached excerpts were generic
risk-factor language or incidental country mentions with no stated
sourcing/manufacturing dependency specific enough to support a real claim.
Confirmed this was correct scope discipline, not a missed extraction, by
re-reading their raw excerpts by hand.

## Phase 4 — Causal graph + Alert Cards

**Bug found and fixed:** `FilingMention` IDs were originally hashed from
`source_url + excerpt_index` alone. Eli Lilly's 10-K has one sentence naming
*both* Puerto Rico and Ireland as manufacturing sites — the agent correctly
extracted two separate `FilingMention`s from that one excerpt, both with the
same `excerpt_index`, which collided onto the same id. Any dict keyed by
`id` (which `src/graph.py` does) silently dropped one of the two, and a debug
print briefly appeared to show a nonsensical Germany-policy-event-linked-to-
a-China-filing-mention pairing before the root cause was found. Fixed by
hashing on `source_url + excerpt_index + country + commodity` instead, and
added a unique-ID assertion check while debugging it.

**Decision:** commodity-only matches (same commodity, different country) are
deliberately excluded from the graph — too weak a signal at this data scope,
would produce noisy links (e.g. two unrelated companies both mentioning
"generic drugs"). Only shared-country links (optionally with matching
commodity, which raises confidence) are kept.

**Decision:** links are deduplicated per (policy event, company, country) —
Bristol-Myers Squibb's 10-K states its Ireland manufacturing presence in two
different sections (MD&A and Properties), which would otherwise produce two
near-identical Alert Cards for the same underlying fact.

Result: 6 `GraphLink`s (Ireland x4 companies, Germany x2 companies), each
turned into a cited Alert Card by `src/alerts.py`. Spot-checked all 6
explanations by hand against the source snippets given to the model — no
invented specifics (dollar amounts, percentages, dates not in the source
text) found.

## Phase 5 — Dashboard

Static Jinja2 -> `dist/index.html`, zero external JS/CSS dependencies. The
dependency-tree visual is hand-computed SVG (3 columns: policy event -> 
shared country -> company), not a charting library — verified rendering
correctly in-browser (Chromium via the Claude Code browser tool), including
the per-alert "reviewed" checkbox persisting via `localStorage`.

## Phase 6 — Evaluation

8 hand-labeled golden cases (6 recall tests, 2 precision/true-negative
tests), written from manually reviewing the cached raw data, then checked
against pipeline output. See `eval/golden_events_pharma.yaml` for full
rationale per case.

**Bug found and fixed:** `run_pipeline.py` originally called
`run_baseline()` unconditionally on every run. Since every other phase
checks for existing output first, this was the one phase that would
silently regenerate — meaning a second full pipeline run would silently
overwrite the frozen `data/baseline_output.json` the hackathon's own rules
say must not be touched again after Phase 6, with a *different* LLM
generation each time, making the eval numbers non-reproducible run to run.
Fixed `src/baseline.py` to check for existing output the same way every
other phase does; regenerated one final baseline and re-ran the full eval
against it.

**Result (final, reproducible from the committed data/):**

| | Baseline | Advanced |
|---|---|---|
| Accuracy vs. 8 golden labels | 25% (2/8) | **100% (8/8)** |
| Correct where the other was wrong | 0 | **6** |

The single most load-bearing fact behind this number: the word "Ireland"
appears **zero times** anywhere in the baseline's output (verified by direct
string search, not just the LLM judge), despite the baseline being given the
exact same raw Federal Register notice and the exact same four companies'
10-K excerpts that state it. Four of the pipeline's six real links are
Ireland links the baseline never had a chance of catching because it never
mentioned the country at all.

**Note on eval-08 (Lilly / China) — the most interesting case in the set,
not a clean win either way:** Lilly's own 10-K explicitly states "we...
depend on China-based suppliers for portions of our supply chain" (a real,
extracted `FilingMention`). But no `PolicyEvent` for China exists in this
run's data, so the graph correctly produces no link — not because any agent
filtered it out, but because there's nothing on the policy side to link to.
Checked *why*: fetched the actual full-text XML of the Section 232 pharma
investigation notice directly from `federalregister.gov` (not just its
title+abstract, which is all the connector normally pulls) — it genuinely
never names China or India anywhere in the document. That's a real,
structural fact about how this notice is worded, not a search-term miss.
Documented here rather than hidden: this is the honest boundary of what a
free-tier, title+abstract-scoped policy pull can support.

## Hot take (biggest failure mode observed)

The pipeline's failure mode isn't hallucination — every Alert Card explanation
was checked by hand against its two source snippets and none invented facts
beyond them. **The real failure mode is one-sided coverage**: the Filing
Agent can correctly and honestly extract a company's own admission of a
country dependency (Lilly/China is the clean example), but if the policy-side
source's actual document text doesn't name that country, the graph has
nothing to link it to — through no fault of either agent. A genuinely useful
next feature, explicitly out of scope this round, is a **Gap/Opportunity
view**: surfacing `FilingMention`s with no matching `PolicyEvent` as their
own kind of signal ("this company has disclosed a real dependency here, but
no policy-side confirmation exists yet — watch this country"), rather than
only ever showing confirmed dual-sourced links.
