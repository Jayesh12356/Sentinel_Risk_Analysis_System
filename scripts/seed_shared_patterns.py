"""seed_shared_patterns.py — Seed anonymised cross-company threat patterns.

Seeds 6 demo SharedPattern records into the sentinel_shared_patterns Qdrant
collection to demonstrate the Level 6 federated intelligence layer.

3 patterns span 2+ companies, showing cross-company value.
All patterns are fully anonymised — zero company names or identifiers.

Usage:
    python scripts/seed_shared_patterns.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

logger = structlog.get_logger(__name__)


# ── 6 anonymised patterns ─────────────────────────────────────────────────
# 3 multi-sector overlapping patterns (supply chain attack, ransomware on
# EHR/data stores, supply chain vendor exploitation)
# 3 sector-specific patterns

DEMO_PATTERNS = [
    {
        # CROSS-SECTOR: supply chain via third-party vendor — seen by RetailCo + TechCorp
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "supply-chain-3pl-compromise")),
        "pattern_type": "SUPPLY_CHAIN",
        "description": "Third-party software vendor update mechanism compromised, delivering malicious payload to downstream client environments. Attackers inserted backdoor code during the vendor's automated build pipeline.",
        "entities_generic": ["third-party vendor", "software update mechanism", "build pipeline"],
        "source_type": "NEWS",
        "priority": "P1",
        "risk_score": 0.89,
        "occurrence_count": 2,
        "first_seen": "2024-11-01T00:00:00Z",
        "last_seen": "2024-12-15T00:00:00Z",
        "tenant_count": 2,
        "mitre_techniques": ["T1195.002", "T1059"],
        "sector_relevance": ["Technology", "Retail", "Financial Services"],
        "remediation_hint": "Audit all third-party software update channels; enforce build pipeline integrity checks (SLSA framework); validate vendor SBOM.",
    },
    {
        # CROSS-SECTOR: ransomware targeting critical data stores — seen by HealthCo + FinanceInc
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "ransomware-critical-data-stores")),
        "pattern_type": "RANSOMWARE",
        "description": "Ransomware campaign targeting organisations with high-value structured data stores (EHR, trading databases, ERP). Initial access via phishing, lateral movement via credential dumping, encryption of primary data stores within 72 hours.",
        "entities_generic": ["phishing email", "credential harvesting tool", "primary database"],
        "source_type": "CYBER_THREAT",
        "priority": "P1",
        "risk_score": 0.94,
        "occurrence_count": 2,
        "first_seen": "2024-10-10T00:00:00Z",
        "last_seen": "2025-01-05T00:00:00Z",
        "tenant_count": 2,
        "mitre_techniques": ["T1566.002", "T1003.001", "T1486"],
        "sector_relevance": ["Healthcare", "Financial Services"],
        "remediation_hint": "Implement LSASS protection (Credential Guard); enforce MFA on all admin accounts; maintain offline backups tested for healthcare-grade RTO.",
    },
    {
        # CROSS-SECTOR: IAM credential exposure via public source code — seen by TechCorp + FinanceInc
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "iam-credential-exfil-public-repo")),
        "pattern_type": "DATA_BREACH",
        "description": "Cloud infrastructure credentials (IAM keys, service account tokens) inadvertently committed to public version control repositories. Automated scanning bots harvest credentials within minutes of commit and use them to access cloud environments.",
        "entities_generic": ["cloud IAM credentials", "version control repository", "automation bot"],
        "source_type": "NEWS",
        "priority": "P1",
        "risk_score": 0.87,
        "occurrence_count": 3,
        "first_seen": "2024-09-01T00:00:00Z",
        "last_seen": "2025-02-01T00:00:00Z",
        "tenant_count": 2,
        "mitre_techniques": ["T1552.001", "T1552.004"],
        "sector_relevance": ["Technology", "Financial Services"],
        "remediation_hint": "Implement pre-commit secret scanning hooks (gitleaks/truffleHog); rotate all cloud credentials quarterly; enable audit logging on all IAM activity.",
    },
    {
        # SECTOR-SPECIFIC: healthcare PHI exfiltration via API misconfiguration
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "phi-api-oauth-misconfiguration")),
        "pattern_type": "DATA_BREACH",
        "description": "Patient health information exposed via misconfigured OAuth2 scope in a patient-facing health record API. Authenticated users could access other patients' records through predictable FHIR resource identifiers.",
        "entities_generic": ["patient portal API", "OAuth2 configuration", "health record database"],
        "source_type": "CYBER_THREAT",
        "priority": "P1",
        "risk_score": 0.88,
        "occurrence_count": 1,
        "first_seen": "2025-01-15T00:00:00Z",
        "last_seen": "2025-01-15T00:00:00Z",
        "tenant_count": 1,
        "mitre_techniques": ["T1530", "T1190"],
        "sector_relevance": ["Healthcare"],
        "remediation_hint": "Enforce FHIR patient context binding; validate OAuth2 scopes against patient identity on every request; implement SMART on FHIR authorization.",
    },
    {
        # SECTOR-SPECIFIC: BEC wire fraud targeting finance
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "bec-wire-fraud-finance")),
        "pattern_type": "FINANCIAL_FRAUD",
        "description": "Business Email Compromise campaign using AI-generated executive voice cloning to authorise fraudulent wire transfers. Attackers target finance departments with urgent requests from spoofed executive email accounts, reinforced with synthetic voice calls.",
        "entities_generic": ["executive email", "wire transfer system", "voice authentication"],
        "source_type": "CYBER_THREAT",
        "priority": "P1",
        "risk_score": 0.92,
        "occurrence_count": 1,
        "first_seen": "2024-12-01T00:00:00Z",
        "last_seen": "2025-01-20T00:00:00Z",
        "tenant_count": 1,
        "mitre_techniques": ["T1566.001", "T1534"],
        "sector_relevance": ["Financial Services"],
        "remediation_hint": "Require dual-person authorisation for wire transfers above threshold; implement voice-verification callback protocol; train staff on AI voice cloning recognition.",
    },
    {
        # SECTOR-SPECIFIC: regulatory fine for inadequate security controls
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "regulatory-fine-security-controls")),
        "pattern_type": "REGULATORY",
        "description": "Regulatory enforcement action resulting in significant financial penalty due to inadequate technical security controls. Regulator identified failure to implement appropriate encryption, access management, and audit logging as required by applicable data protection regulation.",
        "entities_generic": ["regulatory body", "security audit", "compliance program"],
        "source_type": "NEWS",
        "priority": "P2",
        "risk_score": 0.78,
        "occurrence_count": 2,
        "first_seen": "2024-08-01T00:00:00Z",
        "last_seen": "2024-11-30T00:00:00Z",
        "tenant_count": 2,
        "mitre_techniques": [],
        "sector_relevance": ["Technology", "Healthcare", "Financial Services", "Retail"],
        "remediation_hint": "Maintain documented security risk analysis; conduct annual penetration testing; implement continuous compliance monitoring; ensure audit log retention meets regulatory minimums.",
    },
]


async def seed_patterns() -> None:
    """Upsert all demo patterns into sentinel_shared_patterns."""
    from sentinel.config import get_settings
    from sentinel.db.qdrant_client import _get_client, ensure_collection
    from sentinel.llm import client as llm

    settings = get_settings()
    coll = settings.QDRANT_SHARED_COLLECTION

    print(f"[seed_shared_patterns] Using collection: {coll}")

    # Ensure collection exists
    await ensure_collection(collection_name=coll)

    client = _get_client()

    from qdrant_client import models as qmodels

    seeded = 0
    for pattern in DEMO_PATTERNS:
        # Build embedding text from description + entities + techniques
        embed_text = (
            f"{pattern['pattern_type']} {pattern['description']} "
            f"{' '.join(pattern['entities_generic'])} "
            f"{' '.join(pattern['mitre_techniques'])}"
        )
        vector = await llm.embed(embed_text)

        payload = {k: v for k, v in pattern.items() if k != "id"}
        payload["seeded"] = True
        payload["seeded_at"] = datetime.now(timezone.utc).isoformat()

        await client.upsert(
            collection_name=coll,
            points=[
                qmodels.PointStruct(
                    id=pattern["id"],
                    vector=vector,
                    payload=payload,
                )
            ],
        )
        seeded += 1
        print(f"  ✓ [{pattern['pattern_type']}] {pattern['description'][:60]}...")

    print(f"\n[seed_shared_patterns] Done. {seeded} patterns seeded into '{coll}'.")


if __name__ == "__main__":
    asyncio.run(seed_patterns())
