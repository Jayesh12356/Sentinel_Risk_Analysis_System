"""LangGraph pipeline — StateGraph with all 21 agent nodes (Level 10).

Pipeline flow (Level 10 with meta monitoring):
  START → WeakSignalDetector → TenantLoader → SharedPatternReader
        → 3 sensors → EntityExtractor → SignalClassifier → [Loop 1]
        → ForecastAgent → RouterAgent → [Route check]
            Path A (FULL)     → RiskAssessor → CausalChain → RedTeam
                                → BlueTeam → Arbiter → [Loop 2]
                                → ActionPlanner → BriefWriter
            Path B (FAST)     → RiskAssessor → BriefWriter
            Path C (LOG_ONLY) → BriefWriter
        → QualityAgent → MemoryWriter → SharedPatternWriter
        → MetaWriter → END
        → (background) ForecastOutcomeTracker + FeedbackAgent + MetaAgent (every N runs)

All 21 nodes (20 Level 1-9 + MetaWriter).
Loop 1: confidence < 0.5 → re-process through EntityExtractor/SignalClassifier
Loop 2: Red Team wins → escalate priority, re-run RiskAssessor"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from langgraph.graph import END, START, StateGraph

from sentinel.config import get_settings
from sentinel.pipeline.state import PipelineState
from sentinel.tenants.context import TenantContext

# ── Agent imports ────────────────────────────────────────────────────────
from sentinel.agents.layer0_sensors.news_scanner import NewsScanner
from sentinel.agents.layer0_sensors.cyber_threat import CyberThreatAgent
from sentinel.agents.layer0_sensors.financial_signal import FinancialSignalAgent
from sentinel.agents.layer1_processing.entity_extractor import EntityExtractor
from sentinel.agents.layer1_processing.signal_classifier import SignalClassifier
from sentinel.agents.layer1_processing.forecast_agent import ForecastAgent  # Level 7
from sentinel.agents.layer1_processing.router import RouterAgent
from sentinel.agents.layer2_reasoning.risk_assessor import RiskAssessor
from sentinel.agents.layer2_reasoning.causal_chain import CausalChainBuilder
from sentinel.agents.layer3_deliberation.red_team import RedTeamAgent
from sentinel.agents.layer3_deliberation.blue_team import BlueTeamAgent
from sentinel.agents.layer3_deliberation.arbiter import ArbiterAgent
from sentinel.agents.layer3_deliberation.action_planner import ActionPlanner  # Level 8
from sentinel.agents.layer4_output.brief_writer import BriefWriter
from sentinel.agents.layer4_output.quality_agent import QualityAgent
from sentinel.memory.writer import write_memory_entry
from sentinel.models.route_decision import RoutePath
from sentinel.forecast import weak_signal_detector  # Level 7

logger = structlog.get_logger(__name__)

# ── Pipeline limits ──────────────────────────────────────────────────────
MAX_SIGNALS_PER_RUN = 10  # Cap signals processed per run (demo guard)

# ── Node name constants ──────────────────────────────────────────────────

NEWS_SCANNER = "news_scanner"
CYBER_THREAT = "cyber_threat"
FINANCIAL_SIGNAL = "financial_signal"
ENTITY_EXTRACTOR = "entity_extractor"
SIGNAL_CLASSIFIER = "signal_classifier"
FORECAST_AGENT = "forecast_agent"              # Level 7: predictive intelligence
ROUTER = "router"
RISK_ASSESSOR = "risk_assessor"
CAUSAL_CHAIN = "causal_chain"
RED_TEAM = "red_team"
BLUE_TEAM = "blue_team"
ARBITER = "arbiter"
BRIEF_WRITER = "brief_writer"
QUALITY_AGENT = "quality_agent"
MEMORY_WRITER = "memory_writer"
TENANT_LOADER = "tenant_loader"                # Level 6: load TenantContext
SHARED_PATTERN_READER = "shared_pattern_reader"  # Level 6: read cross-tenant patterns
SHARED_PATTERN_WRITER = "shared_pattern_writer"  # Level 6: write anonymised patterns
WEAK_SIGNAL_DETECTOR = "weak_signal_detector"  # Level 7: pre-pipeline heuristic flags
ACTION_PLANNER = "action_planner"              # Level 8: autonomous action planning
META_WRITER = "meta_writer"                    # Level 10: health events + governance writer

# ── Agent instances (created once, reused across pipeline runs) ──────────

_settings = None


def _get_settings():
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings


def _make_agent(cls):
    """Instantiate an agent with current demo_mode setting."""
    return cls(demo_mode=_get_settings().demo_mode)


# ── Node wrapper functions (delegate to real agents) ─────────────────────


async def _news_scanner(state: dict[str, Any]) -> dict[str, Any]:
    """Run NewsScanner agent."""
    agent = _make_agent(NewsScanner)
    return await agent.run(state)


async def _cyber_threat(state: dict[str, Any]) -> dict[str, Any]:
    """Run CyberThreatAgent."""
    agent = _make_agent(CyberThreatAgent)
    return await agent.run(state)


async def _financial_signal(state: dict[str, Any]) -> dict[str, Any]:
    """Run FinancialSignalAgent."""
    agent = _make_agent(FinancialSignalAgent)
    return await agent.run(state)


async def _entity_extractor(state: dict[str, Any]) -> dict[str, Any]:
    """Run EntityExtractor agent (with signal cap guard)."""
    signals = state.get("signals", [])
    if len(signals) > MAX_SIGNALS_PER_RUN:
        logger.warning(
            "pipeline.signal_cap",
            original=len(signals),
            capped=MAX_SIGNALS_PER_RUN,
        )
        state["signals"] = signals[:MAX_SIGNALS_PER_RUN]
    agent = _make_agent(EntityExtractor)
    return await agent.run(state)


async def _signal_classifier(state: dict[str, Any]) -> dict[str, Any]:
    """Run SignalClassifier agent."""
    agent = _make_agent(SignalClassifier)
    return await agent.run(state)


async def _forecast_agent(state: dict[str, Any]) -> dict[str, Any]:  # Level 7
    """Run ForecastAgent — predict P2/P3 escalation probability (thinking=ON)."""
    agent = _make_agent(ForecastAgent)
    return await agent.run(state)


async def _router(state: dict[str, Any]) -> dict[str, Any]:
    """Run RouterAgent (Level 2 — dynamic path routing)."""
    agent = _make_agent(RouterAgent)
    return await agent.run(state)


async def _risk_assessor(state: dict[str, Any]) -> dict[str, Any]:
    """Run RiskAssessor agent."""
    agent = _make_agent(RiskAssessor)
    return await agent.run(state)


async def _causal_chain(state: dict[str, Any]) -> dict[str, Any]:
    """Run CausalChainBuilder agent."""
    agent = _make_agent(CausalChainBuilder)
    return await agent.run(state)


async def _red_team(state: dict[str, Any]) -> dict[str, Any]:
    """Run RedTeamAgent."""
    agent = _make_agent(RedTeamAgent)
    return await agent.run(state)


async def _blue_team(state: dict[str, Any]) -> dict[str, Any]:
    """Run BlueTeamAgent."""
    agent = _make_agent(BlueTeamAgent)
    return await agent.run(state)


async def _arbiter(state: dict[str, Any]) -> dict[str, Any]:
    """Run ArbiterAgent."""
    agent = _make_agent(ArbiterAgent)
    return await agent.run(state)


async def _action_planner(state: dict[str, Any]) -> dict[str, Any]:  # Level 8
    """Run ActionPlanner — confidence-gated autonomous actions (thinking=ON)."""
    agent = _make_agent(ActionPlanner)
    return await agent.run(state)


async def _brief_writer(state: dict[str, Any]) -> dict[str, Any]:
    """Run BriefWriter agent."""
    agent = _make_agent(BriefWriter)
    return await agent.run(state)


async def _quality_agent(state: dict[str, Any]) -> dict[str, Any]:
    """Run QualityAgent — score the brief (Level 4)."""
    agent = _make_agent(QualityAgent)
    return await agent.run(state)


async def _memory_writer(state: dict[str, Any]) -> dict[str, Any]:
    """Write processed signals to long-term memory (Level 3).

    Level 6: reads memory collection from tenant_context if present.
    """
    signals = state.get("signals", [])
    reports = state.get("risk_reports", [])
    decisions = state.get("route_decisions", [])

    # Resolve tenant-scoped memory collection (Level 6) or fall back to settings
    tenant_ctx = state.get("tenant_context")
    if tenant_ctx and hasattr(tenant_ctx, "memory_collection"):
        memory_collection = tenant_ctx.memory_collection
    else:
        memory_collection = get_settings().QDRANT_MEMORY_COLLECTION

    # Build lookup maps
    report_map = {}
    for r in reports:
        if hasattr(r, "signal_id"):
            report_map[str(r.signal_id)] = r

    decision_map = {}
    for d in decisions:
        if hasattr(d, "signal_id"):
            decision_map[str(d.signal_id)] = d

    entries = []
    for signal in signals:
        sid = str(signal.id)
        report = report_map.get(sid)
        decision = decision_map.get(sid)
        try:
            entry = await write_memory_entry(signal, report, decision, collection_name=memory_collection)
            entries.append(entry)
        except Exception:
            logger.exception("memory_writer.signal_error", signal_id=sid)

    logger.info("memory_writer.complete", entries_written=len(entries))
    return {"memory_entries": entries}


async def _shared_pattern_reader(state: dict[str, Any]) -> dict[str, Any]:
    """SharedPatternReader — query cross-tenant patterns before sensor agents (Level 6).

    Runs after TENANT_LOADER.  Results stored in state['shared_patterns']
    and later injected into CausalChainBuilder prompt context.
    """
    try:
        from sentinel.shared.pattern_reader import get_patterns_for_signals
        # At this point signals haven't been collected yet, so we do a single
        # query using a broad context string — more granular query happens in CausalChain
        patterns = await get_patterns_for_signals(signals=[], limit_per_signal=5)
        logger.info("shared_pattern_reader.done", patterns=len(patterns))
        return {"shared_patterns": patterns}
    except Exception as exc:
        logger.warning("shared_pattern_reader.error", error=str(exc))
        return {"shared_patterns": []}


async def _shared_pattern_writer(state: dict[str, Any]) -> dict[str, Any]:
    """SharedPatternWriter — anonymise signals and write to shared collection (Level 6).

    Runs after MEMORY_WRITER.  Non-blocking writes — errors are logged but not raised.
    """
    try:
        from sentinel.shared.pattern_writer import write_patterns_for_run
        signals = state.get("signals", [])
        tenant_ctx = state.get("tenant_context")
        company_profile = {}
        if tenant_ctx and hasattr(tenant_ctx, "company_profile"):
            company_profile = tenant_ctx.company_profile

        patterns = await write_patterns_for_run(
            signals=signals,
            company_profile=company_profile,
        )
        logger.info("shared_pattern_writer.done", patterns_written=len(patterns))
    except Exception as exc:
        logger.warning("shared_pattern_writer.error", error=str(exc))
    return {}


async def _weak_signal_detector(state: dict[str, Any]) -> dict[str, Any]:  # Level 7
    """WeakSignalDetector — pre-pipeline heuristic flagging (no LLM, pure Python).

    Runs BEFORE sensors so flags are available to ForecastAgent.
    At START, signals haven't been collected yet, so we pre-initialize the
    state fields and the actual detection happens post-sensor in ForecastAgent.
    """
    # At pipeline start, signals list is empty.
    # Initialize weak_signal_flags and forecasts in state.
    # The actual detect() call will happen inside ForecastAgent once signals exist.
    logger.info("weak_signal_detector.init", note="flags will be populated after sensor stage")
    return {
        "weak_signal_flags": {},    # Will be populated by ForecastAgent after signals are collected
        "forecasts": [],            # Will be populated by ForecastAgent
    }


# ── Conditional edge functions ───────────────────────────────────────────


def _loop1_check(state: PipelineState) -> str:
    """Loop 1: if any signal confidence < 0.5, re-process.

    Returns the next node name for LangGraph conditional routing.
    """
    loop_count = state.get("loop1_count", 0)
    loop_max = state.get("loop1_max", 2)

    if loop_count >= loop_max:
        logger.info("loop1.max_reached", count=loop_count)
        return ROUTER

    signals = state.get("signals", [])
    low_confidence = any(
        s.confidence < 0.5 for s in signals if hasattr(s, "confidence")
    )

    if low_confidence:
        logger.info("loop1.triggered", count=loop_count)
        return ENTITY_EXTRACTOR

    logger.info("loop1.passed")
    return ROUTER


def _route_check(state: PipelineState) -> str:
    """Route check: determine which pipeline path to follow.

    Examines route_decisions to pick the dominant path:
      - If ANY signal is FULL → go full pipeline (Path A)
      - Else if ANY is FAST → go fast pipeline (Path B)
      - Else → log only (Path C)
    """
    decisions = state.get("route_decisions", [])

    if not decisions:
        logger.warning("route_check.no_decisions, defaulting to FULL")
        return RISK_ASSESSOR

    has_full = any(d.path == RoutePath.FULL for d in decisions)
    has_fast = any(d.path == RoutePath.FAST for d in decisions)

    if has_full:
        logger.info("route_check.path_a_full")
        return RISK_ASSESSOR
    elif has_fast:
        logger.info("route_check.path_b_fast")
        return RISK_ASSESSOR
    else:
        logger.info("route_check.path_c_log_only")
        return BRIEF_WRITER


def _post_risk_assessor_check(state: PipelineState) -> str:
    """After RiskAssessor: decide whether to continue to full deliberation
    or skip directly to BriefWriter (Path B fast pipeline).

    If any route decision is FULL → continue to CausalChain (Path A)
    Otherwise → skip to BriefWriter (Path B)
    """
    decisions = state.get("route_decisions", [])
    has_full = any(d.path == RoutePath.FULL for d in decisions)

    if has_full:
        logger.info("post_risk.continue_full_pipeline")
        return CAUSAL_CHAIN
    else:
        logger.info("post_risk.skip_to_brief")
        return BRIEF_WRITER


def _loop2_check(state: PipelineState) -> str:
    """Loop 2: if Red Team wins debate, escalate and re-assess.

    Returns the next node name for LangGraph conditional routing.
    Level 8: passes to ACTION_PLANNER instead of BRIEF_WRITER.
    """
    loop_count = state.get("loop2_count", 0)
    loop_max = state.get("loop2_max", 1)

    if loop_count >= loop_max:
        logger.info("loop2.max_reached", count=loop_count)
        return ACTION_PLANNER   # Level 8: go to ActionPlanner first

    reports = state.get("risk_reports", [])
    red_wins = any(
        r.deliberation.red_team_wins
        for r in reports
        if hasattr(r, "deliberation")
    )

    if red_wins:
        logger.info("loop2.triggered", count=loop_count)
        return RISK_ASSESSOR

    logger.info("loop2.passed")
    return ACTION_PLANNER    # Level 8: go to ActionPlanner first


# ── Level 10: MetaWriter node ────────────────────────────────────────────


async def _meta_writer(state: dict[str, Any]) -> dict[str, Any]:
    """Level 10: Write health events, update run counter, trigger MetaAgent if due."""
    health_events = state.get("health_events", [])
    run_counter = state.get("run_counter", 0) + 1
    settings = get_settings()

    # Write collected health events
    if health_events and settings.META_ENABLED:
        try:
            from sentinel.meta.health_event import write_health_events
            await write_health_events(health_events)
        except Exception as exc:
            logger.warning("meta_writer.health_events_failed", error=str(exc))

    # Log pipeline completion to governance
    if settings.GOVERNANCE_ENABLED:
        try:
            from sentinel.meta.governance import log_event
            tenant_ctx = state.get("tenant_context")
            tenant_id = tenant_ctx.tenant_id if tenant_ctx else "default"
            signals = state.get("signals", [])
            await log_event(
                event_type="META_REPORT_GENERATED",
                agent_name="Pipeline",
                tenant_id=tenant_id,
                description=f"Pipeline run #{run_counter} completed with {len(signals)} signals",
                reasoning=f"Run counter: {run_counter}, health events: {len(health_events)}",
            )
        except Exception as exc:
            logger.warning("meta_writer.governance_failed", error=str(exc))

    # Trigger MetaAgent every N runs
    if settings.META_ENABLED and run_counter % settings.META_RUN_INTERVAL_RUNS == 0:
        try:
            import asyncio
            from sentinel.meta.meta_agent import MetaAgent
            tenant_ctx = state.get("tenant_context")
            tenant_id = tenant_ctx.tenant_id if tenant_ctx else "default"
            agent = MetaAgent()
            asyncio.create_task(agent.run(tenant_id=tenant_id))
            logger.info("meta_writer.meta_agent_triggered", run_counter=run_counter)
        except Exception as exc:
            logger.warning("meta_writer.meta_trigger_failed", error=str(exc))

    logger.info("meta_writer.done", run_counter=run_counter, events=len(health_events))
    return {"health_events": [], "run_counter": run_counter}


# ── Graph builder ────────────────────────────────────────────────────────


def build_graph(tenant_id: Optional[str] = None) -> StateGraph:
    """Construct the full SENTINEL LangGraph pipeline (Level 6).

    Args:
        tenant_id: Optional tenant slug. If None, uses ACTIVE_TENANT from settings.
                   Pass "default" for backward-compatible Level 1–5 behaviour.

    Returns an uncompiled StateGraph with all nodes and 3 routing paths.
    """

    # Resolve which tenant to run for — captured at graph-build time
    _tenant_id = tenant_id or get_settings().ACTIVE_TENANT

    async def _tenant_loader(state: dict[str, Any]) -> dict[str, Any]:
        """Load TenantContext from registry and inject into state."""
        # Try registry first, fall back to constructing from tenant_id
        try:
            from sentinel.tenants.manager import get_tenant
            tenant = await get_tenant(_tenant_id)
            if tenant:
                ctx = TenantContext.from_tenant_id(_tenant_id)
                ctx = ctx.model_copy(update={"tenant_name": tenant.name})
                # Load company profile if available
                import json, os
                profile_path = tenant.profile_path
                if os.path.exists(profile_path):
                    with open(profile_path, encoding="utf-8") as f:
                        ctx = ctx.model_copy(update={"company_profile": json.load(f)})
            else:
                # Unknown tenant_id — use dynamic context
                ctx = TenantContext.from_tenant_id(_tenant_id)
        except Exception as exc:
            logger.warning("tenant_loader.error", error=str(exc), tenant_id=_tenant_id)
            ctx = TenantContext.from_tenant_id(_tenant_id)

        logger.info(
            "tenant_loader.ok",
            tenant_id=ctx.tenant_id,
            signals_collection=ctx.signals_collection,
            memory_collection=ctx.memory_collection,
        )
        return {"tenant_context": ctx, "shared_patterns": []}

    graph = StateGraph(PipelineState)

    # ── Register all 20 nodes (19 Level 1-7 + ActionPlanner) ─
    graph.add_node(WEAK_SIGNAL_DETECTOR, _weak_signal_detector)         # Level 7: pre-filter
    graph.add_node(TENANT_LOADER, _tenant_loader)                       # Level 6: context
    graph.add_node(SHARED_PATTERN_READER, _shared_pattern_reader)       # Level 6: pre-sensing
    graph.add_node(NEWS_SCANNER, _news_scanner)
    graph.add_node(CYBER_THREAT, _cyber_threat)
    graph.add_node(FINANCIAL_SIGNAL, _financial_signal)
    graph.add_node(ENTITY_EXTRACTOR, _entity_extractor)
    graph.add_node(SIGNAL_CLASSIFIER, _signal_classifier)
    graph.add_node(FORECAST_AGENT, _forecast_agent)                     # Level 7: after classifier
    graph.add_node(ROUTER, _router)
    graph.add_node(RISK_ASSESSOR, _risk_assessor)
    graph.add_node(CAUSAL_CHAIN, _causal_chain)
    graph.add_node(RED_TEAM, _red_team)
    graph.add_node(BLUE_TEAM, _blue_team)
    graph.add_node(ARBITER, _arbiter)
    graph.add_node(ACTION_PLANNER, _action_planner)                     # Level 8: after arbiter
    graph.add_node(BRIEF_WRITER, _brief_writer)
    graph.add_node(QUALITY_AGENT, _quality_agent)
    graph.add_node(MEMORY_WRITER, _memory_writer)
    graph.add_node(SHARED_PATTERN_WRITER, _shared_pattern_writer)       # Level 6: post-memory
    graph.add_node(META_WRITER, _meta_writer)                           # Level 10: health + governance

    # ── Linear edges: START → weak_signal_detector → tenant_loader → shared_pattern_reader → sensors ─
    graph.add_edge(START, WEAK_SIGNAL_DETECTOR)                           # Level 7: pre-filter first
    graph.add_edge(WEAK_SIGNAL_DETECTOR, TENANT_LOADER)                   # Level 6 context second
    graph.add_edge(TENANT_LOADER, SHARED_PATTERN_READER)                  # Level 6: pre-fetch patterns
    graph.add_edge(SHARED_PATTERN_READER, NEWS_SCANNER)                   # then sensors start
    graph.add_edge(NEWS_SCANNER, CYBER_THREAT)
    graph.add_edge(CYBER_THREAT, FINANCIAL_SIGNAL)
    graph.add_edge(FINANCIAL_SIGNAL, ENTITY_EXTRACTOR)
    graph.add_edge(ENTITY_EXTRACTOR, SIGNAL_CLASSIFIER)

    # ── Loop 1: after SignalClassifier → check confidence ────────────
    #    Routes to FORECAST_AGENT (not ROUTER directly) on pass
    graph.add_conditional_edges(
        SIGNAL_CLASSIFIER,
        _loop1_check,
        {
            ENTITY_EXTRACTOR: ENTITY_EXTRACTOR,
            ROUTER: FORECAST_AGENT,   # Loop 1 pass now goes through ForecastAgent first
        },
    )

    # ── ForecastAgent → Router (Level 7) ─────────────────────────────
    graph.add_edge(FORECAST_AGENT, ROUTER)

    # ── Route check: after RouterAgent → Path A/B/C ──────────────────
    graph.add_conditional_edges(
        ROUTER,
        _route_check,
        {
            RISK_ASSESSOR: RISK_ASSESSOR,   # Path A or B → both go to RiskAssessor
            BRIEF_WRITER: BRIEF_WRITER,     # Path C → skip everything
        },
    )

    # ── After RiskAssessor → full pipeline or skip to brief ──────────
    graph.add_conditional_edges(
        RISK_ASSESSOR,
        _post_risk_assessor_check,
        {
            CAUSAL_CHAIN: CAUSAL_CHAIN,     # Path A → continue deliberation
            BRIEF_WRITER: BRIEF_WRITER,     # Path B → skip deliberation
        },
    )

    # ── Linear edges: reasoning → deliberation (Path A only) ─────────
    graph.add_edge(CAUSAL_CHAIN, RED_TEAM)
    graph.add_edge(RED_TEAM, BLUE_TEAM)
    graph.add_edge(BLUE_TEAM, ARBITER)

    # ── Loop 2: after Arbiter → check Red Team verdict ──────────────
    #    Level 8: Loop 2 now routes to ACTION_PLANNER instead of BRIEF_WRITER
    graph.add_conditional_edges(
        ARBITER,
        _loop2_check,
        {
            RISK_ASSESSOR: RISK_ASSESSOR,
            ACTION_PLANNER: ACTION_PLANNER,     # Level 8: action planning
        },
    )

    # ── ActionPlanner → BriefWriter (Level 8) ────────────────────────
    graph.add_edge(ACTION_PLANNER, BRIEF_WRITER)

    # ── Final edges: BriefWriter → QualityAgent → MemoryWriter → SharedPatternWriter → MetaWriter → END
    graph.add_edge(BRIEF_WRITER, QUALITY_AGENT)
    graph.add_edge(QUALITY_AGENT, MEMORY_WRITER)
    graph.add_edge(MEMORY_WRITER, SHARED_PATTERN_WRITER)             # Level 6: write patterns
    graph.add_edge(SHARED_PATTERN_WRITER, META_WRITER)               # Level 10: health + governance
    graph.add_edge(META_WRITER, END)

    logger.info("pipeline.graph.built", nodes=21, loops=2, routing_paths=3)
    return graph


def compile_graph():
    """Build and compile the pipeline graph for execution."""
    graph = build_graph()
    return graph.compile()


def _trigger_feedback_agent_async() -> None:
    """Fire FeedbackAgent as a background asyncio task.

    Called from the pipeline run after MemoryWriter completes.
    Non-blocking — does not add latency to the pipeline.
    """
    async def _run():
        try:
            from sentinel.agents.feedback.feedback_agent import FeedbackAgent
            agent = FeedbackAgent()
            result = await agent.run()
            import structlog as _slog
            _slog.get_logger(__name__).info("feedback_agent.background.done", result=result)
        except Exception as exc:
            import structlog as _slog
            _slog.get_logger(__name__).warning("feedback_agent.background.error", error=str(exc))

    import asyncio
    try:
        asyncio.create_task(_run())
    except RuntimeError:
        # No running event loop — skip silently (test environments)
        pass
