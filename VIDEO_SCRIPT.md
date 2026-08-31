# 5-Minute Solution Video — Shot List & Script

Not part of the code submission — a recording aid only. Structure follows
the hackathon's required beats: problem+baseline -> one end-to-end run ->
comparison -> changelog highlights -> hot take. Timings are targets, not
hard cuts; trim the italic stage directions as you go.

Screens to have ready before you hit record:
1. A terminal in the repo root, venv activated.
2. `README.md` open (for the 10-second intro beat).
3. `dist/index.html` open in a browser tab, already built with BOTH segments
   (`python run_pipeline.py` then `python run_pipeline.py semiconductor`) —
   you'll switch the Segment dropdown live on camera.
4. `CHANGELOG.md` open, scrolled to the entries you plan to reference (pick
   which ones per the "Changelog highlights" beat below before recording).
5. `data/pharma/baseline_output.json` open in an editor (or a terminal ready
   to grep it), so you can prove the "Ireland" claim live on camera.

---

## 0:00–0:45 — Problem + baseline

*Screen: README.md, top section.*

> "Portfolio managers, business people, and government analysts tracking a
> supply chain all have the same problem: tariff news, SEC filings, and
> market signals are scattered across sources. Nobody connects 'Country X
> just changed an import tariff' to 'Company Y's own 10-K already flagged
> exactly this dependency' — so the ripple effect gets missed, or found too
> late.
>
> So I built SupplyChain Sentinel: a two-agent pipeline that reads policy
> events and SEC filings, finds the causal links between them through a
> shared entity graph, and produces cited Alert Cards. And to prove it
> actually helps — not just that it looks impressive — I built a baseline
> first: one direct LLM prompt over the exact same raw data, no structure,
> no graph. That's the thing the real pipeline has to beat."

*Screen: terminal, `cat data/pharma/baseline_output.json | head` or open it
in an editor — just enough to show it's a real, coherent-looking summary.
Don't over-explain it yet; you'll come back to it.*

## 0:45–2:30 — One realistic end-to-end run

*Screen: terminal.*

> "Everything runs from committed cache — zero network calls needed to
> GDELT, Federal Register, or SEC EDGAR to reproduce this. Only the LLM
> calls need a live API key. Let me run it."

```bash
python run_pipeline.py
```

*While it runs (mostly cache hits, ~1-2 min if any step needs a fresh LLM
call), narrate over it:*

> "Phase by phase: the connectors pull raw policy notices and SEC filing
> excerpts — those are cached to `data/pharma/cache` so this step is
> reproducible offline. Then two agents run. The Policy Agent reads dozens of
> raw government notices and filters them down to the ones that are actually
> about pharma tariffs — it throws out things like an unrelated antidumping
> case on soybean meal. The Filing Agent reads each company's 10-K excerpts
> and pulls out real, cited country-dependency statements — in either
> direction: a company sourcing from a country, or a company selling into one
> and needing an export license to. For companies with only generic
> boilerplate to work with, it correctly finds *nothing* worth extracting.
> That's the agent doing its job, not failing."

*Screen: switch to `dist/index.html` once it's rebuilt.*

> "Then the graph step connects policy events to filing mentions by shared
> country, and one more LLM call writes a plain-English explanation for
> each link, citing both sources. Here's the dashboard: an interactive
> dependency graph you can hover and click to trace one company's exact path
> back to its policy catalyst, a dozen Alert Cards below it sortable by date,
> each one clickable back to its actual government notice and its actual SEC
> filing — and this Segment dropdown."

*Click the Segment dropdown, switch to Semiconductor live.*

> "Same pipeline, a completely different real-world story: US-China export
> controls, not tariffs. Twenty-two policy events, thirty-five graph links,
> and it's almost entirely China — which is itself accurate, not a bug: that
> IS how concentrated semiconductor policy actually is right now."

*Click into one Alert Card in either segment, read a sentence or two aloud,
click both source links to show they resolve to the real documents.*

## 2:30–3:30 — Final comparison

*Screen: terminal, run `python -m eval.run_eval pharma` (or just show the
saved table from the last real run).*

> "Here's the actual measured comparison — same 8 hand-labeled pharma test
> cases, both pipelines, no cherry-picking. Baseline: 25% accuracy. Advanced
> pipeline: 100%. Six real links the baseline missed, zero regressions."

*Screen: back to baseline_output.json, run a quick search.*

> "And here's the proof that's not just an LLM judge's opinion: the word
> 'Ireland' appears **zero times** anywhere in the baseline's output —
> despite it being given the exact same Federal Register notice and the
> exact same companies' 10-K excerpts that state it. The information was
> right there in its input. A single summarization pass just doesn't
> reliably cross-reference two sources at that level of specificity — that's
> the whole thesis of this project, demonstrated, not asserted."

## 3:30–4:30 — Changelog highlights

*Screen: CHANGELOG.md.*

> "Two things worth calling out from the build log. Biggest single
> contributor to data quality, early on: the excerpt-extraction fix in the
> EDGAR connector. My first pass let the word 'tariffs' — which shows up
> dozens of times as generic legal boilerplate in every 10-K — crowd out
> every excerpt slot before any actual country-specific disclosure got a
> chance. I rewrote it to reserve slots per category and round-robin across
> countries, and that's what surfaced the country-specific sourcing
> disclosures the rest of the pipeline depends on.
>
> The one that mattered most once I added a second segment: my Filing Agent
> only recognized 'the company sources from country X.' Adding semiconductors
> exposed that as a pharma-shaped assumption — NVIDIA's own 10-K states its
> single largest China exposure is on the *selling* side, needing an export
> license to ship there, and my agent was silently skipping it because that's
> not a sourcing dependency. Broadening the prompt to recognize both
> directions picked up NVIDIA's real China story, and even added six more
> findings back in pharma for free.
>
> One thing I tried and removed: GDELT was the specified news source, but
> its API has been down for this entire build, re-checked from three
> different network paths — so the policy connector tries GDELT first and
> automatically falls back to the Federal Register API, which is also free
> and keyless. I kept the GDELT code path in — it's not deleted, it's just
> not what actually ran this time."

## 4:30–5:00 — Hot take

*Screen: dashboard, dependency graph, Gap/Opportunity section.*

> "My main takeaway isn't that the agents hallucinate — I hand-checked Alert
> Card explanations against their source snippets, and none of them invented
> facts. The real failure mode is a schema forcing a single answer onto an
> ambiguous reality. One government notice describes 'products of the
> European Union' without naming a specific member state — and my first
> Policy Agent run guessed 'Ireland.' Rerunning it later, it guessed
> 'Germany' instead. Same document, two different confident-sounding
> countries, because my schema only had room for one country and the model
> filled the gap rather than say so. The fix wasn't a better prompt — it was
> giving the schema room to say 'European Union' honestly and resolving that
> against real member-state filings downstream.
>
> That's the general lesson: an agent pipeline is only as honest as the
> shape you give its answers room to take."

*End on the dashboard, Segment dropdown visible, cards below it.*
