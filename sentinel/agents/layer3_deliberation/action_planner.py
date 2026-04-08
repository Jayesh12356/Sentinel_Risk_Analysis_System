"""ActionPlanner — decides which actions to take (Level 8, thinking=ON).

LangGraph node: runs AFTER ArbiterAgent, BEFORE BriefWriter (Path A only).
Receives signal, risk_report, arbiter verdict, company_profile.
Applies confidence-gated autonomy:
  - HIGH (>= 0.85): auto-execute via ActionEngine
  - MED  (0.60-0.84): store as PENDING_APPROVAL
  - LOW  (< 0.60): REPORT_ONLY
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from sentinel.config import get_settings
from sentinel.models.action_entry import ActionEntry, ActionStatus, ActionType
from sentinel.actions.engine import ActionEngine
from sentinel.actions.registry import get_enabled_actions, ActionConfig

logger = structlog.get_logger(__name__)


class ActionPlanner:
    """Plans and gates autonomous actions based on signal analysis."""

    def __init__(self, demo_mode: bool = False) -> None:
        self.demo_mode = demo_mode
        self.engine = ActionEngine()

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Plan actions for all processed signals and execute/queue them."""
        signals = state.get("signals", [])
        risk_reports = state.get("risk_reports", [])
        tenant_ctx = state.get("tenant_context")
        tenant_id = tenant_ctx.tenant_id if tenant_ctx else get_settings().ACTIVE_TENANT
        forecasts = state.get("forecasts", [])

        # Get enabled actions for this tenant
        enabled_configs = await get_enabled_actions(tenant_id)
        if not enabled_configs:
            logger.info("action_planner.no_enabled_actions", tenant_id=tenant_id)
            return {"actions": []}

        settings = get_settings()
        all_actions: list[ActionEntry] = []

        # Build report lookup
        report_map: dict[str, Any] = {}
        for r in risk_reports:
            if hasattr(r, "signal_id"):
                report_map[str(r.signal_id)] = r

        for signal in signals:
            sid = str(signal.id)
            report = report_map.get(sid)
            priority = str(signal.priority) if hasattr(signal, "priority") else "P3"

            # Only plan actions for P0/P1 signals (high priority)
            # or P2 signals with forecasts predicting escalation
            should_plan = priority in ("P0", "P1")
            if not should_plan and forecasts:
                # Check if any forecast predicts this signal will escalate
                for fc in forecasts:
                    if hasattr(fc, "signal_id") and str(fc.signal_id) == sid:
                        if hasattr(fc, "probability") and fc.probability >= 0.70:
                            should_plan = True
                            break

            if not should_plan:
                continue

            # Determine actions via LLM (or heuristic in demo mode)
            planned = await self._plan_actions_for_signal(
                signal=signal,
                report=report,
                priority=priority,
                tenant_id=tenant_id,
                enabled_configs=enabled_configs,
                settings=settings,
            )
            all_actions.extend(planned)

        # Apply confidence gate and execute/queue
        executed_actions = []
        for action in all_actions:
            action = self._apply_confidence_gate(action, settings, enabled_configs)

            if action.status == ActionStatus.AUTO_EXECUTED:
                # Execute immediately
                action = await self.engine.execute(action)
            elif action.status == ActionStatus.PENDING_APPROVAL:
                logger.info(
                    "action_planner.pending",
                    action_id=action.id,
                    action_type=action.action_type.value,
                    confidence=action.confidence,
                )
            else:
                logger.info(
                    "action_planner.report_only",
                    action_id=action.id,
                    action_type=action.action_type.value,
                    confidence=action.confidence,
                )

            executed_actions.append(action)

        logger.info(
            "action_planner.done",
            total=len(executed_actions),
            auto=sum(1 for a in executed_actions if a.status == ActionStatus.AUTO_EXECUTED),
            pending=sum(1 for a in executed_actions if a.status == ActionStatus.PENDING_APPROVAL),
            report_only=sum(1 for a in executed_actions if a.status == ActionStatus.REPORT_ONLY),
        )

        return {"actions": executed_actions}

    async def _plan_actions_for_signal(
        self,
        signal: Any,
        report: Any,
        priority: str,
        tenant_id: str,
        enabled_configs: list[ActionConfig],
        settings: Any,
    ) -> list[ActionEntry]:
        """Determine which actions to create for a given signal."""
        actions: list[ActionEntry] = []
        sid = str(signal.id)
        title = getattr(signal, "title", str(signal.id))

        # Build context for action planning
        risk_score = 0.0
        reasoning_context = ""
        if report:
            risk_score = getattr(report, "overall_risk_score", 0.0)
            reasoning_context = getattr(report, "summary", "")

        # Determine base confidence from priority + risk score
        base_confidence = self._compute_base_confidence(priority, risk_score)

        enabled_types = {c.action_type for c in enabled_configs}

        # P0 signals: page on-call + Slack + Jira
        if priority == "P0":
            if ActionType.PAGERDUTY_ALERT in enabled_types:
                actions.append(ActionEntry(
                    tenant_id=tenant_id,
                    signal_id=sid,
                    action_type=ActionType.PAGERDUTY_ALERT,
                    title=f"🚨 P0 Alert: {title}",
                    description=f"Critical P0 signal detected. Risk score: {risk_score:.2f}",
                    payload={"severity": "critical", "component": "sentinel"},
                    reasoning=f"P0 priority signal requires immediate on-call notification. {reasoning_context}",
                    confidence=min(base_confidence + 0.10, 1.0),
                ))

            if ActionType.SLACK_MESSAGE in enabled_types:
                actions.append(ActionEntry(
                    tenant_id=tenant_id,
                    signal_id=sid,
                    action_type=ActionType.SLACK_MESSAGE,
                    title=f"Security Alert: {title}",
                    description=f"P0 signal detected with risk score {risk_score:.2f}",
                    payload={"channel": "#security-alerts"},
                    reasoning=f"All P0 signals should be broadcast immediately. {reasoning_context}",
                    confidence=min(base_confidence + 0.10, 1.0),
                ))

            if ActionType.JIRA_TICKET in enabled_types:
                actions.append(ActionEntry(
                    tenant_id=tenant_id,
                    signal_id=sid,
                    action_type=ActionType.JIRA_TICKET,
                    title=f"[SENTINEL] {title}",
                    description=f"Automated incident ticket for P0 signal.\n\nRisk Score: {risk_score:.2f}\n\n{reasoning_context}",
                    payload={"issue_type": "Bug", "priority": "Highest"},
                    reasoning=f"P0 signal requires incident tracking. {reasoning_context}",
                    confidence=base_confidence,
                ))

        # P1 signals: Slack + Jira + Email draft
        elif priority == "P1":
            if ActionType.SLACK_MESSAGE in enabled_types:
                actions.append(ActionEntry(
                    tenant_id=tenant_id,
                    signal_id=sid,
                    action_type=ActionType.SLACK_MESSAGE,
                    title=f"⚠️ P1 Alert: {title}",
                    description=f"High-priority signal. Risk score: {risk_score:.2f}",
                    payload={"channel": "#security-alerts"},
                    reasoning=f"P1 signals should be communicated to the security team. {reasoning_context}",
                    confidence=base_confidence,
                ))

            if ActionType.JIRA_TICKET in enabled_types:
                actions.append(ActionEntry(
                    tenant_id=tenant_id,
                    signal_id=sid,
                    action_type=ActionType.JIRA_TICKET,
                    title=f"[SENTINEL] {title}",
                    description=f"P1 signal - requires investigation.\n\nRisk Score: {risk_score:.2f}\n\n{reasoning_context}",
                    payload={"issue_type": "Task", "priority": "High"},
                    reasoning=f"P1 signal needs tracking for investigation. {reasoning_context}",
                    confidence=base_confidence - 0.05,
                ))

            if ActionType.EMAIL_DRAFT in enabled_types:
                actions.append(ActionEntry(
                    tenant_id=tenant_id,
                    signal_id=sid,
                    action_type=ActionType.EMAIL_DRAFT,
                    title=f"Incident Notification: {title}",
                    description=f"A P1 security incident has been detected.\n\nDetails: {reasoning_context}",
                    payload={"template": "incident_notification"},
                    reasoning=f"Stakeholders should be notified about P1 incidents. {reasoning_context}",
                    confidence=base_confidence - 0.10,
                ))

        # P2 with high forecast — alert only
        else:
            if ActionType.SLACK_MESSAGE in enabled_types:
                actions.append(ActionEntry(
                    tenant_id=tenant_id,
                    signal_id=sid,
                    action_type=ActionType.SLACK_MESSAGE,
                    title=f"📊 Forecast Alert: {title}",
                    description=f"P2 signal with predicted escalation. Risk score: {risk_score:.2f}",
                    payload={"channel": "#security-alerts"},
                    reasoning=f"Signal forecast predicts escalation to higher priority. {reasoning_context}",
                    confidence=base_confidence - 0.15,
                ))

        # Level 9: Supplier risk detection — triggers INITIATE_NEGOTIATION
        if (
            ActionType.INITIATE_NEGOTIATION in enabled_types
            and settings.NEGOTIATION_ENABLED
            and priority in ("P0", "P1")
            and risk_score >= 0.70
        ):
            supplier_risk = self._detect_supplier_risk(signal, report, reasoning_context)
            if supplier_risk:
                actions.append(ActionEntry(
                    tenant_id=tenant_id,
                    signal_id=sid,
                    action_type=ActionType.INITIATE_NEGOTIATION,
                    title=f"🤝 Negotiate: {supplier_risk['supplier']}",
                    description=f"Supplier '{supplier_risk['supplier']}' at risk. Initiating alternative search.",
                    payload={"supplier_name": supplier_risk["supplier"]},
                    reasoning=f"Supplier risk detected: {supplier_risk['reason']}. {reasoning_context}",
                    confidence=base_confidence - 0.05,
                ))

        return actions

    def _compute_base_confidence(self, priority: str, risk_score: float) -> float:
        """Compute base confidence from priority and risk score."""
        priority_weights = {"P0": 0.90, "P1": 0.80, "P2": 0.65, "P3": 0.50}
        base = priority_weights.get(priority, 0.50)
        # risk_score (0-1) adds up to 0.10 confidence
        return min(base + risk_score * 0.10, 1.0)

    def _apply_confidence_gate(
        self,
        action: ActionEntry,
        settings: Any,
        enabled_configs: list[ActionConfig],
    ) -> ActionEntry:
        """Apply confidence-gated autonomy rules."""
        auto_threshold = settings.ACTION_AUTO_THRESHOLD
        approval_threshold = settings.ACTION_APPROVAL_THRESHOLD

        # Check if this action type allows auto-execution
        config = next(
            (c for c in enabled_configs if c.action_type == action.action_type),
            None,
        )
        can_auto = config.auto_execute if config else False

        if action.confidence >= auto_threshold and can_auto:
            action.status = ActionStatus.AUTO_EXECUTED
        elif action.confidence >= approval_threshold:
            action.status = ActionStatus.PENDING_APPROVAL
        else:
            action.status = ActionStatus.REPORT_ONLY

        return action

    def _detect_supplier_risk(
        self,
        signal: Any,
        report: Any,
        reasoning_context: str,
    ) -> dict | None:
        """Detect if a signal involves supplier risk (Level 9).

        Returns {"supplier": name, "reason": description} or None.
        """
        RISK_KEYWORDS = [
            "bankruptcy", "bankrupt", "insolvent", "insolvency",
            "acquisition", "acquired", "merger",
            "disruption", "supply chain", "supply-chain",
            "sanctions", "sanctioned", "embargo",
            "shutdown", "shut down", "wind down", "cease operations",
            "data breach", "compromised",
        ]

        # Build text to scan
        text_to_scan = ""
        title = getattr(signal, "title", "")
        content = getattr(signal, "content", "")
        text_to_scan = f"{title} {content} {reasoning_context}".lower()

        # Check for risk keywords
        risk_found = any(kw in text_to_scan for kw in RISK_KEYWORDS)
        if not risk_found:
            return None

        # Try to match a known supplier from company profile
        try:
            from sentinel.profile.manager import get_active_profile
            profile = get_active_profile()
            suppliers = profile.suppliers or []
        except Exception:
            suppliers = []

        # Check entities in signal for supplier names
        entities = getattr(signal, "entities", []) or []
        entity_names = [getattr(e, "name", str(e)) for e in entities]

        matched_supplier = None
        # Check signal entities against known suppliers
        for supplier in suppliers:
            supplier_lower = supplier.lower()
            if supplier_lower in text_to_scan:
                matched_supplier = supplier
                break
            for ename in entity_names:
                if supplier_lower in ename.lower() or ename.lower() in supplier_lower:
                    matched_supplier = supplier
                    break
            if matched_supplier:
                break

        # If no match from profile, use the first entity that looks like a company
        if not matched_supplier and entity_names:
            matched_supplier = entity_names[0]

        if not matched_supplier:
            return None

        # Determine the specific risk reason
        reason = "Supply chain disruption"
        for kw in RISK_KEYWORDS:
            if kw in text_to_scan:
                reason = kw.replace("_", " ").title()
                break

        return {"supplier": matched_supplier, "reason": reason}
