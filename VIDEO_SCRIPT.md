# 5-Minute Solution Video — Shot List & Script

Not part of the code submission — a recording aid only. Structure follows
the hackathon's required beats: problem+baseline -> one end-to-end run ->
comparison -> changelog highlights -> hot take. Timings are targets, not
hard cuts; trim the italic stage directions as you go.

Screens to have ready before you hit record:
1. A terminal in the repo root, venv activated.
2. `README.md` open (for the 10-second intro beat).
3. `dist/index.html` open in a browser tab, already built.
4. `CHANGELOG.md` open, scrolled to the Phase 0 and Phase 4 entries.
5. `data/baseline_output.json` open in an editor (or a terminal ready to
   grep it), so you can prove the "Ireland" claim live on camera.

---

## 0:00–0:45 — Problem + baseline

*Screen: README.md, top section.*

> "Portfolio managers, business people, and government analysts tracking the
> pharma supply chain all have the same problem: tariff news, SEC filings,
> and market signals are scattered across sources. Nobody connects 'Country X
> just changed an API import tariff' to 'Company Y's own 10-K already
> flagged exactly this dependency' — so the ripple effect gets missed, or
> found too late.
>
> So I built SupplyChain Sentinel: a two-agent pipeline that reads policy
> events and SEC filings, finds the causal links between them through a
> shared entity graph, and produces cited Alert Cards. And to prove it
> actually helps — not just that it looks impressive — I built a baseline
> first: one direct LLM prompt over the exact same raw data, no structure,
> no graph. That's the thing the real pipeline has to beat."

*Screen: terminal, `cat data/baseline_output.json | head` or open it in an
editor — just enough to show it's a real, coherent-looking summary. Don't
over-explain it yet; you'll come back to it.*

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
> excerpts — those are cached to `data/cache` so this step is
> reproducible offline. Then two agents run. The Policy Agent reads ~66 raw
> government notices and filters them down to the dozen that are actually
> about pharma tariffs — it threw out things like an unrelated antidumping
> case on soybean meal. The Filing Agent reads each company's 10-K excerpts
> and pulls out real, cited country-dependency statements — and for two of
> the eight companies, it correctly found *nothing* worth extracting,
> because their excerpts were too generic. That's the agent doing its job,
> not failing."

*Screen: switch to `dist/index.html` once it's rebuilt.*

> "Then the graph step connects policy events to filing mentions by shared
> country, and one more LLM call writes a plain-English explanation for
> each link, citing both sources. Here's the dashboard: a dependency graph
> — policy event, to shared country, to company — and six Alert Cards below
> it, each one clickable back to its actual government notice and its
> actual SEC filing."

*Click into one Alert Card, read a sentence or two aloud, click both source
links to show they resolve to the real documents.*

## 2:30–3:30 — Final comparison

*Screen: terminal, run `python -m eval.run_eval` (or just show the saved
table from the last real run).*

> "Here's the actual measured comparison — same 8 hand-labeled test cases,
> both pipelines, no cherry-picking. Baseline: 25% accuracy. Advanced
> pipeline: 100%. Six real links the baseline missed, zero regressions."

*Screen: back to baseline_output.json, run a quick search.*

> "And here's the proof that's not just an LLM judge's opinion: the word
> 'Ireland' appears **zero times** anywhere in the baseline's output —
> despite it being given the exact same Federal Register notice and the
> exact same four companies' 10-K excerpts that state it. The information
> was right there in its input. A single summarization pass just doesn't
> reliably cross-reference two sources at that level of specificity — that's
> the whole thesis of this project, demonstrated, not asserted."

## 3:30–4:30 — Changelog highlights

*Screen: CHANGELOG.md.*

> "Two things worth calling out from the build log. Biggest single
> contributor to quality: the excerpt-extraction fix in the EDGAR connector.
> My first pass let the word 'tariffs' — which shows up dozens of times as
> generic legal boilerplate in every 10-K — crowd out every excerpt slot
> before any actual country-specific disclosure got a chance. I rewrote it
> to reserve slots per category and round-robin across countries, and that's
> what actually surfaced the India, China, Ireland, and Germany sourcing
> disclosures the rest of the pipeline depends on. Without that fix, the
> Filing Agent would've had almost nothing real to work with.
>
> One thing I tried and removed: GDELT was the specified news source, but
> its API was down for this entire build — confirmed from three different
> network paths, and independently corroborated by GDELT's own maintainer
> posting about infrastructure outages. So the policy connector tries GDELT
> first and automatically falls back to the Federal Register API, which is
> also free and keyless. I kept the GDELT code path in — it's not deleted,
> it's just not what actually ran this time."

## 4:30–5:00 — Hot take

*Screen: CHANGELOG.md, "Hot take" section at the bottom.*

> "My main takeaway isn't that the agents hallucinate — I hand-checked every
> Alert Card explanation against its source snippets, and none of them
> invented facts. The real failure mode is one-sided coverage. Eli Lilly's
> own 10-K explicitly says it depends on China-based API suppliers — the
> Filing Agent correctly extracted that. But there's no matching
> China-specific policy event in this run's data, so the graph can't link
> it — not because anything failed, but because the policy side genuinely
> doesn't name China in the notice I have. I checked the government
> document's actual full text to confirm that, not just guessed.
>
> That points at the natural next feature — a Gap view that surfaces
> confirmed company dependencies with *no* policy-side match yet, as their
> own kind of signal. Explicitly out of scope for this build, but it's the
> most interesting thing the eval turned up."

*End on the dashboard, cards visible.*
