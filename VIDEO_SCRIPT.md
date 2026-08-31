# 5-Minute Solution Video — Shot List & Script

Not part of the code submission — a recording aid only. Structure follows
the hackathon's required beats: problem+baseline -> one end-to-end run ->
comparison -> changelog highlights -> hot take. Timings are targets, not
hard cuts; trim the italic stage directions as you go.

Screens to have ready before you hit record:
1. A terminal in the repo root, venv activated.
2. `README.md` open (for the 10-second intro beat).
3. `dist/index.html` open in a browser tab, already built with all five
   segments (`python run_pipeline.py <segment>` for pharma, semiconductor,
   textile, automotive, steel_aluminum) — you'll switch the Segment dropdown
   and click a graph node live on camera.
4. `CHANGELOG.md` open, with the "Semiconductor golden eval set..." entry
   found in advance — it's the one with the `a12282024ex22.htm` quote for
   the "biggest contributor" beat below. That bug is already fixed in the
   current repo, so this changelog line is the only place left that still
   shows the buggy URL — don't try to point at a live cache file instead.
5. `data/pharma/baseline_output.json` open in an editor (or a terminal ready
   to grep it), so you can prove the "Ireland" claim live on camera.

---

## 0:00–0:40 — Problem + baseline

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
> shared entity graph, and produces cited Alert Cards. To prove it actually
> helps — not just that it looks impressive — I built a baseline first: one
> direct LLM prompt over the exact same raw data, no structure, no graph.
> That's the thing the real pipeline has to beat."

*Screen: terminal, `cat data/pharma/baseline_output.json | head` or open it
in an editor — just enough to show it's a real, coherent-looking summary.
Don't over-explain it yet; you'll come back to it.*

## 0:40–2:20 — One realistic end-to-end run

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
> excerpts, cached so this step is reproducible offline. Two agents run next.
> The Policy Agent reads dozens of raw government notices and filters them
> down to the ones actually about pharma tariffs. The Filing Agent reads each
> company's 10-K excerpts and pulls out real, cited country-dependency
> statements. Then the graph step connects policy events to filing mentions
> by shared country, and one more LLM call writes a plain-English
> explanation for each link, citing both sources."

*Screen: switch to `dist/index.html` once it's rebuilt.*

> "Here's the dashboard. This is the interactive dependency graph — I can
> click any node and it traces that one company's exact path back to its
> policy catalyst, without lighting up unrelated companies that just happen
> to share a country. Below it, Alert Cards, sortable by date, each citing
> both its actual government notice and its actual SEC filing."

*Click one graph node to demonstrate the trace-and-filter. Then scroll to
the Gap/Opportunity section.*

> "This section is the honest half of the project. A Gap is a company that
> disclosed a real dependency with no matching policy yet. An Opportunity is
> the mirror case — a real policy action with no company tied to it yet.
> Nine of twelve pharma policy events are Opportunities this run — that's
> not a bug, that's showing exactly how much of the policy landscape eight
> seed companies don't cover."

*Click the Segment dropdown, cycle through 2-3 others quickly.*

> "Same pipeline, four more real segments — semiconductor, textile,
> automotive, steel and aluminum — each with its own real GDELT and SEC data,
> not filler. Semiconductor alone is almost entirely China export controls,
> which is itself accurate: that's how concentrated that policy actually is
> right now."

## 2:20–3:05 — Final comparison

*Screen: terminal, run `python -m eval.run_eval pharma` (or show the saved
table from the last real run).*

> "Here's the actual measured comparison — ten hand-labeled pharma test
> cases, same data, both pipelines, no cherry-picking. Baseline: 10%
> accuracy. Advanced pipeline: 100%. Nine real links the baseline missed,
> zero regressions. Semiconductor's golden set shows the same pattern: 100%
> versus roughly 60%."

*Screen: back to baseline_output.json, run a quick search.*

> "And here's the proof that's not just an LLM judge's opinion: the word
> 'Ireland' appears **zero times** anywhere in the baseline's output —
> despite being given the exact same Federal Register notice and the exact
> same companies' 10-K excerpts that state it. A single summarization pass
> just doesn't reliably cross-reference two sources at that level of
> specificity."

## 3:05–4:15 — Changelog highlights

*Screen: CHANGELOG.md, scrolled to the EDGAR exhibit-bug entry.*

> "Biggest single contributor to data quality, and I only caught it while
> building a second golden eval set: cross-checking my baseline judge's
> evidence for an 'Intel has no link' test case, it had actually cited
> something real — a government notice naming an Intel subsidiary by name.
> That sent me into why my own pipeline hadn't found anything comparable."

*Screen: point at the quoted `source_url` in CHANGELOG.md —
`.../a12282024ex22.htm` (already fixed in the repo now, so this changelog
line is the only place left that still shows it).*

> "Intel's cached filing excerpt was Exhibit 22 of the 10-K submission — a
> CHIPS Act funding schedule, not the actual 10-K. SEC full-text search can
> match any document in a filing, and my connector was just taking the first
> hit regardless of which one. Three of forty company pulls across all five
> segments had silently hit this. Fixed it to prefer the primary document,
> re-pulled all three, and re-derived both golden sets against the corrected
> data rather than patch around it.
>
> One thing I tried and removed: GDELT was the specified news source, but
> its API has been down for this entire build, re-checked from independent
> network paths every time I added a new segment — so the policy connector
> tries GDELT first and automatically falls back to the Federal Register
> API, also free and keyless. The GDELT code path is still in, it's just not
> what actually ran."

## 4:15–5:00 — Hot take

*Screen: dashboard, dependency graph, catalyst column.*

> "My main takeaway isn't that the agents hallucinate — I hand-checked Alert
> Card explanations against their source snippets, and none of them invented
> facts. The real failure mode is a schema forcing a single answer onto an
> ambiguous reality. One government notice describes 'products of the
> European Union' without naming a specific member state — and my first
> Policy Agent run guessed 'Ireland.' Rerunning it later, it guessed
> 'Germany' instead. Same document, two different confident-sounding
> countries, because my schema only had room for one and the model filled
> the gap rather than say so. The fix wasn't a better prompt, it was giving
> the schema room to say 'European Union' honestly and resolving that against
> real member-state filings downstream — and that same fix is what let the
> dashboard show Germany fed by two genuinely distinct real catalysts instead
> of hiding one.
>
> That's the general lesson: an agent pipeline is only as honest as the
> shape you give its answers room to take."

*End on the dashboard, Segment dropdown visible, cards below it.*
