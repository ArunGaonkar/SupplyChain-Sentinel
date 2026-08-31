"""Shared Anthropic client + trajectory logging used by baseline.py and every agent."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from src.env import load_env

load_env()

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-sonnet-5"

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Create a .env file at the repo root with:\n"
                "ANTHROPIC_API_KEY=sk-ant-...\n"
                "See REPRODUCTION.md."
            )
        _client = anthropic.Anthropic()
    return _client


def call_llm(system: str, user: str, max_tokens: int = 4096) -> str:
    """One Messages API call. Returns the response text.

    Retries once on an empty response — an intermittent failure mode
    observed repeatedly across segments during this build (a call
    completing with zero text content, not an API exception, so it isn't
    caught by any try/except around this function). Retrying the exact same
    request has reliably recovered it every time it's been hit; a second
    empty response is treated as real rather than retried indefinitely.
    """
    client = get_client()
    for attempt in range(2):
        msg = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in msg.content if block.type == "text")
        if text or attempt == 1:
            return text
    return text


def extract_json(text: str):
    """Pulls the first JSON array/object out of a response that may include
    prose or markdown code fences around it."""
    fence = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    start = min((i for i in (text.find("["), text.find("{")) if i != -1), default=-1)
    if start == -1:
        raise ValueError(f"No JSON found in LLM response: {text[:200]!r}")
    end = max(text.rfind("]"), text.rfind("}"))
    return json.loads(text[start : end + 1])


def save_trajectory(agent_name: str, call_id: str, system: str, user: str, response: str, parsed=None) -> Path:
    """Saves one agent call's full input/output as a trajectory log, per the
    hackathon requirement to preserve real trajectories collected during the
    build (not reconstructed afterward)."""
    out_dir = ROOT / "trajectories" / agent_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{call_id}.json"
    record = {
        "agent": agent_name,
        "call_id": call_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "system_prompt": system,
        "user_prompt": user,
        "raw_response": response,
        "parsed_output": parsed,
    }
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return path
