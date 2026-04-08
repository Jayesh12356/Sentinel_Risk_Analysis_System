"""QualityAgent — Level 4 brief quality scoring agent.

Runs AFTER BriefWriter as a LangGraph node. Scores the generated brief
on 5 dimensions via Gemini (thinking=OFF, fast). If quality_score.overall
falls below QUALITY_THRESHOLD, the PromptOptimiser fires async for weak agents.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from sentinel.agents.base import BaseAgent
from sentinel.config import get_settings
from sentinel.models.quality_score import QualityScore

logger = structlog.get_logger(__name__)

QUALITY_PROMPT = """You are a quality evaluation agent for an enterprise risk intelligence system.

Evaluate the following intelligence brief and return a JSON object scoring it on 5 dimensions.
Each score is a float from 0.0 (very poor) to 1.0 (excellent).

Scoring criteria:
- specificity (0.0–1.0): Are the recommendations specific to the company's tech stack, not generic advice?
  0.0 = completely generic ("patch the software"), 1.0 = very specific ("run kubectl rollout restart on pod apache-xyz")
- evidence_depth (0.0–1.0): Are risk claims backed by concrete signal evidence (CVE IDs, dates, source data)?
  0.0 = no evidence cited, 1.0 = every claim has a specific evidential reference
- causal_clarity (0.0–1.0): Is the cause → effect chain logical, traceable, and clearly explained?
  0.0 = no causal reasoning, 1.0 = clear root cause → mechanism → downstream effects
- actionability (0.0–1.0): Can a human read this and immediately know what to do today, in order?
  0.0 = vague or no next steps, 1.0 = ordered, time-bound, owner-assigned actions
- completeness (0.0–1.0): Does the brief address all relevant risk categories for the signals processed?
  0.0 = major categories missing, 1.0 = all relevant categories covered

Also return:
- weak_agents: a list of agent names (from: BriefWriter, CausalChainBuilder, RedTeamAgent, BlueTeamAgent, ArbiterAgent)
  whose outputs appear to have contributed most to low scores. May be empty.
- improvement_notes: a list of 1–3 short strings describing specific weaknesses to fix.

Return ONLY a JSON object. No explanation, no markdown fencing.
Example:
{
  "specificity": 0.45,
  "evidence_depth": 0.70,
  "causal_clarity": 0.85,
  "actionability": 0.60,
  "completeness": 0.75,
  "weak_agents": ["BriefWriter"],
  "improvement_notes": ["Recommendations are generic — not tied to company's Kubernetes stack", "Missing CVSS severity citation"]
}

BRIEF TO EVALUATE:
---
{brief_text}
---
"""


class QualityAgent(BaseAgent):
    """Score the generated brief on 5 quality dimensions."""

    agent_name: str = "QualityAgent"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Score the brief and write quality_score to state."""
        brief = state.get("brief")
        if brief is None:
            logger.warning("quality_agent.no_brief")
            return {}

        settings = get_settings()

        logger.info("quality_agent.start", brief_id=brief.id)

        try:
            quality_score = await self._score_brief(brief)
            logger.info(
                "quality_agent.scored",
                brief_id=brief.id,
                overall=quality_score.overall,
                weak_agents=quality_score.weak_agents,
            )

            # Fire optimiser async if quality below threshold and optimiser enabled
            if (
                settings.OPTIMISER_ENABLED
                and quality_score.overall < settings.QUALITY_THRESHOLD
                and quality_score.weak_agents
            ):
                import asyncio
                from sentinel.optimiser.optimiser import PromptOptimiser

                logger.info(
                    "quality_agent.triggering_optimiser",
                    score=quality_score.overall,
                    threshold=settings.QUALITY_THRESHOLD,
                    weak_agents=quality_score.weak_agents,
                )
                optimiser = PromptOptimiser()
                asyncio.create_task(
                    optimiser.run(
                        weak_agents=quality_score.weak_agents,
                        brief=brief,
                        quality_score=quality_score,
                    )
                )

            return {"quality_score": quality_score}

        except Exception:
            logger.exception("quality_agent.error")
            return {}

    async def _score_brief(self, brief: Any) -> QualityScore:
        """Call Gemini to score the brief, parse result into QualityScore."""
        # Build a text representation of the brief
        brief_text = f"Title: {brief.title}\n\n"
        brief_text += f"Executive Summary:\n{brief.executive_summary}\n\n"
        if hasattr(brief, "sections") and brief.sections:
            for section in brief.sections:
                brief_text += f"## {section.heading}\n{section.content}\n\n"
        if hasattr(brief, "alerts") and brief.alerts:
            brief_text += "Alerts:\n"
            for alert in brief.alerts:
                brief_text += f"- [{alert.priority}] {alert.title}: {alert.recommended_action}\n"

        prompt = QUALITY_PROMPT.replace("{brief_text}", brief_text[:4000])

        # Thinking OFF for QualityAgent (fast + cheap)
        raw = await self.llm_complete(prompt, thinking=False)

        return self._parse_quality(raw, brief.id)

    def _parse_quality(self, raw: str, brief_id: str) -> QualityScore:
        """Parse LLM JSON response into QualityScore."""
        import re

        text = raw.strip()
        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        fence_match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        # Try to extract JSON object if text has extra content
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start != -1 and brace_end != -1:
            text = text[brace_start:brace_end + 1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("quality_agent.parse_failed, using defaults")
            data = {}

        specificity = float(data.get("specificity", 0.5))
        evidence_depth = float(data.get("evidence_depth", 0.5))
        causal_clarity = float(data.get("causal_clarity", 0.5))
        actionability = float(data.get("actionability", 0.5))
        completeness = float(data.get("completeness", 0.5))

        overall = QualityScore.compute_overall(
            specificity, evidence_depth, causal_clarity, actionability, completeness
        )

        return QualityScore(
            brief_id=brief_id,
            specificity=specificity,
            evidence_depth=evidence_depth,
            causal_clarity=causal_clarity,
            actionability=actionability,
            completeness=completeness,
            overall=overall,
            weak_agents=data.get("weak_agents", []),
            improvement_notes=data.get("improvement_notes", []),
        )
