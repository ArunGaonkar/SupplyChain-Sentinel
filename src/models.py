"""Pydantic schemas shared across connectors, agents, graph, and alerts."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PolicyEvent(BaseModel):
    """A single policy/news event extracted by the Policy Agent from GDELT."""

    id: str
    country: str
    policy_type: str  # e.g. "tariff_increase", "export_restriction", "trade_agreement"
    affected_product: str  # e.g. "active pharmaceutical ingredients"
    date: str  # ISO date
    source_url: str
    snippet: str
    severity: str  # "low" | "medium" | "high"


class FilingMention(BaseModel):
    """A single company -> country/commodity dependency extracted by the Filing Agent from SEC filings."""

    id: str
    company: str
    ticker: str
    filing_type: str  # e.g. "10-K", "8-K"
    filing_date: str  # ISO date
    mentioned_country: str
    mentioned_commodity: str
    risk_text: str
    source_url: str  # SEC filing link + section reference


class GraphLink(BaseModel):
    """Connects a PolicyEvent to a FilingMention via a shared country/commodity node."""

    id: str
    policy_event_id: str
    filing_mention_id: str
    shared_country: Optional[str] = None
    shared_commodity: Optional[str] = None
    hop_count: int  # 1 = shares both country+commodity, 2 = shares one of them
    confidence: float = Field(ge=0.0, le=1.0)


class AlertCard(BaseModel):
    """Final cited, explainable output shown on the dashboard."""

    id: str
    title: str
    severity: str  # "low" | "medium" | "high"
    explanation: str  # LLM-generated, must cite both source URLs
    policy_event_id: str
    filing_mention_id: str
    graph_link_id: str
    policy_source_url: str
    filing_source_url: str
