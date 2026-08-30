"""Runs the full SupplyChain Sentinel pipeline end to end, in order.

Every step reads from data/cache/ (or its own prior output) first and only
calls an external API if that cache is missing — so a rerun with the
existing data/ and data/cache/ directories intact touches only the
Anthropic API (for the agent/LLM steps), never GDELT/Federal Register/SEC.

See REPRODUCTION.md for exact commands, expected output, and runtime.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.config import load_segment
from src.connectors import edgar, gdelt


def main():
    cfg = load_segment("pharma")

    print("\n=== Phase 0: connectors (pull + cache raw data) ===")
    gdelt.pull_policy_events(cfg["gdelt_query_terms"])
    edgar.pull_filings(cfg["companies"], cfg["edgar_query_terms"], cfg["countries"])

    print("\n=== Phase 1: baseline (single-prompt summarizer) ===")
    from src.baseline import run_baseline

    run_baseline()

    print("\n=== Phase 2: Policy Agent ===")
    from src.agents.policy_agent import run_policy_agent

    run_policy_agent()

    print("\n=== Phase 3: Filing Agent ===")
    from src.agents.filing_agent import run_filing_agent

    run_filing_agent()

    print("\n=== Phase 4: causal graph + Alert Cards ===")
    from src.alerts import run_alerts
    from src.graph import run_graph

    run_graph()
    run_alerts()

    print("\n=== Phase 5: dashboard ===")
    from src.dashboard import build_dashboard

    path = build_dashboard()
    print(f"Dashboard written to {path}")

    print("\n=== Phase 6: evaluation (baseline vs. advanced) ===")
    from eval.run_eval import _print_report, run_eval

    result = run_eval()
    _print_report(result)

    print("\nDone. Open dist/index.html in a browser to see the dashboard.")


if __name__ == "__main__":
    main()
