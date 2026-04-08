"""QualityScore — brief quality scoring model for SENTINEL Level 4.

Each pipeline run produces a QualityScore that grades the generated brief
on 5 dimensions. Low scores trigger the PromptOptimiser.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class QualityScore(BaseModel):
    """Quality scoring result for a generated brief."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    brief_id: str = Field(..., description="ID of the brief being scored")

    # 5-dimension scores (each 0.0–1.0)
    specificity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Are recommendations specific to company stack?",
    )
    evidence_depth: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Are claims backed by signal evidence?",
    )
    causal_clarity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Is the causal chain logical and clear?",
    )
    actionability: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Can a human act on this brief immediately?",
    )
    completeness: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Are all major risk categories addressed?",
    )

    # Weighted overall score
    overall: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Weighted average quality score",
    )

    # Agents whose output scored lowest (candidates for optimisation)
    weak_agents: list[str] = Field(
        default_factory=list,
        description="Agent names that contributed to low-quality sections",
    )

    # Specific notes on what was weak (used to guide PromptOptimiser)
    improvement_notes: list[str] = Field(
        default_factory=list,
        description="Specific issues to fix in prompt rewriting",
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def compute_overall(
        cls,
        specificity: float,
        evidence_depth: float,
        causal_clarity: float,
        actionability: float,
        completeness: float,
    ) -> float:
        """Compute weighted average from the 5 dimension scores.

        Weights:
            specificity    0.25
            evidence_depth 0.20
            causal_clarity 0.20
            actionability  0.25
            completeness   0.10
        """
        return round(
            specificity * 0.25
            + evidence_depth * 0.20
            + causal_clarity * 0.20
            + actionability * 0.25
            + completeness * 0.10,
            4,
        )

    def to_payload(self) -> dict:
        """Convert to dict for storage."""
        return {
            "id": self.id,
            "brief_id": self.brief_id,
            "specificity": self.specificity,
            "evidence_depth": self.evidence_depth,
            "causal_clarity": self.causal_clarity,
            "actionability": self.actionability,
            "completeness": self.completeness,
            "overall": self.overall,
            "weak_agents": self.weak_agents,
            "improvement_notes": self.improvement_notes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict) -> QualityScore:
        """Reconstruct from stored dict."""
        data = dict(payload)
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)
