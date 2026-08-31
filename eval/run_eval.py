"""Phase 6 — baseline vs. advanced evaluation.

Runs both pipelines' ALREADY-PRODUCED outputs (data/baseline_output.json,
frozen in Phase 1 and never touched again; data/alert_cards.json, produced
by the advanced pipeline) against eval/golden_events_pharma.yaml and reports,
per hand-labeled case, whether each pipeline caught (or correctly avoided
fabricating) the company<->country connection.

Advanced-pipeline matching is deterministic (checks the structured
alert_cards.json / graph output directly — no LLM involved, so it can't be
fooled). Baseline matching uses an LLM-as-judge over the frozen baseline
prose, since there's no structure to check directly — that asymmetry is the
whole point: the baseline's only artifact IS unstructured prose.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.llm import call_llm, extract_json


JUDGE_SYSTEM = """You are grading whether a piece of analyst text explicitly draws a
specific causal connection between a company and a country's trade/tariff
policy action. Answer strictly based on what the text says — do not use
outside knowledge.

Return ONLY a JSON object: {"caught": true/false, "quote": "<=200 char
verbatim quote supporting your answer, or empty string if caught is false"}."""


def _normalize_country(c: str | None) -> str | None:
    if c is None:
        return None
    c = c.strip().lower()
    return {"usa": "united states", "u.s.": "united states", "us": "united states"}.get(c, c)


def _advanced_caught(case: dict, alert_cards: list[dict], events_by_id: dict, mentions_by_id: dict) -> tuple[bool, str]:
    for card in alert_cards:
        mention = mentions_by_id.get(card["filing_mention_id"], {})
        # Matched against the FilingMention's own mentioned_country, not the
        # PolicyEvent's — a policy event can be bloc-wide ("European Union"),
        # resolved against a specific member state on the filing side (see
        # src/graph.py EU_MEMBERS), so the mention is the ground truth for
        # "does this ticker+country combination have a confirmed link."
        if mention.get("ticker") != case["ticker"]:
            continue
        card_country = _normalize_country(mention.get("mentioned_country"))
        case_country = _normalize_country(case.get("country"))
        if case_country is None:
            continue  # eval-07: any card for this ticker at all would be the thing to flag
        if card_country == case_country:
            return True, card["title"]
    return False, ""


def _baseline_caught(case: dict, baseline_text: str) -> tuple[bool, str]:
    country_clause = f"the country {case['country']}" if case["country"] else "ANY specific country"
    claim = (
        f"Does the text below explicitly state that {case['company']} ({case['ticker']}) "
        f"has supply-chain/manufacturing/tariff exposure tied to {country_clause}, "
        f"as a specific stated connection (not just both terms appearing separately)?"
    )
    user = f"{claim}\n\n--- TEXT ---\n{baseline_text}"
    response = call_llm(JUDGE_SYSTEM, user, max_tokens=300)
    try:
        obj = extract_json(response)
        return bool(obj.get("caught")), obj.get("quote", "")
    except (ValueError, json.JSONDecodeError):
        return False, ""


def run_eval(segment: str = "pharma") -> dict:
    segment_dir = ROOT / "data" / segment
    golden_path = ROOT / "eval" / f"golden_events_{segment}.yaml"
    alert_cards_path = segment_dir / "alert_cards.json"

    golden = yaml.safe_load(golden_path.read_text(encoding="utf-8"))["cases"]
    baseline = json.loads((segment_dir / "baseline_output.json").read_text(encoding="utf-8"))
    alert_cards = json.loads(alert_cards_path.read_text(encoding="utf-8")) if alert_cards_path.exists() else []
    events_by_id = {e["id"]: e for e in json.loads((segment_dir / "policy_events.json").read_text(encoding="utf-8"))}
    mentions_by_id = {
        m["id"]: m for m in json.loads((segment_dir / "filing_mentions.json").read_text(encoding="utf-8"))
    }

    rows = []
    for case in golden:
        adv_caught, adv_evidence = _advanced_caught(case, alert_cards, events_by_id, mentions_by_id)
        base_caught, base_evidence = _baseline_caught(case, baseline["response"])

        expect = case["expect_link"]
        rows.append(
            {
                "id": case["id"],
                "company": case["company"],
                "ticker": case["ticker"],
                "country": case["country"],
                "expect_link": expect,
                "baseline_caught": base_caught,
                "baseline_correct": base_caught == expect,
                "baseline_evidence": base_evidence,
                "advanced_caught": adv_caught,
                "advanced_correct": adv_caught == expect,
                "advanced_evidence": adv_evidence,
                "advanced_beat_baseline": adv_caught == expect and base_caught != expect,
            }
        )
        print(
            f"[eval] {case['id']} {case['ticker']}/{case['country']} expect={expect} "
            f"| baseline={base_caught} advanced={adv_caught}"
        )

    n = len(rows)
    summary = {
        "total_cases": n,
        "baseline_accuracy": sum(r["baseline_correct"] for r in rows) / n,
        "advanced_accuracy": sum(r["advanced_correct"] for r in rows) / n,
        "cases_advanced_beat_baseline": sum(r["advanced_beat_baseline"] for r in rows),
        "cases_baseline_beat_advanced": sum(
            r["baseline_correct"] and not r["advanced_correct"] for r in rows
        ),
    }
    result = {"rows": rows, "summary": summary}
    (ROOT / "eval" / f"eval_results_{segment}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _print_report(result: dict) -> None:
    rows, summary = result["rows"], result["summary"]
    print("\n" + "=" * 78)
    print(f"{'CASE':<9}{'TICKER':<8}{'COUNTRY':<12}{'EXPECT':<8}{'BASELINE':<11}{'ADVANCED':<10}")
    print("-" * 78)
    for r in rows:
        tag = " <-- advanced caught what baseline missed" if r["advanced_beat_baseline"] else ""
        print(
            f"{r['id']:<9}{r['ticker']:<8}{str(r['country']):<12}{str(r['expect_link']):<8}"
            f"{str(r['baseline_caught']):<11}{str(r['advanced_caught']):<10}{tag}"
        )
    print("-" * 78)
    print(f"Baseline accuracy vs. golden labels: {summary['baseline_accuracy']:.0%}")
    print(f"Advanced accuracy vs. golden labels: {summary['advanced_accuracy']:.0%}")
    print(f"Cases where advanced was correct AND baseline was wrong: {summary['cases_advanced_beat_baseline']}")
    print(f"Cases where baseline was correct AND advanced was wrong: {summary['cases_baseline_beat_advanced']}")
    print("=" * 78)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    segment_arg = sys.argv[1] if len(sys.argv) > 1 else "pharma"
    result = run_eval(segment=segment_arg)
    _print_report(result)
