"""
sentinel/agents/layer1_processing/forecast_agent.py — Level 7 Predictive Risk Intelligence
ForecastAgent: predicts probability of P2/P3 signal escalation to P0/P1 within 72h.

Position in pipeline: AFTER SignalClassifier, BEFORE RouterAgent.
Runs on every P2/P3 signal. Uses Gemini thinking=ON for deep reasoning.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from sentinel.agents.base import BaseAgent
from sentinel.config import settings
from sentinel.db import qdrant_client as db
from sentinel.forecast import store as forecast_store
from sentinel.models.forecast_entry import ForecastEntry, ForecastHorizon, ForecastOutcome
from sentinel.models.signal import SignalPriority
from sentinel.pipeline.state import PipelineState

logger = structlog.get_logger(__name__)

# Targets for prediction (only non-critical signals are forecast candidates)
FORECAST_SOURCE_PRIORITIES = {"P2", "P3"}
FORECAST_TARGET_PRIORITY = {"P2": "P0", "P3": "P1"}

FORECAST_PROMPT = """You are SENTINEL's ForecastAgent. Your task is to predict whether this signal will escalate in priority within the forecast horizon.

## Signal Under Analysis
Title: {signal_title}
Current Priority: {current_priority}
Category: {category}
Entities: {entities}
Content: {content}

## Weak Signal Flags (pre-computed heuristics)
{weak_signal_flags}

## Historical Escalation Patterns (from memory — similar past signals)
{historical_context}

## Cross-Company Threat Intelligence (anonymised shared patterns)
{shared_context}

## Your Historical Forecast Accuracy
Past accuracy rate: {accuracy_rate:.0%} ({correct} correct / {resolved} resolved)
{accuracy_note}

## Task
Evaluate the probability that this {current_priority} signal escalates to {target_priority} or higher within {horizon}.

Respond ONLY with valid JSON:
{{
  "probability": <float 0.0-1.0>,
  "horizon": "<H24|H48|H72|H7D>",
  "predicted_priority": "<P0|P1>",
  "reasoning": "<2-3 sentences explaining your prediction>",
  "evidence": ["<historical signal or pattern that supports this>", "..."]
}}

Be calibrated: only forecast high probability (>0.7) when you have strong historical evidence.
If insufficient history, be conservative and lean toward 0.4-0.6."""


class ForecastAgent(BaseAgent):
    """Predicts escalation probability for P2/P3 signals.

    Uses:
      1. {tenant_id}_memory similarity search for historical escalation signals
      2. sentinel_shared_patterns for cross-company threat context
      3. {tenant_id}_forecasts past accuracy for self-calibration
      4. Gemini with thinking=ON for probability estimate
    """

    agent_name = "ForecastAgent"

    async def run(self, state: PipelineState) -> PipelineState:
        """Run ForecastAgent on all P2/P3 signals in state.

        Skips:
          - P0/P1 signals (already critical)
          - Signals where FORECAST_ENABLED=False
          - Tenants with < FORECAST_MIN_HISTORY past signals

        Stores ForecastEntry in Qdrant and fires predictive alert if
        probability > FORECAST_ALERT_THRESHOLD.
        """
        if not settings.FORECAST_ENABLED:
            self.log.info("forecast_agent.disabled")
            state["forecasts"] = state.get("forecasts", [])
            return state

        signals = state.get("signals", [])
        tenant_context = state.get("tenant_context")
        tenant_id = tenant_context.tenant_id if tenant_context else settings.ACTIVE_TENANT
        memory_collection = f"{tenant_id}_memory"
        shared_collection = settings.QDRANT_SHARED_COLLECTION
        weak_flags = state.get("weak_signal_flags", {})
        shared_patterns = state.get("shared_patterns", [])

        # Get past accuracy for self-calibration
        accuracy_data = await forecast_store.get_accuracy(tenant_id)
        accuracy_rate = accuracy_data.get("rate", 0.0)
        correct = accuracy_data.get("correct", 0)
        resolved = accuracy_data.get("correct", 0) + accuracy_data.get("incorrect", 0)

        forecast_entries: list[ForecastEntry] = []

        for signal in signals:
            priority_val = getattr(signal, "priority", None)
            priority_str = (
                priority_val.value if hasattr(priority_val, "value") else str(priority_val)
            ) if priority_val else "P2"

            if priority_str not in FORECAST_SOURCE_PRIORITIES:
                continue

            signal_id = str(signal.id)
            signal_title = getattr(signal, "title", "Unknown signal")
            category = str(getattr(signal, "category", "UNKNOWN"))
            content = str(getattr(signal, "content", ""))[:300]
            entities = getattr(signal, "entities", []) or []
            entities_str = ", ".join(str(e) for e in entities) if entities else "None extracted"

            # ── Weak signal flags for this signal ───────────────────────────
            flags = weak_flags.get(signal_id, [])
            flags_text = "\n".join(f"  - {f}" for f in flags) if flags else "  None detected"

            # ── Historical memory search ─────────────────────────────────────
            historical_context = await self._get_historical_context(
                signal_title=signal_title,
                content=content,
                memory_collection=memory_collection,
            )

            # ── Check minimum history requirement ────────────────────────────
            if accuracy_data.get("total", 0) == 0 and not historical_context.strip():
                # No history — still forecast but be conservative
                self.log.info(
                    "forecast_agent.no_history",
                    signal_id=signal_id,
                    note="forecasting without historical data",
                )

            # ── Shared pattern context ───────────────────────────────────────
            shared_context = self._format_shared_context(shared_patterns)

            # ── Accuracy calibration note ────────────────────────────────────
            if resolved >= settings.FORECAST_MIN_HISTORY:
                if accuracy_rate < 0.5:
                    accuracy_note = "⚠ Your past accuracy is below 50% — be conservative, reduce estimates by 0.1."
                elif accuracy_rate > 0.8:
                    accuracy_note = "✓ Your past accuracy is above 80% — you can be slightly more confident (add 0.05)."
                else:
                    accuracy_note = "Your accuracy is in a normal range."
            else:
                accuracy_note = f"Insufficient resolved forecasts ({resolved} < {settings.FORECAST_MIN_HISTORY}) for calibration. Use base rates."

            target_priority = FORECAST_TARGET_PRIORITY.get(priority_str, "P0")
            horizon_str = settings.FORECAST_HORIZON_DEFAULT  # e.g. "H72"

            prompt = FORECAST_PROMPT.format(
                signal_title=signal_title,
                current_priority=priority_str,
                category=category,
                entities=entities_str,
                content=content,
                weak_signal_flags=flags_text,
                historical_context=historical_context,
                shared_context=shared_context,
                accuracy_rate=accuracy_rate,
                correct=correct,
                resolved=resolved,
                accuracy_note=accuracy_note,
                target_priority=target_priority,
                horizon=horizon_str,
            )

            # ── LLM call with thinking=ON ────────────────────────────────────
            result = await self._call_llm(
                prompt=prompt,
                signal_id=signal_id,
                signal_title=signal_title,
                priority_str=priority_str,
                target_priority=target_priority,
                category=category,
            )

            if result is None:
                continue

            probability = result.get("probability", 0.0)
            if probability < settings.FORECAST_MIN_PROBABILITY:
                self.log.info(
                    "forecast_agent.below_threshold",
                    signal_id=signal_id,
                    probability=probability,
                    threshold=settings.FORECAST_MIN_PROBABILITY,
                )
                continue

            # Map horizon string to enum safely
            try:
                horizon = ForecastHorizon(result.get("horizon", horizon_str))
            except ValueError:
                horizon = ForecastHorizon(horizon_str)

            entry = ForecastEntry(
                tenant_id=tenant_id,
                signal_id=signal_id,
                signal_title=signal_title,
                signal_category=category,
                current_priority=priority_str,
                predicted_priority=result.get("predicted_priority", target_priority),
                probability=min(1.0, max(0.0, probability)),
                horizon=horizon,
                reasoning=result.get("reasoning", ""),
                evidence=result.get("evidence", []),
                outcome=ForecastOutcome.PENDING,
            )

            # ── Store in Qdrant ──────────────────────────────────────────────
            try:
                await forecast_store.save_forecast(entry)
                forecast_entries.append(entry)
                self.log.info(
                    "forecast_agent.saved",
                    signal_id=signal_id,
                    probability=entry.probability,
                    horizon=entry.horizon.value,
                )
            except Exception:
                self.log.exception("forecast_agent.save_error", signal_id=signal_id)
                forecast_entries.append(entry)  # Still surface in state even if not persisted

            # ── Fire predictive alert if high probability ────────────────────
            if entry.probability > settings.FORECAST_ALERT_THRESHOLD:
                await self._fire_predictive_alert(entry)

        state["forecasts"] = state.get("forecasts", []) + forecast_entries
        self.log.info(
            "forecast_agent.done",
            tenant=tenant_id,
            signals_evaluated=sum(
                1 for s in signals
                if (getattr(s, "priority", None) and
                    (getattr(s.priority, "value", str(s.priority)) in FORECAST_SOURCE_PRIORITIES))
            ),
            forecasts_created=len(forecast_entries),
        )
        return state

    async def _get_historical_context(
        self,
        signal_title: str,
        content: str,
        memory_collection: str,
    ) -> str:
        """Query memory for historically similar signals that escalated."""
        try:
            query = f"{signal_title} {content[:100]}"
            hits = await db.search(
                query_text=query,
                limit=5,
                collection_name=memory_collection,
                score_threshold=0.60,
            )
            if not hits:
                return "  No similar historical signals found."

            lines = []
            for hit in hits:
                p = hit.payload or {}
                title = p.get("title", "Unknown")
                priority = p.get("priority", "?")
                risk = p.get("risk_score", 0)
                date = p.get("created_at", "")[:10]
                lines.append(f"  - [{date}] {title} (priority={priority}, risk={risk:.1f})")

            return "\n".join(lines)
        except Exception:
            self.log.exception("forecast_agent.history_error")
            return "  Historical data unavailable (Qdrant offline?)."

    def _format_shared_context(self, shared_patterns: list) -> str:
        """Format shared cross-company patterns for prompt injection."""
        if not shared_patterns:
            return "  No shared patterns available."
        lines = []
        for sp in shared_patterns[:4]:
            desc = getattr(sp, "description", "") or str(sp)[:100]
            ptype = getattr(sp, "pattern_type", "UNKNOWN")
            tc = getattr(sp, "tenant_count", 1)
            lines.append(f"  - [{ptype}] {desc[:80]} (seen in {tc}+ orgs)")
        return "\n".join(lines) or "  None available."

    async def _call_llm(
        self,
        prompt: str,
        signal_id: str,
        signal_title: str,
        priority_str: str,
        target_priority: str,
        category: str,
    ) -> dict[str, Any] | None:
        """Call Gemini with thinking=ON and parse JSON response."""
        # Demo mode fallback
        if self.demo_mode:
            return self._demo_forecast(priority_str, target_priority, signal_title)

        try:
            raw = await self.complete(
                prompt=prompt,
                thinking=True,
                json_mode=False,
            )
            # Extract JSON from response (may be wrapped in markdown)
            json_str = raw
            if "```json" in raw:
                json_str = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                json_str = raw.split("```")[1].split("```")[0].strip()
            elif "{" in raw:
                start = raw.index("{")
                end = raw.rindex("}") + 1
                json_str = raw[start:end]

            return json.loads(json_str)

        except json.JSONDecodeError:
            self.log.warning(
                "forecast_agent.json_parse_error",
                signal_id=signal_id,
                raw_preview=str(raw)[:200] if "raw" in dir() else "N/A",
            )
            return None
        except Exception:
            self.log.exception("forecast_agent.llm_error", signal_id=signal_id)
            return None

    def _demo_forecast(
        self,
        priority_str: str,
        target_priority: str,
        signal_title: str,
    ) -> dict[str, Any]:
        """Return a realistic demo forecast without calling LLM."""
        import random as _random
        prob = round(_random.uniform(0.55, 0.92), 2)
        return {
            "probability": prob,
            "horizon": "H72",
            "predicted_priority": target_priority,
            "reasoning": (
                f"[DEMO] Based on historical patterns, this {priority_str} signal shows "
                f"characteristics consistent with prior escalations. "
                f"Probability of reaching {target_priority} within 72h estimated at {prob:.0%}."
            ),
            "evidence": [
                "Historical CVE escalation pattern match (Log4Shell-like velocity)",
                "Cross-company shared threat intelligence confirms similar pattern",
            ],
        }

    async def _fire_predictive_alert(self, entry: ForecastEntry) -> None:
        """Fire a predictive alert log entry (email/Slack handled by dispatcher)."""
        self.log.warning(
            "forecast_agent.predictive_alert",
            forecast_id=entry.id,
            signal_title=entry.signal_title,
            current_priority=entry.current_priority,
            predicted_priority=entry.predicted_priority,
            probability=entry.probability,
            horizon=entry.horizon.value,
            subject=f"[SENTINEL FORECAST] {entry.predicted_priority} predicted in {entry.horizon.value}",
        )
        # Future: integrate with alert_dispatcher.send_forecast_alert(entry)
