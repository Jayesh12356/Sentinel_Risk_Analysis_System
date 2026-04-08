"""RouteDecision — Pydantic model for RouterAgent output.

Defines the routing path and company relevance for each signal.
"""

from __future__ import annotations

from enum import Enum
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class RoutePath(str, Enum):
    """Pipeline routing path decided by RouterAgent."""

    FULL = "FULL"           # Path A — full pipeline (P0/P1 + company relevant)
    FAST = "FAST"           # Path B — skip deliberation (P2 / low relevance)
    LOG_ONLY = "LOG_ONLY"   # Path C — just log + brief (P3 / zero relevance)


class RouteDecision(BaseModel):
    """Result of RouterAgent routing a single signal."""

    signal_id: str = Field(description="Signal UUID")
    path: RoutePath = Field(description="Pipeline path to follow")
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="How relevant this signal is to the company profile (0.0–1.0)",
    )
    relevance_reason: str = Field(
        default="",
        description="Why this signal is/isn't relevant to the company",
    )
    company_matches: List[str] = Field(
        default_factory=list,
        description="Which profile fields matched (e.g. 'tech_stack:Apache')",
    )
