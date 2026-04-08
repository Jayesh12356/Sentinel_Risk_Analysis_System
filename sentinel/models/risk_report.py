"""RiskReport — output of Layer 2 reasoning agents.

RiskAssessor produces the risk scores; CausalChainBuilder adds the
causal chain.  The Red/Blue/Arbiter deliberation in Layer 3 may
update the final_priority via Loop 2.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from sentinel.models.signal import SignalPriority


class CausalLink(BaseModel):
    """Single link in a causal chain built by CausalChainBuilder."""

    cause: str = Field(..., description="Upstream cause / event")
    effect: str = Field(..., description="Downstream consequence")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Link confidence score"
    )


class RiskScore(BaseModel):
    """Composite risk score computed by RiskAssessor.

    Final = impact × probability × exposure (each 0–1).
    """

    impact: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Severity of potential damage"
    )
    probability: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Likelihood of occurrence"
    )
    exposure: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Organisational exposure level"
    )
    overall: float = Field(
        default=0.0, ge=0.0, le=1.0, description="impact × probability × exposure"
    )


class DeliberationResult(BaseModel):
    """Outcome of the Red/Blue/Arbiter deliberation (Layer 3)."""

    red_team_argument: str = Field(
        default="", description="Adversarial challenge from RedTeamAgent"
    )
    blue_team_argument: str = Field(
        default="", description="Optimistic defence from BlueTeamAgent"
    )
    arbiter_verdict: str = Field(
        default="", description="Final verdict from ArbiterAgent"
    )
    arbiter_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Arbiter confidence in verdict"
    )
    red_team_wins: bool = Field(
        default=False,
        description="If True, triggers Loop 2 (escalate priority, re-run RiskAssessor)",
    )


class RiskReport(BaseModel):
    """Full risk assessment for a signal, produced by Layer 2 + Layer 3.

    Links back to the originating Signal via signal_id.
    """

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique report identifier",
    )
    signal_id: str = Field(..., description="ID of the source Signal")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Report creation timestamp"
    )

    # --- Risk scoring (Layer 2 — RiskAssessor) ---
    risk_score: RiskScore = Field(
        default_factory=RiskScore, description="Composite risk score"
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Supporting evidence cited by RiskAssessor",
    )

    # --- Causal chain (Layer 2 — CausalChainBuilder) ---
    causal_chain: list[CausalLink] = Field(
        default_factory=list,
        description="Root-cause → downstream-effect chain",
    )
    root_cause: str = Field(
        default="", description="Identified root cause of the risk"
    )

    # --- Deliberation (Layer 3) ---
    deliberation: DeliberationResult = Field(
        default_factory=DeliberationResult,
        description="Red/Blue/Arbiter deliberation outcome",
    )

    # --- Final assessment ---
    initial_priority: SignalPriority = Field(
        default=SignalPriority.P3,
        description="Priority before deliberation",
    )
    final_priority: SignalPriority = Field(
        default=SignalPriority.P3,
        description="Priority after deliberation (may be escalated by Loop 2)",
    )
    summary: str = Field(
        default="", description="Human-readable risk summary"
    )

    # --- Level 2: Company profile matching ---
    company_matches: list[str] = Field(
        default_factory=list,
        description="Profile fields that matched (e.g. 'tech_stack:Apache')",
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="How relevant this signal is to the company profile (0.0–1.0)",
    )

