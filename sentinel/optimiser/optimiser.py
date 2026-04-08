"""PromptOptimiser — Level 4 prompt self-improvement service.

Fires asynchronously (via asyncio.create_task) when QualityAgent
detects quality_score.overall < QUALITY_THRESHOLD.

For each weak agent:
  1. Load current active prompt from PromptStore
  2. Load the brief that scored poorly + improvement_notes
  3. Ask Gemini (thinking=ON) to rewrite the prompt
  4. Save new version to PromptStore
  5. Log the optimisation event

New prompts are used starting from the NEXT pipeline run.
This prevents mid-run prompt inconsistency.
"""

from __future__ import annotations

import structlog

from sentinel.config import get_settings
from sentinel.models.brief import Brief
from sentinel.models.quality_score import QualityScore
from sentinel.optimiser.prompt_store import get_active_prompt, save_prompt_version

logger = structlog.get_logger(__name__)

OPTIMISE_PROMPT_TEMPLATE = """You are a prompt engineering expert. Your task is to improve an AI agent's prompt template.

AGENT: {agent_name}
CURRENT SCORE: {score:.2f} (threshold: {threshold:.2f})
SCORING DIMENSION: {dimension}

ISSUE(S) IDENTIFIED:
{improvement_notes}

THE BRIEF THAT SCORED POORLY (excerpt):
---
{brief_excerpt}
---

CURRENT PROMPT TEMPLATE (this is what the agent is currently using):
---
{current_prompt}
---

INSTRUCTIONS:
1. Rewrite the prompt template to fix the identified issues
2. Keep ALL existing placeholder variables (e.g. {{signal_data}}, {{title}}, {{content}} etc.) exactly as they are
3. Do NOT add new placeholder variables
4. Do NOT change the output format the agent is expected to produce
5. Make targeted improvements to address the specific weaknesses identified
6. Keep the same overall structure and length — only change what needs to change

Return ONLY the improved prompt text. No explanation, no preamble, no markdown fencing.
"""


class PromptOptimiser:
    """Optimise agent prompts based on quality scoring feedback."""

    async def run(
        self,
        weak_agents: list[str],
        brief: Brief,
        quality_score: QualityScore,
    ) -> None:
        """Optimise prompts for all weak agents.

        Args:
            weak_agents:   Agent names whose prompts need improvement.
            brief:         The brief that scored below threshold.
            quality_score: The quality evaluation result.
        """
        settings = get_settings()

        if not settings.OPTIMISER_ENABLED:
            logger.info("prompt_optimiser.disabled")
            return

        logger.info(
            "prompt_optimiser.start",
            weak_agents=weak_agents,
            score=quality_score.overall,
            threshold=settings.QUALITY_THRESHOLD,
        )

        # Determine which dimension scored worst
        dimension_scores = {
            "specificity": quality_score.specificity,
            "evidence_depth": quality_score.evidence_depth,
            "causal_clarity": quality_score.causal_clarity,
            "actionability": quality_score.actionability,
            "completeness": quality_score.completeness,
        }
        weakest_dimension = min(dimension_scores, key=lambda k: dimension_scores[k])

        # Build brief excerpt for context
        brief_excerpt = f"Title: {brief.title}\n{brief.executive_summary[:500]}"
        if hasattr(brief, "sections") and brief.sections:
            for section in brief.sections[:2]:
                brief_excerpt += f"\n\n## {section.heading}\n{section.content[:200]}"

        improvement_notes_str = "\n".join(
            f"- {note}" for note in quality_score.improvement_notes
        ) or "- General quality improvement needed"

        for agent_name in weak_agents:
            await self._optimise_agent(
                agent_name=agent_name,
                brief_excerpt=brief_excerpt,
                improvement_notes=improvement_notes_str,
                quality_score=quality_score,
                weakest_dimension=weakest_dimension,
                threshold=settings.QUALITY_THRESHOLD,
            )

        logger.info("prompt_optimiser.complete", agents_optimised=len(weak_agents))

    async def _optimise_agent(
        self,
        agent_name: str,
        brief_excerpt: str,
        improvement_notes: str,
        quality_score: QualityScore,
        weakest_dimension: str,
        threshold: float,
    ) -> None:
        """Optimise the prompt for a single agent."""
        from sentinel.llm import client as llm

        # Load current active prompt
        current_prompt = await get_active_prompt(agent_name, default="")
        if not current_prompt:
            logger.warning("prompt_optimiser.no_prompt", agent=agent_name)
            return

        # Build optimisation request
        optimise_prompt = OPTIMISE_PROMPT_TEMPLATE \
            .replace("{agent_name}", agent_name) \
            .replace("{score:.2f}", f"{quality_score.overall:.2f}") \
            .replace("{threshold:.2f}", f"{threshold:.2f}") \
            .replace("{dimension}", weakest_dimension) \
            .replace("{improvement_notes}", improvement_notes) \
            .replace("{brief_excerpt}", brief_excerpt[:1000]) \
            .replace("{current_prompt}", current_prompt[:3000])

        try:
            # Thinking ON for PromptOptimiser (deep reasoning)
            new_prompt_text = await llm.complete(
                prompt=optimise_prompt,
                thinking=True,
            )

            if not new_prompt_text or len(new_prompt_text.strip()) < 50:
                logger.warning("prompt_optimiser.empty_response", agent=agent_name)
                return

            # Save new version
            pv = await save_prompt_version(
                agent_name=agent_name,
                prompt_text=new_prompt_text.strip(),
                quality_score=quality_score.overall,
            )

            logger.info(
                "prompt_optimiser.optimised",
                agent=agent_name,
                score_before=quality_score.overall,
                new_version=pv.version,
                prompt_length=len(new_prompt_text),
            )

        except Exception:
            logger.exception("prompt_optimiser.agent_error", agent=agent_name)
