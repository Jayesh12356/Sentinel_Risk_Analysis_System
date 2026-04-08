"""BriefWriter — Layer 4 output agent for executive intelligence briefs.

Uses Gemini via sentinel/llm/client.py with **thinking=OFF** to
generate a structured executive brief aggregating all signals,
risk reports, and deliberation results.

Per CONTEXT.md:
- Thinking OFF (fast + cheap)
- Creates a Brief object with sections, alerts, executive summary
- Aggregates signals and risk reports into final pipeline output
- Level 3: loads CompanyProfile + memory for stack-specific recommendations
- Level 3: detects recurring threat patterns from memory
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from sentinel.agents.base import BaseAgent
from sentinel.config import get_settings
from sentinel.memory.retriever import get_relevant_memories, count_similar_events
from sentinel.models.brief import AlertItem, Brief, BriefSection
from sentinel.models.risk_report import RiskReport
from sentinel.models.signal import Signal, SignalPriority
from sentinel.profile.manager import get_active_profile
from sentinel.optimiser.prompt_store import get_active_prompt

logger = structlog.get_logger(__name__)

BRIEF_PROMPT_TEMPLATE = """You are a senior intelligence analyst writing an executive brief for enterprise leadership.

Synthesise the following signals and risk assessments into a structured executive intelligence brief.

Return a JSON object with:
- title: a descriptive brief title (e.g. "SENTINEL Intelligence Brief — 2025-03-25")
- executive_summary: a 3–5 sentence high-level summary for C-suite executives, written in markdown
- sections: a JSON array of section objects, each with:
    - heading: section title
    - content: 2–4 sentence analysis in markdown
    - priority: "P0", "P1", "P2", or "P3"
- alerts: a JSON array of alert objects, each with:
    - signal_id: the originating signal ID
    - risk_report_id: the associated report ID
    - title: short alert headline
    - priority: "P0", "P1", "P2", or "P3"
    - confidence: float 0.0–1.0
    - recommended_action: a specific actionable recommendation TAILORED to the company profile below

Group sections by risk category. Create one alert per signal assessed.
Order alerts by priority (P0 first).
Make recommendations specific to the company's tech stack and regulatory scope.

Return ONLY a JSON object. No explanation, no markdown fencing.

COMPANY PROFILE:
{company_profile}

SIGNALS AND ASSESSMENTS:
{signal_data}

PAST SIMILAR EVENTS (from memory):
{memory_context}

RECURRING PATTERNS DETECTED:
{recurring_patterns}
"""


class BriefWriter(BaseAgent):
    """Generates executive intelligence briefs from pipeline results.

    Aggregates all signals, risk reports, and deliberation results
    into a final Brief object — the last node in the pipeline.
    """

    agent_name: str = "BriefWriter"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute brief generation — LangGraph node entry point."""
        signals: list[Signal] = state.get("signals", [])
        reports: list[RiskReport] = state.get("risk_reports", [])

        self.log.info(
            "brief_writer.start",
            signal_count=len(signals),
            report_count=len(reports),
        )

        # Level 3: Load company profile
        profile = get_active_profile()
        profile_str = (
            f"Company: {profile.name}\n"
            f"Industry: {profile.industry}\n"
            f"Tech Stack: {', '.join(profile.tech_stack)}\n"
            f"Suppliers: {', '.join(profile.suppliers)}\n"
            f"Regions: {', '.join(profile.regions)}\n"
            f"Regulatory Scope: {', '.join(profile.regulatory_scope)}\n"
            f"Keywords: {', '.join(profile.keywords)}"
        )

        # Level 3: Query memory for past events
        all_memories = []
        for signal in signals[:5]:  # Limit queries
            memories = await get_relevant_memories(
                query_text=signal.title, limit=2, days_back=90,
            )
            all_memories.extend(memories)

        # Deduplicate by title
        seen_titles = set()
        unique_memories = []
        for m in all_memories:
            if m.title not in seen_titles:
                seen_titles.add(m.title)
                unique_memories.append(m)

        memory_lines = []
        for m in unique_memories[:5]:
            memory_lines.append(
                f"- [{m.priority}] {m.title} (risk={m.risk_score:.1f}, "
                f"outcome={m.outcome[:60] if m.outcome else 'N/A'})"
            )
        memory_context_str = "\n".join(memory_lines) if memory_lines else "No past events found."

        # Level 3: Detect recurring patterns
        recurring_patterns: list[str] = []
        entity_set: set[str] = set()
        for signal in signals:
            if signal.entities:
                for e in signal.entities:
                    entity_set.add(e.name)

        for entity_name in list(entity_set)[:10]:  # Limit to 10
            count = await count_similar_events(entity_name, days_back=90)
            if count >= 2:
                recurring_patterns.append(f"{entity_name} — {count} events in 90 days")

        patterns_str = "\n".join(f"- {p}" for p in recurring_patterns) if recurring_patterns else "No recurring patterns detected."

        self.log.info(
            "brief_writer.memory",
            memories_found=len(unique_memories),
            patterns_detected=len(recurring_patterns),
        )

        # Build signal-report pairs for the prompt
        signal_data = self._build_signal_data(signals, reports)

        brief_forecasts = state.get("forecasts", []) or []
        forecast_count = len(brief_forecasts)
        brief_actions = state.get("actions", []) or []  # Level 8

        try:
            brief = await self._generate_brief(
                signals, reports, signal_data,
                profile_str, memory_context_str, patterns_str,
                recurring_patterns, [m.title for m in unique_memories],
                forecasts=brief_forecasts,
                actions=brief_actions,  # Level 8
            )
            self.log.info(
                "brief_writer.done",
                brief_id=brief.id,
                alert_count=len(brief.alerts),
                highest_priority=brief.highest_priority.value,
                forecast_count=forecast_count,
            )
        except Exception:
            self.log.exception("brief_writer.error")
            brief = Brief(
                title="SENTINEL Intelligence Brief — Generation Failed",
                executive_summary="Brief generation encountered an error. Please review raw signals.",
                signal_ids=[s.id for s in signals],
                risk_report_ids=[r.id for r in reports],
                total_signals=len(signals),
                demo=get_settings().demo_mode,
            )

        return {"brief": brief}

    def _build_signal_data(
        self, signals: list[Signal], reports: list[RiskReport]
    ) -> str:
        """Build a text summary of signals+reports for the LLM prompt."""
        report_map: dict[str, RiskReport] = {
            r.signal_id: r for r in reports
        }

        entries: list[str] = []
        for signal in signals:
            report = report_map.get(signal.id)
            entry = (
                f"Signal ID: {signal.id}\n"
                f"Title: {signal.title}\n"
                f"Source: {signal.source.value}\n"
                f"Category: {signal.category}\n"
                f"Priority: {signal.priority.value}\n"
                f"Content: {signal.content[:500]}\n"
            )
            if report:
                entry += (
                    f"Report ID: {report.id}\n"
                    f"Risk Score: impact={report.risk_score.impact}, "
                    f"probability={report.risk_score.probability}, "
                    f"exposure={report.risk_score.exposure}, "
                    f"overall={report.risk_score.overall}\n"
                    f"Evidence: {', '.join(report.evidence)}\n"
                    f"Root Cause: {report.root_cause}\n"
                    f"Final Priority: {report.final_priority.value}\n"
                    f"Arbiter Verdict: {report.deliberation.arbiter_verdict}\n"
                    f"Arbiter Confidence: {report.deliberation.arbiter_confidence}\n"
                )
            entries.append(entry)

        return "\n---\n".join(entries)

    async def _generate_brief(
        self,
        signals: list[Signal],
        reports: list[RiskReport],
        signal_data: str,
        company_profile: str = "",
        memory_context: str = "",
        recurring_patterns_str: str = "",
        recurring_patterns: list[str] | None = None,
        memory_titles: list[str] | None = None,
        forecasts: list | None = None,  # Level 7: ForecastEntry objects
        actions: list | None = None,    # Level 8: ActionEntry objects
    ) -> Brief:
        """Generate the brief via LLM and parse into Brief object."""
        template = await get_active_prompt("BriefWriter", default=BRIEF_PROMPT_TEMPLATE)
        prompt = template.format(
            signal_data=signal_data,
            company_profile=company_profile or "No company profile loaded.",
            memory_context=memory_context or "No past events found.",
            recurring_patterns=recurring_patterns_str or "No recurring patterns detected.",
        )

        # Thinking OFF for BriefWriter (fast + cheap)
        raw_response = await self.llm_complete(prompt, thinking=False)

        parsed = self._parse_brief(raw_response)

        # Determine highest priority across all alerts
        highest = SignalPriority.P3
        priority_order = [SignalPriority.P0, SignalPriority.P1, SignalPriority.P2, SignalPriority.P3]
        for alert in parsed.get("alerts", []):
            try:
                p = SignalPriority(alert.get("priority", "P3"))
                if priority_order.index(p) < priority_order.index(highest):
                    highest = p
            except ValueError:
                pass

        # Build Brief object
        sections = []
        for s in parsed.get("sections", []):
            try:
                sections.append(
                    BriefSection(
                        heading=str(s.get("heading", "")),
                        content=str(s.get("content", "")),
                        priority=SignalPriority(s.get("priority", "P3")),
                    )
                )
            except (ValueError, TypeError):
                pass

        alerts = []
        for a in parsed.get("alerts", []):
            try:
                alerts.append(
                    AlertItem(
                        signal_id=str(a.get("signal_id", "")),
                        risk_report_id=str(a.get("risk_report_id", "")),
                        title=str(a.get("title", "")),
                        priority=SignalPriority(a.get("priority", "P3")),
                        confidence=max(0.0, min(1.0, float(a.get("confidence", 0.0)))),
                        recommended_action=str(a.get("recommended_action", "")),
                    )
                )
            except (ValueError, TypeError):
                pass

        # Level 7: Build predicted_threats from ForecastEntry objects
        forecasts = forecasts or []
        predicted_threats = [
            {
                "signal_title": f.signal_title,
                "current_priority": f.current_priority,
                "predicted_priority": f.predicted_priority,
                "probability": f.probability,
                "horizon": f.horizon.value if hasattr(f.horizon, "value") else str(f.horizon),
                "reasoning": f.reasoning[:200] if f.reasoning else "",
            }
            for f in forecasts
            if f.probability > 0.60
        ]

        # Add predicted threats section if any high-probability forecasts exist
        if predicted_threats:
            forecast_text = "\n".join(
                f"- **{t['signal_title']}**: {t['probability']:.0%} chance of escalating to "
                f"{t['predicted_priority']} within {t['horizon']}. {t['reasoning']}"
                for t in predicted_threats[:5]
            )
            sections.append(
                BriefSection(
                    heading="⚡ Predicted Threats (AI Forecast)",
                    content=f"The following signals are predicted to escalate in priority:\n\n{forecast_text}",
                    priority=SignalPriority.P1,
                )
            )

        # Level 8: Build action summary lists from ActionEntry objects
        actions = actions or []
        actions_taken = []
        actions_pending = []
        actions_report_only = []

        for a in actions:
            action_type = a.action_type.value if hasattr(a.action_type, "value") else str(a.action_type)
            status = a.status.value if hasattr(a.status, "value") else str(a.status)

            if status == "AUTO_EXECUTED":
                actions_taken.append({
                    "action_type": action_type,
                    "title": a.title,
                    "description": a.description,
                    "confidence": a.confidence,
                    "result": a.result or {},
                })
            elif status in ("PENDING_APPROVAL", "APPROVED"):
                actions_pending.append({
                    "id": a.id,
                    "action_type": action_type,
                    "title": a.title,
                    "description": a.description,
                    "confidence": a.confidence,
                    "reasoning": a.reasoning[:200] if a.reasoning else "",
                })
            elif status == "REPORT_ONLY":
                actions_report_only.append({
                    "action_type": action_type,
                    "title": a.title,
                    "reasoning": a.reasoning[:200] if a.reasoning else "",
                    "confidence": a.confidence,
                })

        # Add Actions Taken section (green border in UI)
        if actions_taken:
            taken_text = "\n".join(
                f"- ✅ **{a['action_type']}**: {a['title']} (confidence: {a['confidence']:.0%})"
                for a in actions_taken
            )
            sections.append(
                BriefSection(
                    heading="🎯 Actions Taken (Autonomous)",
                    content=f"The following actions were executed automatically:\n\n{taken_text}",
                    priority=SignalPriority.P0,
                )
            )

        # Add Pending Approval section (orange border in UI)
        if actions_pending:
            pending_text = "\n".join(
                f"- ⏳ **{a['action_type']}**: {a['title']} — {a['reasoning']}"
                for a in actions_pending
            )
            sections.append(
                BriefSection(
                    heading="⏳ Pending Your Approval",
                    content=f"The following actions require human review:\n\n{pending_text}",
                    priority=SignalPriority.P1,
                )
            )

        return Brief(
            title=str(parsed.get("title", "SENTINEL Intelligence Brief")),
            executive_summary=str(parsed.get("executive_summary", "")),
            sections=sections,
            alerts=alerts,
            signal_ids=[s.id for s in signals],
            risk_report_ids=[r.id for r in reports],
            highest_priority=highest,
            total_signals=len(signals),
            demo=get_settings().demo_mode,
            recurring_patterns=recurring_patterns or [],
            memory_context=memory_titles or [],
            predicted_threats=predicted_threats,
            forecast_count=len(forecasts),
            actions_taken=actions_taken,
            actions_pending=actions_pending,
            actions_report_only=actions_report_only,
        )

    def _parse_brief(self, raw: str) -> dict[str, Any]:
        """Parse LLM JSON response into brief dict."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            self.log.warning("brief_writer.parse.invalid_json", raw=cleaned[:200])
            return {
                "title": "SENTINEL Intelligence Brief",
                "executive_summary": "Unable to parse brief from LLM response.",
                "sections": [],
                "alerts": [],
            }
