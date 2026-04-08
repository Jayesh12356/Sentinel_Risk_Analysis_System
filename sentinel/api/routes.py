"""SENTINEL API routes — FastAPI endpoints for the risk intelligence system.

Implements all endpoints from CONTEXT.md:
  GET  /health           → system status
  POST /ingest           → trigger manual ingestion (pipeline run)
  GET  /alerts           → list all alerts by priority
  GET  /alerts/{id}      → single alert detail
  GET  /briefs           → list all briefs
  GET  /briefs/latest    → most recent brief
  GET  /briefs/{id}      → single brief detail
  GET  /pipeline/status  → current pipeline run status
  POST /alerts/test      → fire a test alert (Level 3)
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException

from sentinel.config import get_settings
from sentinel.models.brief import Brief
from sentinel.models.signal import SignalPriority

logger = structlog.get_logger(__name__)

router = APIRouter()

# ── In-memory stores (replaced by DB in production) ──────────────────────
# These hold pipeline results between runs.
_briefs: list[Brief] = []
_risk_reports: list[Any] = []  # RiskReport objects from pipeline runs
_quality_scores: list[Any] = []  # QualityScore objects from pipeline runs (Level 4)
_actions: list[Any] = []  # Level 8: ActionEntry objects from pipeline runs
_pipeline_status: dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "current_node": None,
    "demo_mode": False,
    "signal_count": 0,
    "report_count": 0,
    "error": None,
}


def _get_all_alerts() -> list[dict[str, Any]]:
    """Extract all alert items from stored briefs, most recent first."""
    # Build risk report lookup for company match data
    report_map: dict[str, Any] = {}
    for report in _risk_reports:
        if hasattr(report, "signal_id"):
            report_map[report.signal_id] = report

    alerts: list[dict[str, Any]] = []
    for brief in reversed(_briefs):
        for alert in brief.alerts:
            # Look up company match data from risk report
            report = report_map.get(alert.signal_id)
            company_matches = []
            relevance_score = 0.0
            if report and hasattr(report, "company_matches"):
                company_matches = report.company_matches
                relevance_score = report.relevance_score

            alerts.append(
                {
                    "id": f"{alert.signal_id}_{alert.risk_report_id}",
                    "signal_id": alert.signal_id,
                    "risk_report_id": alert.risk_report_id,
                    "title": alert.title,
                    "priority": alert.priority.value,
                    "confidence": alert.confidence,
                    "recommended_action": alert.recommended_action,
                    "brief_id": brief.id,
                    "created_at": brief.created_at.isoformat(),
                    "run_timestamp": brief.created_at.isoformat(),
                    "run_signal_count": brief.total_signals,
                    "company_matches": company_matches,
                    "relevance_score": relevance_score,
                }
            )
    # Sort by priority (P0 first)
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    alerts.sort(key=lambda a: priority_order.get(a["priority"], 99))
    return alerts


# ── Health ────────────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict[str, Any]:
    """System health status."""
    settings = get_settings()
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "demo_mode": settings.demo_mode,
        "model": settings.SENTINEL_PRIMARY_MODEL,
        "version": "0.1.0",
    }


# ── Pipeline ──────────────────────────────────────────────────────────────

@router.get("/pipeline/status")
async def pipeline_status() -> dict[str, Any]:
    """Current pipeline run status."""
    return _pipeline_status


@router.post("/ingest")
async def ingest(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Trigger a pipeline run (manual ingestion).

    Runs the full LangGraph pipeline in the background. Returns
    immediately with the pipeline status.
    """
    global _pipeline_status

    if _pipeline_status["status"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline already running")

    _pipeline_status = {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
        "current_node": "starting",
        "demo_mode": get_settings().demo_mode,
        "signal_count": 0,
        "report_count": 0,
        "error": None,
    }

    background_tasks.add_task(_run_pipeline)

    return {"status": "started", "message": "Pipeline ingestion triggered"}


async def _run_pipeline() -> None:
    """Execute the full SENTINEL pipeline."""
    global _pipeline_status

    try:
        from sentinel.pipeline.graph import compile_graph

        graph = compile_graph()

        # Run the compiled graph with initial state
        # LangGraph 0.2.x requires __start__ input to contain valid state keys
        _pipeline_status["current_node"] = "sensors"
        initial_state = {
            "signals": [],
            "risk_reports": [],
            "route_decisions": [],
            "brief": None,
            "quality_score": None,
            "actions": [],
            "loop1_count": 0,
            "loop1_max": 2,
            "loop2_count": 0,
            "loop2_max": 1,
            "pipeline_status": "running",
            "error": "",
        }
        result = await graph.ainvoke(initial_state)

        # Extract brief and risk reports from result
        brief = result.get("brief")
        if brief and isinstance(brief, Brief):
            _briefs.append(brief)

        # Capture quality score (Level 4)
        qs = result.get("quality_score")
        if qs is not None:
            _quality_scores.append(qs)

        # Store risk reports for /company/profile/matches endpoint
        reports = result.get("risk_reports", [])
        if reports:
            _risk_reports.extend(reports)

        # Store actions for Level 8 /actions endpoints
        actions = result.get("actions", [])
        if actions:
            _actions.extend(actions)

        _pipeline_status.update(
            {
                "status": "completed",
                "finished_at": datetime.utcnow().isoformat(),
                "current_node": None,
                "signal_count": len(result.get("signals", [])),
                "report_count": len(result.get("risk_reports", [])),
            }
        )
        logger.info(
            "pipeline.completed",
            signal_count=_pipeline_status["signal_count"],
            report_count=_pipeline_status["report_count"],
        )

    except Exception as exc:
        logger.exception("pipeline.error")
        _pipeline_status.update(
            {
                "status": "error",
                "finished_at": datetime.utcnow().isoformat(),
                "current_node": None,
                "error": str(exc),
            }
        )


# ── Alerts ────────────────────────────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    priority: str | None = None,
) -> dict[str, Any]:
    """List all alerts, optionally filtered by priority."""
    alerts = _get_all_alerts()

    if priority:
        priority_upper = priority.upper()
        alerts = [a for a in alerts if a["priority"] == priority_upper]

    return {"alerts": alerts, "total": len(alerts)}


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str) -> dict[str, Any]:
    """Get a single alert by ID."""
    alerts = _get_all_alerts()
    for alert in alerts:
        if alert["id"] == alert_id:
            return alert

    raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")


# ── Briefs ────────────────────────────────────────────────────────────────

@router.get("/briefs")
async def list_briefs() -> dict[str, Any]:
    """List all briefs (summary view)."""
    summaries = [
        {
            "id": b.id,
            "title": b.title,
            "created_at": b.created_at.isoformat(),
            "highest_priority": b.highest_priority.value,
            "total_signals": b.total_signals,
            "alert_count": len(b.alerts),
            "demo": b.demo,
        }
        for b in reversed(_briefs)
    ]
    return {"briefs": summaries, "total": len(summaries)}


@router.get("/briefs/latest")
async def get_latest_brief() -> dict[str, Any]:
    """Get the most recent brief (full detail)."""
    if not _briefs:
        raise HTTPException(status_code=404, detail="No briefs available yet")

    brief = _briefs[-1]
    return brief.model_dump(mode="json")


@router.get("/briefs/{brief_id}")
async def get_brief(brief_id: str) -> dict[str, Any]:
    """Get a single brief by ID (full detail)."""
    for brief in _briefs:
        if brief.id == brief_id:
            return brief.model_dump(mode="json")

    raise HTTPException(status_code=404, detail=f"Brief {brief_id} not found")


# ── Company Profile (Level 2) ────────────────────────────────────────────

@router.get("/company/profile")
async def get_company_profile() -> dict[str, Any]:
    """Return the active company profile."""
    from sentinel.profile.manager import get_active_profile

    profile = get_active_profile()
    return profile.model_dump(mode="json")


@router.put("/company/profile")
async def update_company_profile(body: dict[str, Any]) -> dict[str, Any]:
    """Replace the company profile entirely."""
    from sentinel.models.company_profile import CompanyProfile
    from sentinel.profile.manager import save_profile

    try:
        profile = CompanyProfile(**body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    saved = save_profile(profile)
    logger.info("api.company_profile.updated", name=saved.name)
    return saved.model_dump(mode="json")


@router.get("/company/profile/matches")
async def get_profile_matches() -> dict[str, Any]:
    """Return all signals/reports where company_matches is non-empty.

    Joins stored risk reports with brief alerts, sorted by relevance_score desc.
    """
    # Build alert lookup from all briefs
    alert_map: dict[str, dict[str, Any]] = {}
    for brief in _briefs:
        for alert in brief.alerts:
            alert_map[alert.signal_id] = {
                "title": alert.title,
                "priority": alert.priority.value,
                "confidence": alert.confidence,
                "brief_id": brief.id,
                "created_at": brief.created_at.isoformat(),
            }

    matches: list[dict[str, Any]] = []
    seen: set[str] = set()  # Deduplicate by report id

    for report in _risk_reports:
        if not hasattr(report, "company_matches") or not report.company_matches:
            continue
        if report.id in seen:
            continue
        seen.add(report.id)

        alert_info = alert_map.get(report.signal_id, {})
        matches.append({
            "signal_id": report.signal_id,
            "report_id": report.id,
            "brief_id": alert_info.get("brief_id", ""),
            "title": alert_info.get("title", "Unknown signal"),
            "priority": alert_info.get("priority", "P3"),
            "confidence": alert_info.get("confidence", 0.0),
            "relevance_score": report.relevance_score,
            "company_matches": report.company_matches,
            "summary": report.summary,
            "risk_score": report.risk_score.overall,
            "created_at": alert_info.get("created_at", ""),
        })

    # Sort by relevance_score descending
    matches.sort(key=lambda m: m.get("relevance_score", 0), reverse=True)

    return {"matches": matches, "total": len(matches)}


# ── Alert Dispatcher Test (Level 3) ─────────────────────────────────────

@router.post("/alerts/test")
async def test_alert():
    """Fire a test alert through the AlertDispatcher.

    Useful for verifying email/Slack/demo-mode dispatch works.
    """
    from sentinel.alerts.dispatcher import fire_alert

    result = await fire_alert(
        title="SENTINEL Test Alert",
        priority="P1",
        summary="This is a test alert from POST /alerts/test.",
        signal_id="test-signal-001",
        report_id="test-report-001",
        recommended_action="No action required — test alert.",
    )
    return {"message": "Test alert dispatched", "result": result}


# ── Memory API (Level 3) ────────────────────────────────────────────────

@router.get("/memory")
async def list_memories(limit: int = 20, offset: int = 0):
    """Paginated list of MemoryEntries from Qdrant."""
    from sentinel.db.qdrant_client import _get_client
    from sentinel.models.memory_entry import MemoryEntry

    settings = get_settings()
    collection = f"{settings.ACTIVE_TENANT}_memory"
    client = _get_client()

    # Check collection exists
    collections = await client.get_collections()
    existing = {c.name for c in collections.collections}
    if collection not in existing:
        return {"entries": [], "total": 0, "limit": limit, "offset": offset}

    # Scroll through collection
    result = await client.scroll(
        collection_name=collection,
        limit=limit,
        offset=offset if offset > 0 else None,
        with_payload=True,
        with_vectors=False,
    )

    points, next_offset = result
    entries = []
    for point in points:
        try:
            entry = MemoryEntry.from_payload(point.payload or {})
            entries.append(entry.to_payload())
        except Exception:
            pass

    # Sort by created_at descending
    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)

    return {
        "entries": entries,
        "total": len(entries),
        "limit": limit,
        "offset": offset,
    }


@router.get("/memory/search")
async def search_memories(q: str = "", limit: int = 10):
    """Semantic search over memory entries."""
    from sentinel.memory.retriever import get_relevant_memories

    if not q:
        return {"entries": [], "query": q, "total": 0}

    memories = await get_relevant_memories(
        query_text=q, limit=limit, days_back=365,
    )

    entries = [m.to_payload() for m in memories]
    return {"entries": entries, "query": q, "total": len(entries)}


@router.get("/memory/patterns")
async def memory_patterns():
    """Group memory entries by entity, count occurrences for pattern detection."""
    from sentinel.db.qdrant_client import _get_client
    from sentinel.models.memory_entry import MemoryEntry

    settings = get_settings()
    collection = f"{settings.ACTIVE_TENANT}_memory"
    client = _get_client()

    # Check collection exists
    collections = await client.get_collections()
    existing = {c.name for c in collections.collections}
    if collection not in existing:
        return {"patterns": [], "total_entries": 0}

    # Get all entries
    result = await client.scroll(
        collection_name=collection,
        limit=100,
        with_payload=True,
        with_vectors=False,
    )

    points, _ = result
    entity_counts: dict[str, int] = {}
    entity_details: dict[str, list[str]] = {}

    for point in points:
        payload = point.payload or {}
        entities = payload.get("entities", [])
        title = payload.get("title", "Unknown")
        for entity in entities:
            entity_counts[entity] = entity_counts.get(entity, 0) + 1
            if entity not in entity_details:
                entity_details[entity] = []
            if title not in entity_details[entity]:
                entity_details[entity].append(title)

    # Build sorted pattern list
    patterns = [
        {
            "entity": entity,
            "count": count,
            "events": entity_details.get(entity, [])[:5],
        }
        for entity, count in sorted(
            entity_counts.items(), key=lambda x: x[1], reverse=True
        )
    ]

    return {"patterns": patterns, "total_entries": len(points)}


@router.delete("/memory")
async def clear_memory():
    """Clear the memory collection (delete and recreate)."""
    from sentinel.db.qdrant_client import _get_client, ensure_collection

    settings = get_settings()
    collection = f"{settings.ACTIVE_TENANT}_memory"
    client = _get_client()

    # Check if collection exists
    collections = await client.get_collections()
    existing = {c.name for c in collections.collections}

    if collection in existing:
        await client.delete_collection(collection)
        logger.info("memory.collection.deleted", collection=collection)

    # Recreate empty collection
    await ensure_collection(collection)
    logger.info("memory.collection.recreated", collection=collection)

    return {"message": f"Memory collection '{collection}' cleared and recreated."}


# ── Level 4: Prompt management endpoints ──────────────────────────────────

_PROMPT_AGENTS = [
    "EntityExtractor", "SignalClassifier", "RouterAgent",
    "RiskAssessor", "CausalChainBuilder", "RedTeamAgent",
    "BlueTeamAgent", "ArbiterAgent", "BriefWriter",
]


@router.get("/prompts")
async def list_prompts():
    """List all agents with their current active prompt version."""
    from sentinel.optimiser.prompt_store import get_active_prompt, get_prompt_history

    agents = []
    for agent_name in _PROMPT_AGENTS:
        history = await get_prompt_history(agent_name)
        active_version = history[0].version if history else None
        agents.append({
            "agent_name": agent_name,
            "active_version": active_version,
            "total_versions": len(history),
        })
    return {"agents": agents, "total": len(agents)}


@router.get("/prompts/{agent_name}")
async def get_active_prompt(agent_name: str):
    """Get the currently active prompt for an agent."""
    from sentinel.optimiser.prompt_store import get_active_prompt as _get_prompt, get_prompt_history

    prompt_text = await _get_prompt(agent_name, default="")
    history = await get_prompt_history(agent_name)

    if not prompt_text and not history:
        raise HTTPException(status_code=404, detail=f"No prompts found for agent '{agent_name}'")

    return {
        "agent_name": agent_name,
        "active_prompt": prompt_text,
        "version": history[0].version if history else 1,
        "total_versions": len(history),
    }


@router.get("/prompts/{agent_name}/history")
async def get_prompt_history(agent_name: str):
    """Get full prompt version history for an agent."""
    from sentinel.optimiser.prompt_store import get_prompt_history as _get_history

    history = await _get_history(agent_name)
    return {
        "agent_name": agent_name,
        "versions": [
            {
                "version": pv.version,
                "is_active": pv.is_active,
                "quality_score": pv.quality_score,
                "created_at": pv.created_at.isoformat(),
                "prompt_preview": pv.prompt_text[:200] + "..." if len(pv.prompt_text) > 200 else pv.prompt_text,
            }
            for pv in history
        ],
    }


@router.post("/prompts/{agent_name}/rollback")
async def rollback_prompt(agent_name: str, version: int):
    """Rollback an agent's prompt to a specific version."""
    from sentinel.optimiser.prompt_store import rollback_prompt as _rollback

    pv = await _rollback(agent_name, version)
    if pv is None:
        raise HTTPException(status_code=404, detail=f"Version {version} not found for agent '{agent_name}'")

    return {
        "message": f"Rolled back {agent_name} to version {version}",
        "agent_name": agent_name,
        "version": pv.version,
        "is_active": pv.is_active,
    }


@router.get("/quality")
async def get_quality_scores(limit: int = 10):
    """Get recent quality scores from the last pipeline runs."""
    scores = _quality_scores[-limit:]
    scores_reversed = list(reversed(scores))
    return {
        "quality_scores": [
            {
                "id": qs.id,
                "brief_id": qs.brief_id,
                "overall": qs.overall,
                "specificity": qs.specificity,
                "evidence_depth": qs.evidence_depth,
                "causal_clarity": qs.causal_clarity,
                "actionability": qs.actionability,
                "completeness": qs.completeness,
                "weak_agents": qs.weak_agents,
                "improvement_notes": qs.improvement_notes,
                "created_at": qs.created_at.isoformat(),
            }
            for qs in scores_reversed
        ],
        "total": len(_quality_scores),
        "threshold": get_settings().QUALITY_THRESHOLD,
    }


@router.post("/quality/optimise")
async def trigger_optimisation(background_tasks: BackgroundTasks):
    """Manually trigger prompt optimisation based on last quality score."""
    if not _quality_scores:
        raise HTTPException(status_code=404, detail="No quality scores found — run a pipeline first")

    latest_qs = _quality_scores[-1]
    settings = get_settings()

    if not settings.OPTIMISER_ENABLED:
        return {"message": "Optimiser is disabled (OPTIMISER_ENABLED=false)", "skipped": True}

    if not latest_qs.weak_agents:
        return {"message": "No weak agents identified in latest quality score", "skipped": True}

    if not _briefs:
        raise HTTPException(status_code=404, detail="No briefs found — run a pipeline first")

    latest_brief = _briefs[-1]

    async def _do_optimise():
        from sentinel.optimiser.optimiser import PromptOptimiser
        optimiser = PromptOptimiser()
        await optimiser.run(
            weak_agents=latest_qs.weak_agents,
            brief=latest_brief,
            quality_score=latest_qs,
        )

    background_tasks.add_task(_do_optimise)

    return {
        "message": "Optimisation triggered",
        "weak_agents": latest_qs.weak_agents,
        "quality_score": latest_qs.overall,
        "threshold": settings.QUALITY_THRESHOLD,
    }


# ══════════════════════════════════════════════════════════════════════════
# Level 5 — Human Feedback Endpoints
# ══════════════════════════════════════════════════════════════════════════

from fastapi.responses import HTMLResponse

_FEEDBACK_THANK_YOU_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>SENTINEL — Feedback Recorded</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          min-height:100vh;display:flex;align-items:center;justify-content:center;
          background:#f8fafc;color:#1e293b}}
    .card{{background:#fff;border-radius:16px;border:1px solid #e2e8f0;
           padding:48px 40px;max-width:420px;text-align:center;
           box-shadow:0 4px 24px rgba(0,0,0,.06)}}
    .icon{{font-size:48px;margin-bottom:16px}}
    h1{{font-size:22px;font-weight:700;margin-bottom:8px}}
    p{{color:#64748b;font-size:15px;line-height:1.6}}
    .badge{{display:inline-block;margin-top:20px;padding:6px 16px;
            border-radius:99px;font-size:13px;font-weight:600;
            background:{badge_bg};color:{badge_color}}}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>Feedback Recorded</h1>
    <p>SENTINEL has logged your response for<br/><strong>{signal_title}</strong></p>
    <span class="badge">{action_label}</span>
    <p style="margin-top:24px;font-size:13px;color:#94a3b8">
      This signal's confidence weights will be updated in the next pipeline run.
    </p>
  </div>
</body>
</html>"""

_ACTION_META = {
    "acted_on":       ("✅", "Acted On",       "#d1fae5", "#065f46"),
    "false_positive": ("❌", "False Positive",  "#fee2e2", "#991b1b"),
    "escalate":       ("⬆️", "Escalated",       "#fef3c7", "#92400e"),
    "dismiss":        ("➡️", "Dismissed",        "#f1f5f9", "#475569"),
}


@router.get("/feedback/{signal_id}/{action_name}", response_class=HTMLResponse)
async def record_feedback(
    signal_id: str,
    action_name: str,
    brief_id: str = "",
    title: str = "Unknown Signal",
    source: str = "UNKNOWN",
    priority: str = "P2",
    confidence: float = 0.5,
) -> HTMLResponse:
    """Record a feedback action from a one-click email/Slack link.

    Returns a simple HTML thank-you page shown in the browser.
    """
    from sentinel.models.feedback_entry import FeedbackAction

    # Normalise action name
    action_str = action_name.lower().replace("-", "_")
    try:
        action = FeedbackAction(action_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action '{action_name}'. Use: acted_on, false_positive, escalate, dismiss",
        )

    # Persist to Qdrant (best-effort — don't fail if Qdrant is down)
    try:
        from sentinel.feedback.store import save_feedback
        await save_feedback(
            signal_id=signal_id,
            brief_id=brief_id or "unknown",
            action=action,
            signal_title=title,
            signal_source=source.upper(),
            original_priority=priority,
            original_confidence=confidence,
        )
    except Exception as exc:
        logger.warning("feedback.save_failed", error=str(exc), signal_id=signal_id)

    meta = _ACTION_META.get(action_str, ("📝", action_name.replace("_", " ").title(), "#f1f5f9", "#475569"))
    icon, action_label, badge_bg, badge_color = meta
    html = _FEEDBACK_THANK_YOU_HTML.format(
        icon=icon,
        signal_title=title[:60],
        action_label=action_label,
        badge_bg=badge_bg,
        badge_color=badge_color,
    )
    return HTMLResponse(content=html, status_code=200)


@router.get("/feedback")
async def list_feedback(
    days: int = 30,
    limit: int = 50,
) -> dict[str, Any]:
    """List recent feedback entries."""
    try:
        from sentinel.feedback.store import get_feedback
        entries = await get_feedback(days_back=days)
        entries = entries[:limit]
        return {
            "feedback": [e.to_payload() for e in entries],
            "total": len(entries),
            "window_days": days,
        }
    except Exception as exc:
        logger.warning("feedback.list_failed", error=str(exc))
        return {"feedback": [], "total": 0, "window_days": days}


@router.get("/feedback/stats")
async def feedback_stats(days: int = 30) -> dict[str, Any]:
    """Get feedback statistics — acted_on_rate, false_positive_rate per source."""
    try:
        from sentinel.feedback.store import get_feedback_stats
        return await get_feedback_stats(days_back=days)
    except Exception as exc:
        logger.warning("feedback.stats_failed", error=str(exc))
        return {"total": 0, "acted_on_rate": 0.0, "window_days": days}


@router.get("/feedback/weights")
async def feedback_weights() -> dict[str, Any]:
    """Return current feedback_weights.json contents."""
    import json, os
    path = os.path.join("data", "feedback_weights.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "category_confidence_multipliers": {"CYBER": 1.0, "NEWS": 1.0, "FINANCIAL": 1.0},
            "source_priority_weights": {"NVD": 1.0, "NEWSAPI": 1.0, "SEC_EDGAR": 1.0},
            "overall_acted_on_rate": 0.0,
            "error": "feedback_weights.json not found",
        }


@router.post("/feedback/process")
async def process_feedback(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Manually trigger FeedbackAgent to recompute weights."""
    settings = get_settings()

    async def _run_feedback_agent():
        from sentinel.agents.feedback.feedback_agent import FeedbackAgent
        agent = FeedbackAgent()
        await agent.run()

    background_tasks.add_task(_run_feedback_agent)
    return {"message": "FeedbackAgent triggered — weights will update in background"}


@router.delete("/feedback")
async def clear_all_feedback() -> dict[str, Any]:
    """Clear all feedback entries from Qdrant. For testing only."""
    try:
        from sentinel.feedback.store import clear_feedback
        count = await clear_feedback()
        return {"message": f"Deleted {count} feedback entries"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Level 6: Tenant Management Endpoints ─────────────────────────────────


@router.get("/tenants")
async def list_tenants() -> dict[str, Any]:
    """List all registered tenants."""
    try:
        from sentinel.tenants.manager import list_tenants as _list
        tenants = await _list()
        return {
            "tenants": [t.model_dump() for t in tenants],
            "total": len(tenants),
        }
    except Exception as exc:
        logger.warning("tenants.list_failed", error=str(exc))
        return {"tenants": [], "total": 0}


@router.post("/tenants")
async def create_tenant(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new tenant.

    Body: { "tenant_id": "acmecorp", "name": "Acme Corp", "industry": "Technology" }
    """
    try:
        from sentinel.tenants.manager import create_tenant as _create
        from sentinel.models.tenant import Tenant
        tenant = Tenant(
            id=body.get("tenant_id", body.get("id", "")),
            name=body.get("name", ""),
            industry=body.get("industry", ""),
        )
        created = await _create(tenant)
        return {"tenant": created.model_dump(), "message": "Tenant created"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str) -> dict[str, Any]:
    """Get a single tenant by ID."""
    try:
        from sentinel.tenants.manager import get_tenant as _get
        tenant = await _get(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
        return {"tenant": tenant.model_dump()}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str) -> dict[str, Any]:
    """Delete a tenant from the registry (does NOT delete Qdrant collections)."""
    try:
        from sentinel.tenants.manager import delete_tenant as _delete
        ok = await _delete(tenant_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
        return {"message": f"Tenant '{tenant_id}' deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tenants/{tenant_id}/profile")
async def tenant_profile(tenant_id: str) -> dict[str, Any]:
    """Return the company profile for a tenant."""
    import json
    import os
    from sentinel.config import get_settings
    settings = get_settings()
    profile_path = os.path.join(settings.TENANTS_DIR, tenant_id, "company_profile.json")
    if not os.path.exists(profile_path):
        raise HTTPException(status_code=404, detail=f"Profile for '{tenant_id}' not found")
    with open(profile_path, encoding="utf-8") as f:
        return json.load(f)


# ── Level 6: Shared Intelligence Endpoints ────────────────────────────────


@router.get("/shared/patterns")
async def get_shared_patterns(limit: int = 20, pattern_type: str | None = None) -> dict[str, Any]:
    """Query anonymised cross-company threat patterns.

    Query params:
        limit:        Max patterns to return (default 20).
        pattern_type: Optional filter (CVE_EXPLOIT, SUPPLY_CHAIN, REGULATORY, DATA_BREACH, FINANCIAL_FRAUD, GENERIC).
    """
    try:
        from sentinel.db.qdrant_client import _get_client
        from sentinel.config import get_settings
        settings = get_settings()
        client = _get_client()

        # Scroll all patterns from shared collection
        results, _ = await client.scroll(
            collection_name=settings.QDRANT_SHARED_COLLECTION,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        patterns = []
        for point in results:
            payload = point.payload or {}
            if pattern_type and payload.get("pattern_type") != pattern_type:
                continue
            patterns.append(payload)

        return {
            "patterns": patterns,
            "total": len(patterns),
            "collection": settings.QDRANT_SHARED_COLLECTION,
        }
    except Exception as exc:
        logger.warning("shared.patterns_failed", error=str(exc))
        return {"patterns": [], "total": 0, "error": str(exc)}


@router.get("/shared/patterns/stats")
async def shared_pattern_stats() -> dict[str, Any]:
    """Summary statistics for the shared patterns collection."""
    try:
        from sentinel.db.qdrant_client import _get_client
        from sentinel.config import get_settings
        settings = get_settings()
        client = _get_client()

        results, _ = await client.scroll(
            collection_name=settings.QDRANT_SHARED_COLLECTION,
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )

        type_counts: dict[str, int] = {}
        total_occurrences = 0
        for point in results:
            payload = point.payload or {}
            ptype = payload.get("pattern_type", "UNKNOWN")
            type_counts[ptype] = type_counts.get(ptype, 0) + 1
            total_occurrences += payload.get("occurrence_count", 1)

        return {
            "total_patterns": len(results),
            "total_occurrences": total_occurrences,
            "by_type": type_counts,
            "collection": settings.QDRANT_SHARED_COLLECTION,
        }
    except Exception as exc:
        logger.warning("shared.stats_failed", error=str(exc))
        return {"total_patterns": 0, "error": str(exc)}


# ── Level 7: Forecast Endpoints ──────────────────────────────────────────


@router.get("/forecasts")
async def get_forecasts(tenant_id: str = "default") -> list[dict]:
    """List all forecasts for a tenant, sorted by probability descending."""
    try:
        from sentinel.forecast.store import get_forecasts as _get_forecasts
        entries = await _get_forecasts(tenant_id=tenant_id, pending_only=False)
        return [e.to_payload() for e in entries]
    except Exception as exc:
        logger.warning("forecasts.list_failed", error=str(exc))
        return []


@router.get("/forecasts/active")
async def get_active_forecasts(tenant_id: str = "default") -> list[dict]:
    """List only PENDING forecasts for a tenant."""
    try:
        from sentinel.forecast.store import get_forecasts as _get_forecasts
        entries = await _get_forecasts(tenant_id=tenant_id, pending_only=True)
        return [e.to_payload() for e in entries]
    except Exception as exc:
        logger.warning("forecasts.active_failed", error=str(exc))
        return []


@router.get("/forecasts/accuracy")
async def get_forecast_accuracy(tenant_id: str = "default") -> dict:
    """Return accuracy metrics for a tenant's resolved forecasts."""
    try:
        from sentinel.forecast.store import get_accuracy
        return await get_accuracy(tenant_id=tenant_id)
    except Exception as exc:
        logger.warning("forecasts.accuracy_failed", error=str(exc))
        return {"tenant_id": tenant_id, "rate": 0.0, "error": str(exc)}


@router.get("/forecasts/history")
async def get_forecast_history(tenant_id: str = "default", days: int = 30) -> list[dict]:
    """Return resolved forecasts from the last N days."""
    from datetime import datetime, timedelta, timezone
    try:
        from sentinel.forecast.store import get_forecasts as _get_forecasts
        from sentinel.models.forecast_entry import ForecastOutcome
        all_forecasts = await _get_forecasts(tenant_id=tenant_id, pending_only=False)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        resolved = [
            e for e in all_forecasts
            if e.outcome != ForecastOutcome.PENDING
            and (e.resolved_at is None or e.resolved_at >= cutoff)
        ]
        return [e.to_payload() for e in resolved]
    except Exception as exc:
        logger.warning("forecasts.history_failed", error=str(exc))
        return []


@router.get("/forecasts/signal/{signal_id}")
async def get_forecast_by_signal_route(signal_id: str, tenant_id: str = "default") -> dict:
    """Return the most recent forecast for a specific signal_id."""
    try:
        from sentinel.forecast.store import get_forecast_by_signal
        entry = await get_forecast_by_signal(tenant_id=tenant_id, signal_id=signal_id)
        if entry:
            return entry.to_payload()
        raise HTTPException(status_code=404, detail=f"No forecast for signal {signal_id}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/forecasts/{forecast_id}")
async def get_forecast_detail(forecast_id: str, tenant_id: str = "default") -> dict:
    """Return a single forecast by its ID."""
    try:
        from sentinel.forecast.store import get_forecasts as _get_forecasts
        forecasts = await _get_forecasts(tenant_id=tenant_id, pending_only=False, limit=1000)
        match = next((f for f in forecasts if f.id == forecast_id), None)
        if match:
            return match.to_payload()
        raise HTTPException(status_code=404, detail=f"Forecast {forecast_id} not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/forecasts/resolve")
async def resolve_forecasts(tenant_id: str = "default") -> dict:
    """Manually trigger ForecastOutcomeTracker to resolve pending forecasts."""
    try:
        from sentinel.forecast.outcome_tracker import run as tracker_run
        result = await tracker_run(tenant_id=tenant_id)
        logger.info("forecasts.resolve.done", tenant_id=tenant_id, **result)
        return {"tenant_id": tenant_id, **result}
    except Exception as exc:
        logger.warning("forecasts.resolve_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# Level 8 — Autonomous Actions
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/actions")
async def list_actions(tenant_id: str = "default") -> list[dict]:
    """List all actions for a tenant (most recent first)."""
    return [
        a.to_payload()
        for a in reversed(_actions)
        if a.tenant_id == tenant_id
    ]


@router.get("/actions/pending")
async def list_pending_actions(tenant_id: str = "default") -> list[dict]:
    """List actions awaiting human approval."""
    from sentinel.models.action_entry import ActionStatus
    return [
        a.to_payload()
        for a in reversed(_actions)
        if a.tenant_id == tenant_id and a.status == ActionStatus.PENDING_APPROVAL
    ]


@router.get("/actions/audit")
async def action_audit_log(tenant_id: str = "default") -> list[dict]:
    """Full audit log of all actions (all statuses) for a tenant."""
    return [
        {
            **a.to_payload(),
            "audit_event": a.status.value,
        }
        for a in reversed(_actions)
        if a.tenant_id == tenant_id
    ]


@router.get("/actions/registry")
async def get_action_registry(tenant_id: str = "default") -> list[dict]:
    """Return the current action registry configuration for a tenant."""
    try:
        from sentinel.actions.registry import load_registry
        configs = await load_registry(tenant_id)
        return [
            {
                "action_type": c.action_type.value,
                "enabled": c.enabled,
                "auto_execute": c.auto_execute,
                "config": c.config,
            }
            for c in configs
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/actions/registry")
async def update_action_registry(body: list[dict], tenant_id: str = "default") -> dict:
    """Update the action registry configuration for a tenant."""
    try:
        from sentinel.actions.registry import ActionConfig, save_registry
        configs = [ActionConfig(**item) for item in body]
        await save_registry(tenant_id, configs)
        return {"tenant_id": tenant_id, "updated": len(configs)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/actions/signal/{signal_id}")
async def actions_for_signal(signal_id: str, tenant_id: str = "default") -> list[dict]:
    """Return all actions associated with a specific signal."""
    return [
        a.to_payload()
        for a in reversed(_actions)
        if a.tenant_id == tenant_id and a.signal_id == signal_id
    ]


@router.get("/actions/{action_id}")
async def get_action_detail(action_id: str, tenant_id: str = "default") -> dict:
    """Return a single action by its ID."""
    match = next(
        (a for a in _actions if a.id == action_id and a.tenant_id == tenant_id), None
    )
    if not match:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    return match.to_payload()


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, tenant_id: str = "default") -> dict:
    """Approve a pending action and execute it."""
    from sentinel.models.action_entry import ActionStatus
    from sentinel.actions.engine import ActionEngine

    match = next(
        (a for a in _actions if a.id == action_id and a.tenant_id == tenant_id), None
    )
    if not match:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    if match.status != ActionStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Action is {match.status.value}, not PENDING_APPROVAL",
        )

    match.status = ActionStatus.APPROVED
    match.approved_by = "admin"

    engine = ActionEngine()
    match = await engine.execute(match)

    logger.info("action.approved", action_id=action_id, status=match.status.value)
    return match.to_payload()


@router.post("/actions/{action_id}/reject")
async def reject_action(action_id: str, tenant_id: str = "default") -> dict:
    """Reject a pending action."""
    from sentinel.models.action_entry import ActionStatus

    match = next(
        (a for a in _actions if a.id == action_id and a.tenant_id == tenant_id), None
    )
    if not match:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    if match.status != ActionStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Action is {match.status.value}, not PENDING_APPROVAL",
        )

    match.status = ActionStatus.REJECTED
    logger.info("action.rejected", action_id=action_id)
    return match.to_payload()


# ──────────────────────────────────────────────────────────────────────────
#  Level 9: Negotiation endpoints
# ──────────────────────────────────────────────────────────────────────────


@router.get("/negotiations")
async def list_negotiations(tenant_id: str = "default"):
    """List all negotiation sessions for a tenant."""
    from sentinel.negotiation.store import get_sessions

    sessions = await get_sessions(tenant_id, active_only=False)
    return [s.to_payload() for s in sessions]


@router.get("/negotiations/active")
async def list_active_negotiations(tenant_id: str = "default"):
    """List in-progress negotiation sessions."""
    from sentinel.negotiation.store import get_sessions

    sessions = await get_sessions(tenant_id, active_only=True)
    return [s.to_payload() for s in sessions]


@router.get("/negotiations/demo")
async def run_demo_negotiation(tenant_id: str = "default"):
    """Run a demo negotiation with mock data — full end-to-end workflow."""
    from sentinel.models.negotiation import NegotiationSession, NegotiationStatus
    from sentinel.negotiation.pipeline import run_negotiation
    from sentinel.negotiation.store import save_session

    session = NegotiationSession(
        tenant_id=tenant_id,
        signal_id="demo-signal-001",
        action_id="demo-action-001",
        original_supplier="AcmeCloud Corp",
        risk_reason="Supplier bankruptcy filing detected — operations may cease within 60 days",
        status=NegotiationStatus.SEARCHING,
    )
    await save_session(session)

    # Run the full pipeline (demo mode will use mock data)
    result = await run_negotiation(session)
    return result.to_payload()


@router.get("/negotiations/{session_id}")
async def get_negotiation_detail(session_id: str):
    """Get full detail for a negotiation session."""
    from sentinel.negotiation.store import get_session

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Negotiation {session_id} not found")
    return session.to_payload()


@router.get("/negotiations/{session_id}/emails")
async def get_negotiation_emails(session_id: str):
    """Get outreach emails for a negotiation session."""
    from sentinel.negotiation.store import get_session

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Negotiation {session_id} not found")
    return [e.model_dump(mode="json") for e in session.outreach_emails]


@router.post("/negotiations/{session_id}/send")
async def approve_and_send_emails(session_id: str, tenant_id: str = "default"):
    """Approve and send outreach emails for a session."""
    from sentinel.negotiation.store import get_session, update_session
    from sentinel.models.negotiation import NegotiationStatus
    from datetime import datetime

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Negotiation {session_id} not found")

    # Mark all emails as sent
    for email in session.outreach_emails:
        if not email.sent_at:
            email.sent_at = datetime.utcnow()

    await update_session(session_id, {
        "outreach_emails": session.outreach_emails,
        "status": NegotiationStatus.AWAITING_REPLY,
    })

    return {"session_id": session_id, "emails_sent": len(session.outreach_emails)}


@router.post("/negotiations/{session_id}/cancel")
async def cancel_negotiation(session_id: str):
    """Cancel an in-progress negotiation."""
    from sentinel.negotiation.store import get_session, update_session
    from sentinel.models.negotiation import NegotiationStatus
    from datetime import datetime

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Negotiation {session_id} not found")

    if session.status in (NegotiationStatus.COMPLETE, NegotiationStatus.FAILED):
        raise HTTPException(
            status_code=400,
            detail=f"Session is already {session.status.value}",
        )

    await update_session(session_id, {
        "status": NegotiationStatus.FAILED,
        "completed_at": datetime.utcnow(),
        "recommendation_reasoning": "Cancelled by user",
    })

    return {"session_id": session_id, "status": "FAILED", "message": "Negotiation cancelled"}


@router.get("/negotiations/{session_id}/summary")
async def get_negotiation_summary(session_id: str):
    """Get the final recommendation summary for a negotiation."""
    from sentinel.negotiation.store import get_session

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Negotiation {session_id} not found")
    return {
        "session_id": session.id,
        "original_supplier": session.original_supplier,
        "recommendation": session.recommendation,
        "recommendation_reasoning": session.recommendation_reasoning,
        "status": session.status.value,
        "alternatives_count": len(session.alternatives_found),
        "replies_count": sum(1 for e in session.outreach_emails if e.reply_received),
    }


@router.post("/negotiations/trigger")
async def trigger_negotiation(
    supplier_name: str,
    risk_reason: str = "Manual trigger",
    tenant_id: str = "default",
):
    """Manually trigger a negotiation for a supplier."""
    from sentinel.models.negotiation import NegotiationSession, NegotiationStatus
    from sentinel.negotiation.pipeline import run_negotiation
    from sentinel.negotiation.store import save_session
    import asyncio

    session = NegotiationSession(
        tenant_id=tenant_id,
        signal_id="manual-trigger",
        action_id="manual-trigger",
        original_supplier=supplier_name,
        risk_reason=risk_reason,
        status=NegotiationStatus.SEARCHING,
    )
    await save_session(session)

    # Fire as background task
    asyncio.create_task(run_negotiation(session))

    return {
        "session_id": session.id,
        "supplier": supplier_name,
        "status": "SEARCHING",
        "message": f"Negotiation pipeline started for {supplier_name}",
    }


# ══════════════════════════════════════════════════════════════════════
# Level 10 — Meta + Governance + A/B Test Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.get("/meta/reports")
async def list_meta_reports(
    limit: int = 20,
    tenant_id: str = "default",
):
    """List MetaReports, newest first."""
    try:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        settings = get_settings()
        client = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        results = await client.scroll(
            collection_name="sentinel_meta",
            scroll_filter=Filter(must=[
                FieldCondition(key="type", match=MatchValue(value="meta_report")),
            ]),
            limit=limit,
            with_payload=True,
        )
        await client.close()

        reports = [p.payload for p in results[0]]
        reports.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return {"reports": reports[:limit]}
    except Exception:
        # Return demo data
        from sentinel.meta.meta_agent import MetaAgent
        agent = MetaAgent()
        report = await agent.run(tenant_id=tenant_id)
        return {"reports": [report.to_payload()]}


@router.get("/meta/reports/latest")
async def get_latest_meta_report(tenant_id: str = "default"):
    """Get the most recent MetaReport."""
    try:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        settings = get_settings()
        client = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        results = await client.scroll(
            collection_name="sentinel_meta",
            scroll_filter=Filter(must=[
                FieldCondition(key="type", match=MatchValue(value="meta_report")),
            ]),
            limit=10,
            with_payload=True,
        )
        await client.close()

        if results[0]:
            reports = [p.payload for p in results[0]]
            reports.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            return reports[0]
    except Exception:
        pass

    # Generate fresh report
    from sentinel.meta.meta_agent import MetaAgent
    agent = MetaAgent()
    report = await agent.run(tenant_id=tenant_id)
    return report.to_payload()


@router.get("/meta/reports/{report_id}")
async def get_meta_report(report_id: str):
    """Get a specific MetaReport by ID."""
    try:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        settings = get_settings()
        client = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        results = await client.scroll(
            collection_name="sentinel_meta",
            scroll_filter=Filter(must=[
                FieldCondition(key="type", match=MatchValue(value="meta_report")),
                FieldCondition(key="id", match=MatchValue(value=report_id)),
            ]),
            limit=1,
            with_payload=True,
        )
        await client.close()

        if results[0]:
            return results[0][0].payload
    except Exception:
        pass

    return {"error": "Report not found"}


@router.post("/meta/run")
async def trigger_meta_agent(tenant_id: str = "default"):
    """Trigger MetaAgent to run immediately."""
    from sentinel.meta.meta_agent import MetaAgent
    agent = MetaAgent()
    report = await agent.run(tenant_id=tenant_id)
    return report.to_payload()


@router.get("/meta/health")
async def get_agent_health(tenant_id: str = "default"):
    """Get current agent health scores."""
    from sentinel.meta.meta_agent import MetaAgent
    agent = MetaAgent()
    health = await agent._collect_agent_health()
    return {"agents": [h.model_dump() for h in health]}


@router.get("/meta/debate-balance")
async def get_debate_balance():
    """Get red vs blue team win rates."""
    from sentinel.meta.meta_agent import MetaAgent
    agent = MetaAgent()
    balance = await agent._compute_debate_balance()
    return balance.model_dump()


@router.get("/meta/action-effectiveness")
async def get_action_effectiveness(tenant_id: str = "default"):
    """Get action acted-on rates."""
    from sentinel.meta.meta_agent import MetaAgent
    agent = MetaAgent()
    effectiveness = await agent._compute_action_effectiveness(tenant_id)
    return effectiveness.model_dump()


@router.get("/governance/log")
async def get_governance_log(
    limit: int = 100,
    event_type: str | None = None,
):
    """Get governance log entries, newest first."""
    from sentinel.meta.governance import get_log
    entries = await get_log(limit=limit, event_type=event_type)
    return {"entries": [e.to_payload() for e in entries]}


@router.get("/governance/overrides")
async def get_overrides(active_only: bool = True):
    """List override rules."""
    from sentinel.meta.override import list_overrides
    rules = await list_overrides(active_only=active_only)
    return {"overrides": [r.to_payload() for r in rules]}


@router.post("/governance/overrides")
async def create_override(
    scope: str,
    target: str,
    reason: str = "",
    applied_by: str = "user",
):
    """Create a new override rule."""
    from sentinel.meta.override import create_override as _create
    rule = await _create(
        scope=scope,
        target=target,
        reason=reason,
        applied_by=applied_by,
    )
    return rule.to_payload()


@router.delete("/governance/overrides/{override_id}")
async def delete_override(override_id: str):
    """Deactivate an override rule."""
    from sentinel.meta.override import deactivate_override
    rule = await deactivate_override(override_id)
    if rule:
        return {"status": "deactivated", "override": rule.to_payload()}
    return {"error": "Override not found"}


@router.get("/ab-tests")
async def list_ab_tests():
    """List all A/B tests."""
    from sentinel.meta.ab_test import ABTestManager
    manager = ABTestManager()
    tests = manager.get_all_tests()
    return {"tests": [t.model_dump() for t in tests]}


@router.get("/ab-tests/active")
async def list_active_ab_tests():
    """List currently running A/B tests."""
    from sentinel.meta.ab_test import ABTestManager
    manager = ABTestManager()
    tests = manager.get_active_tests()
    return {"tests": [t.model_dump() for t in tests]}


@router.get("/ab-tests/{test_id}")
async def get_ab_test(test_id: str):
    """Get a single A/B test by ID."""
    from sentinel.meta.ab_test import ABTestManager
    manager = ABTestManager()
    test = manager.get_test(test_id)
    if test:
        return test.model_dump()
    return {"error": "Test not found"}
