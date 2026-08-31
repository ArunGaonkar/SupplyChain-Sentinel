"""Runs the full SupplyChain Sentinel pipeline end to end, in order, for one
segment: `python run_pipeline.py [segment]` (default: pharma).

Every step reads from data/<segment>/cache/ (or its own prior output) first
and only calls an external API if that cache is missing — so a rerun with
the existing data/ directories intact touches only the Anthropic API (for
the agent/LLM steps), never GDELT/Federal Register/SEC.

Phase 5 (dashboard) always rebuilds from EVERY segment that has data on
disk, not just the one just processed — the dashboard's segment dropdown
switches between them client-side, so it needs all of them present.
Phase 6 (eval) runs only if a golden test set exists for this segment
(eval/golden_events_<segment>.yaml) — semiconductor doesn't have one yet by
design (see README "Out of scope"), so it's skipped there, not faked.

See REPRODUCTION.md for exact commands, expected output, and runtime.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.config import load_segment
from src.connectors import edgar, gdelt


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else "pharma"
    cfg = load_segment(segment)

    print(f"\n=== Phase 0: connectors (pull + cache raw data) [{segment}] ===")
    gdelt.pull_policy_events(cfg["gdelt_query_terms"], segment=segment)
    edgar.pull_filings(
        cfg["companies"],
        cfg["edgar_query_terms"],
        cfg["countries"],
        segment=segment,
        priority_terms=cfg.get("edgar_priority_terms"),
    )

    print(f"\n=== Phase 1: baseline (single-prompt summarizer) [{segment}] ===")
    from src.baseline import run_baseline

    run_baseline(segment=segment)

    print(f"\n=== Phase 2: Policy Agent [{segment}] ===")
    from src.agents.policy_agent import run_policy_agent

    run_policy_agent(segment=segment)

    print(f"\n=== Phase 3: Filing Agent [{segment}] ===")
    from src.agents.filing_agent import run_filing_agent

    run_filing_agent(segment=segment)

    print(f"\n=== Phase 4: causal graph + Alert Cards [{segment}] ===")
    from src.alerts import run_alerts
    from src.graph import run_graph

    run_graph(segment=segment)
    run_alerts(segment=segment)

    print("\n=== Phase 5: dashboard (all segments) ===")
    from src.dashboard import build_dashboard

    path = build_dashboard()
    print(f"Dashboard written to {path}")

    golden_path = ROOT / "eval" / f"golden_events_{segment}.yaml"
    if golden_path.exists():
        print(f"\n=== Phase 6: evaluation (baseline vs. advanced) [{segment}] ===")
        from eval.run_eval import _print_report, run_eval

        result = run_eval(segment=segment)
        _print_report(result)
    else:
        print(f"\n=== Phase 6: evaluation skipped — no {golden_path.name} for this segment ===")

    print("\nDone. Open dist/index.html in a browser to see the dashboard.")


if __name__ == "__main__":
    main()
