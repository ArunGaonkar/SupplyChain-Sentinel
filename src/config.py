"""Loads config/segments/<segment>.yaml into a plain dict."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_segment(segment: str = "pharma") -> dict:
    path = ROOT / "config" / "segments" / f"{segment}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No config for segment '{segment}'. Only 'pharma' is implemented in this build."
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
