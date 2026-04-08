"""PipelineState — shared state definition for the LangGraph pipeline.

This TypedDict flows through all 13 agent nodes.  Each agent reads
what it needs and writes its outputs back into the state.
"""

from __future__ import annotations

from typing import TypedDict, Optional

from sentinel.models.brief import Brief
from sentinel.models.forecast_entry import ForecastEntry
from sentinel.models.memory_entry import MemoryEntry
from sentinel.models.quality_score import QualityScore
from sentinel.models.risk_report import RiskReport
from sentinel.models.route_decision import RouteDecision
from sentinel.models.signal import Signal
from sentinel.tenants.context import TenantContext


class PipelineState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes.

    Fields are populated progressively as the pipeline advances:
      Layer 0 → signals
      Layer 1 → enriched signals (entities, priority, confidence)
      Layer 1.5 → route_decisions (RouterAgent)
      Layer 2 → risk_reports (scores, causal chains)
      Layer 3 → deliberation results update risk_reports
      Layer 4 → brief
      Layer 5 → memory_entries (MemoryWriter)
    """

    # --- Layer 0: Sensor outputs ---
    signals: list[Signal]

    # --- Layer 1: Processing enrichment ---
    # (EntityExtractor / SignalClassifier mutate signals in-place)

    # --- Layer 1.5: Routing decisions (Level 2) ---
    route_decisions: list[RouteDecision]

    # --- Layer 2: Reasoning outputs ---
    risk_reports: list[RiskReport]

    # --- Layer 3: Deliberation ---
    # (Red/Blue/Arbiter update risk_reports in-place)

    # --- Layer 4: Final output ---
    brief: Brief | None

    # --- Layer 4b: Quality scoring (Level 4) ---
    quality_score: Optional[QualityScore]

    # --- Layer 5: Memory persistence (Level 3) ---
    memory_entries: list[MemoryEntry]

    # --- Pipeline control ---
    loop1_count: int          # How many times Loop 1 has re-run
    loop1_max: int            # Max Loop 1 iterations (default 2)
    loop2_count: int          # How many times Loop 2 has re-run
    loop2_max: int            # Max Loop 2 iterations (default 1)
    pipeline_status: str      # "running" | "completed" | "error"
    error: str                # Last error message, if any

    # --- Level 6: Tenant isolation (optional, defaults via TenantContext.default()) ---
    tenant_context: TenantContext     # Per-tenant Qdrant collection names + profile

    # --- Level 6: Shared intelligence (populated by SharedPatternReader) ---
    shared_patterns: list             # List[SharedPattern] — cross-company patterns

    # --- Level 7: Predictive intelligence (populated by WeakSignalDetector + ForecastAgent) ---
    weak_signal_flags: dict           # Dict[signal_id, List[str]] — pre-pipeline weak signal flags
    forecasts: list[ForecastEntry]   # Populated by ForecastAgent after SignalClassifier

    # --- Level 8: Autonomous actions (populated by ActionPlanner) ---
    actions: list                     # List[ActionEntry] — actions planned/executed/pending

    # --- Level 10: Meta + Governance (populated by agents) ---
    health_events: list               # List[AgentHealthEvent] — emitted by each agent
    run_counter: int                  # Pipeline run counter for MetaAgent scheduling
