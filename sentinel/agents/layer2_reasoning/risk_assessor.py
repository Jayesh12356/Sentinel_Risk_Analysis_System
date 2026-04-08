"""RiskAssessor — Layer 2 reasoning agent for risk scoring (Level 2).

Uses Gemini via sentinel/llm/client.py to compute risk scores
(impact × probability × exposure) and gather supporting evidence
for each classified signal.

Level 2 upgrade: loads CompanyProfile and computes profile_boost
to personalise the exposure score based on entity matches.

Per CONTEXT.md:
- Thinking OFF (fast + cheap)
- Creates RiskReport objects linked to signals via signal_id
- Sets initial_priority from signal.priority
- Computes RiskScore: impact × probability × final_exposure (profile-weighted)

Profile boost weights:
  tech_stack match  → +0.20
  supplier match    → +0.25
  region match      → +0.15
  regulatory match  → +0.20
  keyword match     → +0.10
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from sentinel.agents.base import BaseAgent
from sentinel.models.risk_report import RiskReport, RiskScore
from sentinel.models.signal import Signal, SignalPriority
from sentinel.profile.manager import get_active_profile
from sentinel.optimiser.prompt_store import get_active_prompt

logger = structlog.get_logger(__name__)

RISK_PROMPT_TEMPLATE = """You are a risk assessment analyst for an enterprise risk intelligence system.

Assess the risk posed by the following signal and return a JSON object with:
- impact: float 0.0–1.0 — severity of potential damage if the risk materialises
- probability: float 0.0–1.0 — likelihood of the risk occurring or worsening
- exposure: float 0.0–1.0 — how exposed a typical enterprise organisation is
- evidence: a JSON array of 2–5 short strings citing specific facts from the signal that support your assessment
- summary: a 2–3 sentence risk summary suitable for an executive audience

Return ONLY a JSON object. No explanation, no markdown fencing.
Example: {{"impact": 0.85, "probability": 0.70, "exposure": 0.60, "evidence": ["Active exploitation in the wild", "CVSS score 9.8"], "summary": "Critical vulnerability actively exploited."}}

SIGNAL TITLE: {title}
SIGNAL PRIORITY: {priority}
SIGNAL CATEGORY: {category}
SIGNAL SOURCE: {source}

SIGNAL CONTENT:
{content}

ENTITIES:
{entities}
"""

# ── Profile boost weights (from CONTEXT.md) ──────────────────────────────
BOOST_TECH_STACK = 0.20
BOOST_SUPPLIER = 0.25
BOOST_REGION = 0.15
BOOST_REGULATORY = 0.20
BOOST_KEYWORD = 0.10


class RiskAssessor(BaseAgent):
    """Assesses risk for each signal and creates RiskReport objects.

    Level 2: Now includes profile-weighted exposure scoring.
    Produces RiskReport with composite risk score, supporting evidence,
    company_matches, and relevance_score.
    """

    agent_name: str = "RiskAssessor"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute risk assessment — LangGraph node entry point."""
        signals: list[Signal] = state.get("signals", [])
        existing_reports: list[RiskReport] = state.get("risk_reports", [])

        self.log.info(
            "risk_assessor.start",
            signal_count=len(signals),
            existing_reports=len(existing_reports),
        )

        # Load company profile for personalised scoring
        profile = get_active_profile()
        self.log.info(
            "risk_assessor.profile_loaded",
            company=profile.name,
            tech_stack_count=len(profile.tech_stack),
        )

        new_reports: list[RiskReport] = []
        for signal in signals:
            # Skip signals that already have a report (Loop 2 re-run)
            already_assessed = any(
                r.signal_id == signal.id for r in existing_reports
            )
            if already_assessed:
                self.log.debug(
                    "risk_assessor.skip.existing", signal_id=signal.id
                )
                continue

            try:
                report = await self._assess_signal(signal, profile)
                new_reports.append(report)
                self.log.info(
                    "risk_assessor.signal.done",
                    signal_id=signal.id,
                    overall_score=report.risk_score.overall,
                    priority=report.initial_priority.value,
                    relevance=report.relevance_score,
                    matches=len(report.company_matches),
                )
            except Exception:
                self.log.exception(
                    "risk_assessor.signal.error", signal_id=signal.id
                )

        # Merge new reports with existing
        all_reports = existing_reports + new_reports

        self.log.info(
            "risk_assessor.done",
            new_reports=len(new_reports),
            total_reports=len(all_reports),
        )
        return {"risk_reports": all_reports}

    async def _assess_signal(self, signal: Signal, profile: Any) -> RiskReport:
        """Assess a single signal and produce a RiskReport with profile boost."""
        entity_str = "None"
        if signal.entities:
            entity_str = ", ".join(
                f"{e.name} ({e.entity_type})" for e in signal.entities
            )

        template = await get_active_prompt("RiskAssessor", default=RISK_PROMPT_TEMPLATE)
        prompt = template.format(
            title=signal.title,
            priority=signal.priority.value,
            category=signal.category,
            source=signal.source.value,
            content=signal.content,
            entities=entity_str,
        )

        # Thinking OFF for RiskAssessor
        raw_response = await self.llm_complete(prompt, thinking=False)
        result = self._parse_assessment(raw_response)

        # --- Level 2: Compute profile boost ---
        base_exposure = result["exposure"]
        company_matches, profile_boost = self._compute_profile_boost(signal, profile)
        final_exposure = min(base_exposure + profile_boost, 1.0)

        # Compute relevance score from matches
        relevance_score = min(profile_boost / 0.5, 1.0) if profile_boost > 0 else 0.0

        # Compute overall score with personalised exposure
        impact = result["impact"]
        probability = result["probability"]
        overall = impact * probability * final_exposure

        risk_score = RiskScore(
            impact=impact,
            probability=probability,
            exposure=round(final_exposure, 4),
            overall=round(overall, 4),
        )

        self.log.debug(
            "risk_assessor.profile_boost",
            signal_id=signal.id,
            base_exposure=base_exposure,
            profile_boost=round(profile_boost, 4),
            final_exposure=round(final_exposure, 4),
            matches=company_matches,
        )

        return RiskReport(
            signal_id=signal.id,
            risk_score=risk_score,
            evidence=result["evidence"],
            summary=result["summary"],
            initial_priority=signal.priority,
            final_priority=signal.priority,  # May be updated by Loop 2
            company_matches=company_matches,
            relevance_score=round(relevance_score, 4),
        )

    def _compute_profile_boost(
        self, signal: Signal, profile: Any
    ) -> tuple[list[str], float]:
        """Compute profile boost from entity matches against company profile.

        Returns (company_matches, profile_boost).
        """
        matches: list[str] = []
        boost = 0.0

        # Collect all signal text for matching
        signal_text = f"{signal.title} {getattr(signal, 'description', '') or ''} {signal.content or ''}".lower()
        entity_names = set()
        if signal.entities:
            entity_names = {e.name.lower() for e in signal.entities}

        searchable = signal_text + " " + " ".join(entity_names)

        # tech_stack match
        for tech in profile.tech_stack:
            if tech.lower() in searchable:
                matches.append(f"tech_stack:{tech}")
                boost += BOOST_TECH_STACK

        # supplier match
        for supplier in profile.suppliers:
            if supplier.lower() in searchable:
                matches.append(f"supplier:{supplier}")
                boost += BOOST_SUPPLIER

        # region match
        for region in profile.regions:
            if region.lower() in searchable:
                matches.append(f"region:{region}")
                boost += BOOST_REGION

        # regulatory match
        for reg in profile.regulatory_scope:
            if reg.lower() in searchable:
                matches.append(f"regulatory:{reg}")
                boost += BOOST_REGULATORY

        # keyword match
        for keyword in profile.keywords:
            if keyword.lower() in searchable:
                matches.append(f"keyword:{keyword}")
                boost += BOOST_KEYWORD

        return matches, boost

    def _parse_assessment(self, raw: str) -> dict[str, Any]:
        """Parse LLM JSON response into assessment dict."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            self.log.warning(
                "risk_assessor.parse.invalid_json", raw=cleaned[:200]
            )
            return {
                "impact": 0.5,
                "probability": 0.5,
                "exposure": 0.5,
                "evidence": ["Unable to parse LLM response"],
                "summary": "Risk assessment could not be completed.",
            }

        def _clamp(val: Any, default: float = 0.5) -> float:
            try:
                return max(0.0, min(1.0, float(val)))
            except (ValueError, TypeError):
                return default

        evidence = data.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = [str(evidence)]
        evidence = [str(e) for e in evidence]

        return {
            "impact": _clamp(data.get("impact")),
            "probability": _clamp(data.get("probability")),
            "exposure": _clamp(data.get("exposure")),
            "evidence": evidence,
            "summary": str(data.get("summary", "")),
        }
