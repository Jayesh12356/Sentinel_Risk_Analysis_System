"""Brief — executive intelligence brief produced by BriefWriter (Layer 4).

This is the final output of the SENTINEL pipeline: a structured,
human-readable report that aggregates signals, risk assessments, and
deliberation results into an actionable executive summary.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from sentinel.models.signal import SignalPriority


class BriefSection(BaseModel):
    """A single section within the executive brief."""

    heading: str = Field(..., description="Section heading")
    content: str = Field(..., description="Section body text (markdown)")
    priority: SignalPriority = Field(
        default=SignalPriority.P3,
        description="Highest priority of signals covered in this section",
    )


class AlertItem(BaseModel):
    """A top-level actionable alert surfaced in the brief."""

    signal_id: str = Field(..., description="Originating signal ID")
    risk_report_id: str = Field(..., description="Associated risk report ID")
    title: str = Field(..., description="Alert headline")
    priority: SignalPriority = Field(..., description="Alert priority")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Arbiter confidence"
    )
    recommended_action: str = Field(
        default="", description="Recommended response action"
    )


class Brief(BaseModel):
    """Executive intelligence brief — final SENTINEL pipeline output.

    Aggregates multiple signals and risk reports into one structured
    document with prioritised alerts and actionable recommendations.
    """

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique brief identifier",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Brief creation timestamp"
    )

    # --- Content ---
    title: str = Field(
        default="SENTINEL Intelligence Brief",
        description="Brief title / headline",
    )
    executive_summary: str = Field(
        default="", description="High-level executive summary (markdown)"
    )
    sections: list[BriefSection] = Field(
        default_factory=list, description="Detailed analysis sections"
    )
    alerts: list[AlertItem] = Field(
        default_factory=list, description="Prioritised actionable alerts"
    )

    # --- Lineage ---
    signal_ids: list[str] = Field(
        default_factory=list, description="IDs of all signals included"
    )
    risk_report_ids: list[str] = Field(
        default_factory=list, description="IDs of all risk reports included"
    )

    # --- Metadata ---
    highest_priority: SignalPriority = Field(
        default=SignalPriority.P3,
        description="Highest priority across all alerts in this brief",
    )
    total_signals: int = Field(
        default=0, description="Number of signals covered"
    )
    demo: bool = Field(
        default=False, description="True if generated from demo-mode data"
    )

    # --- Memory (Level 3) ---
    recurring_patterns: list[str] = Field(
        default_factory=list,
        description="Recurring threat patterns detected (e.g. 'Apache — 3 events in 90 days')",
    )
    memory_context: list[str] = Field(
        default_factory=list,
        description="Past event titles that informed this analysis",
    )

    # --- Predictive Intelligence (Level 7) ---
    predicted_threats: list[dict] = Field(
        default_factory=list,
        description="High-probability forecasts (prob>0.60) predicted to escalate. "
                    "Each item: {signal_title, current_priority, predicted_priority, probability, horizon, reasoning}",
    )
    forecast_count: int = Field(
        default=0,
        description="Total number of active forecasts for this pipeline run",
    )

    # --- Autonomous Actions (Level 8) ---
    actions_taken: list[dict] = Field(
        default_factory=list,
        description="Actions that were AUTO_EXECUTED this run. "
                    "Each item: {action_type, title, description, confidence, result}",
    )
    actions_pending: list[dict] = Field(
        default_factory=list,
        description="Actions awaiting human approval (PENDING_APPROVAL). "
                    "Each item: {id, action_type, title, description, confidence, reasoning}",
    )
    actions_report_only: list[dict] = Field(
        default_factory=list,
        description="Low-confidence actions logged as REPORT_ONLY. "
                    "Each item: {action_type, title, reasoning, confidence}",
    )
