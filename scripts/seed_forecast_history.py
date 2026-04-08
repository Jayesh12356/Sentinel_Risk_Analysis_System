"""
scripts/seed_forecast_history.py — Level 7 Predictive Risk Intelligence
Seeds 30 historical MemoryEntries per demo tenant spanning the last 90 days
with realistic escalation patterns for ForecastAgent to learn from.

Usage:
    python scripts/seed_forecast_history.py

Requires Qdrant running. Seeds per tenant:
  - 5 CVEs that escalated from P2 → P0 within 48h
  - 3 financial signals that escalated P2 → P1 within 7 days
  - 10 signals that stayed at their original priority (true negatives)
  - 12 additional varied signals across categories
"""
from __future__ import annotations

import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from sentinel.db.qdrant_client import ensure_collection, store_signal

# ── Demo data ────────────────────────────────────────────────────────────────

CVE_ESCALATIONS = [
    {"title": "Log4Shell CVE-2021-44228 initial disclosure [ESCALATED P2→P0 in 24h]",
     "summary": "Apache Log4j vulnerability. Mass exploitation within 24h.", "priority": "P0", "risk": 9.5,
     "entities": ["Apache", "Log4j", "Java", "RCE"], "source": "cyber"},
    {"title": "Citrix Bleed CVE-2023-4966 session token leak [ESCALATED P2→P0 in 36h]",
     "summary": "Unauthenticated session token disclosure via Citrix ADC. LockBit exploited within 36h.", "priority": "P0", "risk": 9.1,
     "entities": ["Citrix", "LockBit", "ADC"], "source": "cyber"},
    {"title": "MOVEit Transfer SQLi CVE-2023-34362 [ESCALATED P2→P0 in 48h]",
     "summary": "Clop ransomware actively exploited within 48h affecting 2000+ orgs.", "priority": "P0", "risk": 9.3,
     "entities": ["MOVEit", "Progress Software", "Clop"], "source": "cyber"},
    {"title": "ProxyLogon Exchange CVE-2021-26855 [ESCALATED P2→P0 in 40h]",
     "summary": "Nation-state HAFNIUM exploitation of Exchange SSRF. Widespread compromise.", "priority": "P0", "risk": 9.0,
     "entities": ["Microsoft Exchange", "HAFNIUM", "APT"], "source": "cyber"},
    {"title": "GoAnyWhere MFT RCE CVE-2023-0669 [ESCALATED P3→P0 in 72h]",
     "summary": "Fortra GoAnyWhere zero-day. Clop mass exploitation of 130+ orgs.", "priority": "P0", "risk": 9.4,
     "entities": ["Fortra", "GoAnyWhere", "Clop", "zero-day"], "source": "cyber"},
]

FINANCIAL_ESCALATIONS = [
    {"title": "SVB deposit run wire transfer spikes [ESCALATED P2→P1 in 168h]",
     "summary": "Silicon Valley Bank unusual outbound wire activity. Bank run within 7 days.", "priority": "P1", "risk": 7.8,
     "entities": ["SVB", "Silicon Valley Bank", "FDIC"], "source": "financial"},
    {"title": "First Republic liquidity concerns SEC disclosure [ESCALATED P2→P1 in 120h]",
     "summary": "First Republic deposit outflows. Systemic risk escalation within 5 days.", "priority": "P1", "risk": 7.5,
     "entities": ["First Republic", "JPMorgan", "FDIC"], "source": "financial"},
    {"title": "Terraform LUNA stablecoin depegging early signal [ESCALATED P2→P1 in 144h]",
     "summary": "UST peg deviation. $40B market cap collapse within 6 days.", "priority": "P1", "risk": 7.2,
     "entities": ["Terraform", "Do Kwon", "LUNA", "UST"], "source": "financial"},
]

TRUE_NEGATIVES = [
    {"title": "Routine NVD Patch Tuesday advisory", "priority": "P3", "risk": 2.0, "entities": ["Microsoft", "Patch Tuesday"], "source": "cyber"},
    {"title": "Minor SEC EDGAR filing delay", "priority": "P3", "risk": 1.5, "entities": ["SEC", "EDGAR"], "source": "financial"},
    {"title": "Low-severity XSS in open-source library", "priority": "P3", "risk": 2.5, "entities": ["npm"], "source": "cyber"},
    {"title": "Quarterly earnings miss 2% within analyst range", "priority": "P3", "risk": 2.0, "entities": ["Earnings"], "source": "financial"},
    {"title": "GDPR notice to SME — minor data handling issue", "priority": "P3", "risk": 1.8, "entities": ["GDPR", "ICO"], "source": "news"},
    {"title": "Phishing simulation 8% click rate — within baseline", "priority": "P2", "risk": 3.5, "entities": ["Phishing"], "source": "cyber"},
    {"title": "Supply chain vendor audit — no material findings", "priority": "P3", "risk": 1.2, "entities": ["Audit"], "source": "news"},
    {"title": "Cloud cost increase Q3 — within variance", "priority": "P3", "risk": 1.0, "entities": ["AWS"], "source": "financial"},
    {"title": "Penetration test informational finding only", "priority": "P3", "risk": 2.2, "entities": ["Pentest"], "source": "cyber"},
    {"title": "CMDB refresh — stale asset records updated", "priority": "P3", "risk": 0.8, "entities": ["CMDB"], "source": "news"},
]

VARIED_SIGNALS = [
    {"title": "SolarWinds Orion supply chain attack analysis", "priority": "P2", "risk": 6.5, "entities": ["SolarWinds", "Orion", "APT29"], "source": "cyber"},
    {"title": "SWIFT messaging system anomaly detected", "priority": "P2", "risk": 6.8, "entities": ["SWIFT", "Bangladesh Bank"], "source": "financial"},
    {"title": "Okta support system breach — customer data", "priority": "P2", "risk": 6.2, "entities": ["Okta", "IAM"], "source": "cyber"},
    {"title": "Colonial Pipeline ransomware early indicators", "priority": "P2", "risk": 7.0, "entities": ["DarkSide", "OT", "Pipeline"], "source": "cyber"},
    {"title": "CISA emergency directive — authentication bypass", "priority": "P2", "risk": 6.9, "entities": ["CISA", "ICS"], "source": "cyber"},
    {"title": "Federal Reserve unexpected rate guidance signals", "priority": "P2", "risk": 5.8, "entities": ["Federal Reserve", "Powell", "Rates"], "source": "financial"},
    {"title": "Zero-click vulnerability in enterprise email", "priority": "P2", "risk": 6.7, "entities": ["Exchange", "zero-click"], "source": "cyber"},
    {"title": "Healthcare clearinghouse outage", "priority": "P2", "risk": 6.3, "entities": ["Change Healthcare", "Claims"], "source": "news"},
    {"title": "EU AI Act compliance deadline approaching", "priority": "P2", "risk": 4.0, "entities": ["EU AI Act", "Compliance"], "source": "news"},
    {"title": "Nation-state APT targeting financial sector", "priority": "P2", "risk": 7.1, "entities": ["APT41", "SWIFT"], "source": "cyber"},
    {"title": "Kubernetes API server misconfiguration found", "priority": "P2", "risk": 6.0, "entities": ["CVE-2024-21626", "K8s"], "source": "cyber"},
    {"title": "Third-party breach affecting SSO integration", "priority": "P2", "risk": 6.4, "entities": ["SSO", "OAuth", "SAML"], "source": "cyber"},
]

TENANT_IDS = ["techcorp", "retailco", "financeinc", "healthco"]


def _make_payload(record: dict, tenant_id: str, days_ago: int) -> tuple[str, str, dict]:
    """Build (signal_id, embed_text, payload) for a historical signal."""
    signal_id = str(uuid.uuid4())
    mem_id = str(uuid.uuid4())
    created = (datetime.now(timezone.utc) - timedelta(days=days_ago, hours=random.randint(0, 8))).isoformat()

    title = record["title"]
    summary = record.get("summary", title)
    entities = record.get("entities", [])

    embed_text = f"{title} {summary} {' '.join(entities)}"
    payload = {
        "id": mem_id,
        "signal_id": signal_id,
        "title": title,
        "summary": summary,
        "entities": entities,
        "priority": record["priority"],
        "risk_score": record.get("risk", 5.0),
        "route_path": "FULL",
        "company_matches": [],
        "relevance_score": random.uniform(0.6, 0.95),
        "source": record.get("source", "cyber"),
        "outcome": "processed",
        "created_at": created,
    }
    return mem_id, embed_text, payload


async def seed_tenant(tenant_id: str) -> int:
    collection = f"{tenant_id}_memory"
    await ensure_collection(collection)

    records = []
    days_cursor = 90

    for record in CVE_ESCALATIONS:
        records.append((record, days_cursor))
        days_cursor -= random.randint(5, 8)

    for record in FINANCIAL_ESCALATIONS:
        records.append((record, days_cursor))
        days_cursor -= random.randint(6, 10)

    for record in TRUE_NEGATIVES:
        records.append((record, days_cursor))
        days_cursor -= random.randint(1, 2)

    for record in VARIED_SIGNALS:
        records.append((record, max(1, days_cursor)))
        days_cursor -= random.randint(0, 1)

    for record, days_ago in records:
        mem_id, embed_text, payload = _make_payload(record, tenant_id, days_ago)
        await store_signal(
            signal_id=mem_id,
            text=embed_text,
            payload=payload,
            collection_name=collection,
        )

    print(f"[OK] {len(records)} historical entries seeded for {tenant_id}")
    return len(records)


async def main() -> None:
    print("Seeding Level 7 forecast history (30 entries × 4 tenants)...")
    total = 0
    for tenant_id in TENANT_IDS:
        total += await seed_tenant(tenant_id)
    print(f"\nDone. Total: {total} entries seeded.")
    print("ForecastAgent now has historical escalation patterns to learn from.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
