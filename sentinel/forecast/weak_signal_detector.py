"""
sentinel/forecast/weak_signal_detector.py — Level 7 Predictive Risk Intelligence
Pure-Python pre-pipeline step that flags signals with low priority but high escalation potential.

No LLM calls. Uses pattern matching on signal metadata.
Output: weak_signal_flags: Dict[signal_id, List[str]] injected into PipelineState.
"""
from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# CVE reference pattern (e.g. CVE-2024-12345)
CVE_PATTERN = re.compile(r"CVE-\d{4}-\d+", re.IGNORECASE)

# Keywords suggesting escalation potential
ESCALATION_KEYWORDS = [
    "zero-day", "0-day", "remote code execution", "rce", "unauthenticated",
    "critical infrastructure", "supply chain", "systemic", "clearinghouse",
    "federal reserve", "sec filing", "regulatory action", "class action",
    "ransomware", "nation-state", "apt", "advanced persistent",
    "mass exploitation", "exploit kit", "proof of concept", "poc available",
    "widely exploited", "actively exploited",
]

# Entities whose signals warrant extra scrutiny regardless of priority
HIGH_IMPORTANCE_ENTITY_PATTERNS = [
    r"\bFederal Reserve\b", r"\bSEC\b", r"\bCISA\b", r"\bNSA\b",
    r"\bMicrosoft\b", r"\bCrowdStrike\b", r"\bSolarwinds\b", r"\bOkta\b",
    r"\bAWS\b", r"\bGoogle Cloud\b", r"\bAzure\b",
    r"\bjpmorgan\b", r"\bgoldman sachs\b", r"\bciti\b", r"\bblackrock\b",
]
_ENTITY_RE = [re.compile(p, re.IGNORECASE) for p in HIGH_IMPORTANCE_ENTITY_PATTERNS]


def _count_cve_refs(text: str) -> int:
    return len(CVE_PATTERN.findall(text))


def _has_escalation_keyword(text: str) -> list[str]:
    text_lower = text.lower()
    return [kw for kw in ESCALATION_KEYWORDS if kw in text_lower]


def _has_high_importance_entity(text: str) -> bool:
    return any(r.search(text) for r in _ENTITY_RE)


def detect(
    signals: list[Any],
    tenant_context: Any | None = None,
    shared_patterns: list[Any] | None = None,
) -> dict[str, list[str]]:
    """Analyse signals for weak signal indicators.

    Args:
        signals:         List of Signal objects from the pipeline.
        tenant_context:  TenantContext (unused but accepted for future use).
        shared_patterns: Shared cross-company patterns from SharedPatternReader
                         (used for cross-tenant pattern match check).

    Returns:
        Dict mapping signal_id → List[str] of flag reasons.
        Only includes signals with at least one flag.
    """
    flags: dict[str, list[str]] = {}

    shared_keywords: list[str] = []
    if shared_patterns:
        for sp in shared_patterns:
            desc = getattr(sp, "description", "") or ""
            shared_keywords.extend(
                w.lower() for w in desc.split() if len(w) > 5
            )

    for signal in signals:
        signal_id = str(getattr(signal, "id", "") or "")
        if not signal_id:
            continue

        priority = getattr(signal, "priority", "P2") or "P2"
        # Only flag P2 and P3 signals (P0/P1 already critical)
        if priority in ("P0", "P1"):
            continue

        title = getattr(signal, "title", "") or ""
        content = getattr(signal, "content", "") or ""
        full_text = f"{title} {content}"
        signal_flags: list[str] = []

        # ── Check 1: CVE reference count ────────────────────────────────
        cve_count = _count_cve_refs(full_text)
        if cve_count >= 3:
            signal_flags.append(
                f"HIGH_CVE_DENSITY: {cve_count} CVE references detected"
            )

        # ── Check 2: Escalation keywords ────────────────────────────────
        matched_kws = _has_escalation_keyword(full_text)
        if matched_kws:
            signal_flags.append(
                f"ESCALATION_KEYWORDS: {', '.join(matched_kws[:3])}"
            )

        # ── Check 3: High-importance entity ─────────────────────────────
        if _has_high_importance_entity(full_text):
            signal_flags.append("HIGH_IMPORTANCE_ENTITY: systemically significant entity detected")

        # ── Check 4: Cross-tenant pattern match ─────────────────────────
        if shared_keywords:
            text_lower = full_text.lower()
            matched_shared = [kw for kw in shared_keywords if kw in text_lower]
            if len(matched_shared) >= 3:
                signal_flags.append(
                    f"CROSS_TENANT_PATTERN_MATCH: matches {len(matched_shared)} shared threat keywords"
                )

        # ── Check 5: Low CVSS but critical system ───────────────────────
        # Look for "CVSS: X.Y" or "CVSS score: X" patterns where X < 7
        cvss_match = re.search(r"cvss[:\s]+(\d+\.?\d*)", full_text, re.IGNORECASE)
        if cvss_match:
            try:
                cvss_score = float(cvss_match.group(1))
                if cvss_score < 7.0 and _has_high_importance_entity(full_text):
                    signal_flags.append(
                        f"LOW_CVSS_HIGH_IMPORTANCE: CVSS {cvss_score} on critical system"
                    )
            except ValueError:
                pass

        if signal_flags:
            flags[signal_id] = signal_flags
            logger.info(
                "weak_signal.flagged",
                signal_id=signal_id,
                priority=priority,
                flags=signal_flags,
            )

    logger.info(
        "weak_signal_detector.done",
        total_signals=len(signals),
        flagged=len(flags),
    )
    return flags
