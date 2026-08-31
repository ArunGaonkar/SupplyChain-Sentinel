# Improvement Changelog

One entry per phase/iteration: what was tried, the evidence, and the
decision/learning. Includes things tried and removed, per the hackathon's own
rules for this document.

## Post-submission — Semiconductor golden eval set; three more segments; nav UI

Requested: a hand-labeled golden eval set for semiconductor; three more
segments (textile, automotive, steel/aluminum); a "move to top" button and a
side nav for jumping between dashboard sections.

**A real EDGAR connector bug, found while designing the semiconductor golden
set, not while building a new segment:** cross-checking the baseline
judge's evidence for an "Intel has no country link" test case surfaced that
the baseline had actually cited something real — a Federal Register notice
naming "Intel Semiconductor (Dalian)" by name. Investigating why the
*advanced* pipeline hadn't found anything comparable led to Intel's cached
filing excerpt: `.../a12282024ex22.htm` — Exhibit 22 of the 10-K submission
(a CHIPS Act funding-agreement schedule), not the actual 10-K body. EDGAR's
full-text search matches any document in a filing submission, and
`_search_best_filing` was taking `hits[0]` regardless of which document that
was. Checked all 16 company pulls across both segments at the time: 3 had
this exact problem (pharma's MRK, semiconductor's INTC and MU). Fixed by
preferring hits where `file_type` matches the requested form, falling back
to an exhibit only if literally nothing else exists. Re-pulled all three
companies' real 10-Ks and reran both segments end to end: pharma's link
count went 8 → 12, semiconductor's 7 unique company/country pairs → 7 (same
count, but INTC and MU are now *correctly* included instead of absent, and
MRK gained a real Switzerland link it didn't have before). Both golden sets
were re-derived from scratch against this corrected data rather than
patched, the same discipline as the original pharma set: hand-review the
cache first, confirm against pipeline output second, never copy from
`alert_cards.json` directly.

**A second, unrelated intermittent bug, caught by the same re-derivation
churn:** both `policy_agent.py` and `filing_agent.py` occasionally got back
a completely empty response from the API (not an exception — a call that
completes with zero text content). It surfaced repeatedly enough across
these reruns (pharma's ABBV losing all 3 mentions on one run, then recovering
on retry; two separate steel_aluminum policy batches in a row) that manual
retries stopped being a reasonable response. Added a one-retry-on-empty
wrapper directly in `src/llm.py`'s `call_llm`, since every occurrence so far
has recovered on a second identical call.

**Segment results:** semiconductor's golden set (9 cases, 7 positive + 2
gap negatives): 100% advanced vs. ~60-67% baseline (varies a few points
run-to-run — the baseline side of `eval/run_eval.py` is judged by a fresh
LLM call each run, not cached, so its score is expected to move slightly;
the advanced pipeline's score doesn't, since it's read directly from the
structured graph), 3-4 cases advanced caught that baseline missed, 0
regressions either way. A smaller baseline gap than pharma's own 100%/10% —
China chip export controls are famous enough that a single-prompt baseline
gets some of the "obvious" cases right too — but the advanced pipeline still
never misses anything the baseline got right, and correctly abstains on
both Taiwan/TSMC gap cases the same way baseline does.
Textile, automotive, and steel/aluminum were all built with the same recipe
(config → GDELT/Federal Register pull → EDGAR pull → Policy Agent → Filing
Agent → graph → alerts); no golden sets were built for those three (out of
scope for this round — see README).

**A data-pull lesson, not a code bug, from textile specifically:** the
first-pass query terms ("textile tariff", "apparel import tariff", etc.)
surfaced almost no policy events outside China, even though Vietnam and
Bangladesh are the dominant real sourcing countries in every seed company's
own 10-K. Testing more specific terms directly against the Federal Register
API before committing ("Vietnam tariff apparel", "reciprocal tariff
Vietnam") surfaced the real April 2025 reciprocal-tariff proclamation and a
real Vietnam-specific Section 301 investigation that the generic terms had
missed entirely. Applied the same direct-testing step to automotive and
steel/aluminum's query terms before pulling, rather than after finding the
same gap three more times.

**A third real bug — cross-segment ID collisions — found once all five
segments' data landed in the same dashboard:** spot-checking the live
dashboard after building textile/automotive/steel_aluminum, pharma's
"Graph Links" tile read 4 instead of the actual 12, while automotive's read
21 instead of 13. `PolicyEvent`/`FilingMention`/`GraphLink` ids are hashed
from `source_url` and unique only *within* one segment's own pull — but a
genuinely cross-industry government notice (a multi-sector USMCA
implementation order, a broad reciprocal-tariff proclamation) legitimately
gets pulled by more than one segment's search terms, landing the identical
id in both. Confirmed by directly diffing `source_url` across all five
segments' `policy_events.json`: 4 real collisions, e.g. the same USMCA
notice hashing to the same id in both `textile` and `automotive`. Since the
dashboard merges every segment's events/mentions/links into one client-side
`eventsById`/`mentionsById` map (keyed by that bare id) for the interactive
graph, one segment's entry was silently overwriting another's — which then
made the *other* segment's own graph links resolve to the wrong segment
when filtered, exactly matching the observed under- and over-counts. Fixed
by segment-prefixing every id that crosses into the client-side JSON and
the corresponding `data-event-id`/`data-mention-id` card attributes
(`src/dashboard.py`'s new `gid()` helper) — ids used only for lookups
internal to one segment's own data (`events_by_id` etc.) stay unprefixed,
since those never had a collision risk to begin with.

**Dashboard nav:** a fixed side nav (Dependency Graph / Alert Cards / Gaps /
Opportunities), highlighting whichever section is currently in view via
`IntersectionObserver`, and a "back to top" button that fades in after
scrolling. The side nav's links are real `<a href="#id">` anchors rather
than JS-driven `scrollIntoView` calls (like the stat tiles use) — an anchor
click handled with `scrollIntoView({behavior:"smooth"})` turned out to
silently not animate in some cases (auto-expanding the target `<details>`
correctly every time, per `openAncestorDetails`, but never actually
scrolling), while the browser's own native hash-navigation always works
reliably. Switched to letting the native navigation do the scrolling,
smoothed globally via `scroll-behavior: smooth` on `<html>` — the standard
mechanism for a real link — rather than fighting it with `preventDefault()`
and a manual scroll call.

## Post-submission — Semiconductor segment (real second segment, not a stub)

Requested: expand from pharma-only to also cover semiconductors, and retry
GDELT (still down — same confirmed infrastructure outage as Phase 0, checked
again from two independent network paths).

**Refactor required first:** every path in the codebase was hardcoded to
`data/policy_events.json` etc. — a single, implicit "pharma" dataset. Adding
a second segment meant threading a `segment` parameter through every
connector, agent, `graph.py`, `alerts.py`, `baseline.py`, and `eval/
run_eval.py`, and moving data to `data/<segment>/...`. Trajectory filenames
also gained a segment prefix (`pharma_batch_000.json`) since `policy_agent`'s
batch-number naming would otherwise collide across segments.

**Real bug found and fixed (generalizing a pharma-specific assumption):**
`src/connectors/edgar.py` hardcoded `"tariffs"/"tariff"` as the search term
tried first when picking which filing to pull, on the unstated assumption
that tariffs are always the central policy lever. For semiconductors, export
controls (the China Entity List, license requirements on advanced chips) are
at least as central as tariffs — this is not a semiconductor-only
technicality, it's the dominant real 2025-2026 policy story for this sector.
Fixed by making the priority-term list a per-segment config field
(`edgar_priority_terms`) instead of a hardcoded constant.

**Real bug found and fixed (a second pharma-specific assumption, more
consequential):** the Filing Agent's prompt only recognized SOURCE
dependencies ("the company manufactures/sources in country X"). Rerunning it
for semiconductors surfaced that NVIDIA's own 10-K discusses its single most
material China exposure — a "significant portion of our revenue," subject to
US export-license requirements — and the agent correctly skipped it, because
that's a MARKET/export dependency (the company sells there and needs a
license to), not a sourcing one. The prompt was pharma-shaped: pharma tariffs
are overwhelmingly about importing FROM a country, so sourcing-only framing
happened to be sufficient there and the gap never showed up. Broadened the
prompt to recognize both directions equally. Rerunning pharma too (for
consistency, not because pharma needed it) picked up 6 more FilingMentions
there as well (18 -> 24) — a small quality improvement piggybacking on a fix
made for a different segment's problem. Re-ran the full pharma eval
afterward to confirm this didn't regress it: still 25% baseline / 100%
advanced / 6 cases won / 0 lost.

**Bug found and fixed (silent truncation, not a logic error):** both
`policy_agent.py` (`max_tokens=3000`) and `filing_agent.py`
(`max_tokens=2000`) had been sized against pharma's hit rate. Semiconductor's
batches had a higher density of genuinely relevant items, so two
policy-agent batches and two filing-agent calls got cut off mid-JSON-array —
caught immediately because `extract_json` then failed to parse them (a loud
failure, not a silent one), not because anyone was watching for it. Raised
both limits (4096 / 3000) and reran; every batch parsed cleanly afterward.

**Result:** semiconductor produced 22 PolicyEvents, 32 FilingMentions, 35
GraphLinks, 34 Alert Cards, from real GDELT-outage-fallback Federal Register
notices and real 10-Ks — richer and more concentrated than pharma's numbers,
which is itself an honest finding: real-world semiconductor export-control
policy in this window is genuinely denser and more China-concentrated than
pharma tariff policy is EU-concentrated. No golden eval set was built for
semiconductor (out of scope for this pass — see README); `run_pipeline.py`
skips Phase 6 for a segment with no golden file rather than fake a score.

**Dashboard:** the Segment dropdown (previously a no-op stub) now genuinely
switches — every segment with data is rendered into the same page, tagged
`data-segment`, and the existing time-range/focus filter mechanism was
extended with a segment filter using the identical pattern. Switching
segments clears any active company/country focus, since a focus based on a
country string (e.g. "China" or "Germany") could otherwise silently carry
over and match the wrong segment's same-named country.

## Post-submission — Dashboard v3 (Opportunities, grouping, sort, dynamic stats, glossary)

Requested feedback on v2: the header stat tiles didn't visibly do anything,
the Gap section was one flat list with no company grouping, "Gap/Opportunity"
only ever showed Gaps, alert cards didn't show their own date, and there was
nowhere to look up what any of the terminology meant.

**Bug found and fixed before it shipped:** the first attempt at grouping
gaps by company used a dict key named `"items"` — Jinja's `.` attribute
access on a Python dict tries `getattr()` before `__getitem__`, so
`group.items` silently resolved to `dict.items` (the built-in method
object) instead of the list, and the template threw `TypeError: object of
type 'builtin_function_or_method' has no len()` immediately, not silently
wrong — caught before ever rendering. Renamed the key to `"mentions"`.

**Bug found and fixed before it shipped (second one):** after adding
country-grouping for Opportunities using the same `.company-group` CSS
class as the company-grouped Gaps, the filter JS's "hide empty groups"
logic only ever queried `.card[data-kind="gap"]` inside each group — so
every Opportunity group (which only contains `data-kind="opportunity"`
cards) always looked empty and got hidden regardless of the actual filter
state. Fixed by making the group-emptying pass check both kinds and
attribute each visible card to the right counter by its own `data-kind`.

**Decision — what "Opportunity" means:** symmetric with Gap. A Gap is a
FilingMention with no matching PolicyEvent (company disclosed a dependency,
no policy confirms it). An Opportunity is the mirror case: a PolicyEvent
with no matching FilingMention (a real policy action happened, but no
covered company's filing has been tied to it). 10 of the 12 policy events
this run are Opportunities — most policy actions in the pull don't happen
to match any of the 8 seed companies' disclosed dependencies, which is
itself informative (it's showing exactly how much of the policy landscape
this narrow company list doesn't yet cover).

**Added:** Alert Cards show their own Policy Event Date directly (previously
only used for filtering, never displayed) and can be sorted most-recent /
oldest. Gaps are grouped by company, Opportunities by country, both as
nested collapsible `<details>`. Alert Cards and Gap/Opportunity are each
one big collapsible section with a larger heading. Header stat tiles are
now clickable (jump-and-expand to the relevant section) and update live
from the current time-range filter, with a "showing: X" label so it's
never ambiguous whether a number is the full dataset or the filtered view.
A separate glossary.html page defines every entity and term used across
the dashboard.

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
