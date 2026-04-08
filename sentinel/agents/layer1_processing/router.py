"""RouterAgent — LLM-powered dynamic pipeline routing (Level 2).

Inserted after SignalClassifier in the LangGraph pipeline.
Reads each signal + the active CompanyProfile and decides which
pipeline path to follow:

  Path A (FULL)     — P0/P1 + company relevant → full deliberation
  Path B (FAST)     — P2 / low relevance → RiskAssessor → BriefWriter
  Path C (LOG_ONLY) — P3 / zero relevance → BriefWriter directly
"""

from __future__ import annotations

import json
from typing import Any

from sentinel.agents.base import BaseAgent
from sentinel.models.route_decision import RouteDecision, RoutePath
from sentinel.profile.manager import get_active_profile
from sentinel.optimiser.prompt_store import get_active_prompt as get_prompt


class RouterAgent(BaseAgent):
    """Decide pipeline path per signal based on priority + company relevance."""

    agent_name = "RouterAgent"

    _SYSTEM_PROMPT = """\
You are a pipeline routing agent for an enterprise risk intelligence system.
You receive a signal and a company profile. Your job is to decide which
pipeline path to route this signal through.

RULES:
- Path A (FULL): Use for P0 or P1 signals that are relevant to the company.
  Also use FULL if any signal entity directly matches the company's tech_stack,
  suppliers, or regulatory_scope.
- Path B (FAST): Use for P2 signals OR signals with low company relevance
  (relevance_score < 0.4). Skip deliberation but still assess risk.
- Path C (LOG_ONLY): Use for P3 signals OR signals with zero company relevance
  (relevance_score < 0.1). Just log and include in brief summary.

Output ONLY valid JSON with these fields:
{
  "path": "FULL" | "FAST" | "LOG_ONLY",
  "relevance_score": <float 0.0–1.0>,
  "relevance_reason": "<1-2 sentence explanation>",
  "company_matches": ["<field>:<matched_value>", ...]
}
"""

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Route each signal and store decisions in state."""
        signals = state.get("signals", [])
        profile = get_active_profile()
        decisions: list[RouteDecision] = state.get("route_decisions", [])

        self.log.info(
            "router.start",
            signal_count=len(signals),
            company=profile.name,
        )

        for signal in signals:
            decision = await self._route_signal(signal, profile)
            decisions.append(decision)
            self.log.info(
                "router.decision",
                signal_id=str(signal.id),
                title=signal.title[:60],
                path=decision.path.value,
                relevance=decision.relevance_score,
            )

        self.log.info(
            "router.complete",
            total=len(decisions),
            full=sum(1 for d in decisions if d.path == RoutePath.FULL),
            fast=sum(1 for d in decisions if d.path == RoutePath.FAST),
            log_only=sum(1 for d in decisions if d.path == RoutePath.LOG_ONLY),
        )

        return {"route_decisions": decisions}

    async def _route_signal(self, signal: Any, profile: Any) -> RouteDecision:
        """Route a single signal using LLM + company profile."""
        # Build signal summary for the LLM
        signal_info = {
            "id": str(signal.id),
            "title": signal.title,
            "priority": signal.priority.value if hasattr(signal.priority, "value") else str(signal.priority),
            "source": signal.source.value if hasattr(signal.source, "value") else str(signal.source),
            "content": (signal.content or "")[:500],
            "entities": [
                {"name": e.name, "type": e.entity_type}
                for e in (signal.entities or [])
            ],
        }

        profile_info = {
            "name": profile.name,
            "industry": profile.industry,
            "tech_stack": profile.tech_stack,
            "suppliers": profile.suppliers,
            "regions": profile.regions,
            "regulatory_scope": profile.regulatory_scope,
            "keywords": profile.keywords,
        }

        system_prompt = await get_prompt("RouterAgent", default=self._SYSTEM_PROMPT)

        prompt = f"""{system_prompt}

SIGNAL:
{json.dumps(signal_info, indent=2)}

COMPANY PROFILE:
{json.dumps(profile_info, indent=2)}

Respond with JSON only:"""

        try:
            raw = await self.llm_complete(prompt, thinking=False)
            return self._parse_decision(raw, str(signal.id))
        except Exception:
            self.log.exception("router.llm_error", signal_id=str(signal.id))
            # Fallback: use priority-based heuristic
            return self._fallback_decision(signal)

    def _parse_decision(self, raw: str, signal_id: str) -> RouteDecision:
        """Parse LLM JSON response into a RouteDecision."""
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            data = json.loads(text)
            return RouteDecision(
                signal_id=signal_id,
                path=RoutePath(data.get("path", "FULL")),
                relevance_score=float(data.get("relevance_score", 0.5)),
                relevance_reason=data.get("relevance_reason", ""),
                company_matches=data.get("company_matches", []),
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            self.log.warning("router.parse_error", signal_id=signal_id, raw=text[:200])
            return RouteDecision(
                signal_id=signal_id,
                path=RoutePath.FULL,
                relevance_score=0.5,
                relevance_reason="Failed to parse LLM response, defaulting to FULL path",
            )

    def _fallback_decision(self, signal: Any) -> RouteDecision:
        """Priority-based fallback when LLM call fails."""
        priority = signal.priority.value if hasattr(signal.priority, "value") else str(signal.priority)

        if priority in ("P0", "P1"):
            path = RoutePath.FULL
            score = 0.7
        elif priority == "P2":
            path = RoutePath.FAST
            score = 0.3
        else:
            path = RoutePath.LOG_ONLY
            score = 0.1

        return RouteDecision(
            signal_id=str(signal.id),
            path=path,
            relevance_score=score,
            relevance_reason=f"LLM fallback: priority-based routing ({priority})",
        )
