"""Seed the 4 demo tenants for SENTINEL Level 6.

Usage:
    python scripts/init_tenants.py

Creates:
  - data/tenants/registry.json with 4 tenant entries
  - data/tenants/{id}/company_profile.json for each
  - Qdrant collections: {id}_signals, {id}_memory, {id}_feedback for each tenant
  - sentinel_shared_patterns collection

Run after docker-compose up -d and init_qdrant.py.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from sentinel.config import get_settings
from sentinel.db.qdrant_client import ensure_collection
from sentinel.tenants.manager import create_tenant, get_tenant


# Full company profile data for each demo tenant
_TENANT_PROFILES: dict[str, dict] = {
    "techcorp": {
        "name": "TechCorp",
        "industry": "Technology / SaaS",
        "profile": {
            "name": "TechCorp",
            "industry": "Technology / SaaS",
            "tech_stack": ["AWS", "Apache", "Kubernetes", "PostgreSQL", "Kafka"],
            "regions": ["US", "EU"],
            "regulatory_frameworks": ["SOC2", "GDPR"],
            "key_vendors": ["AWS", "Datadog", "Okta", "Cloudflare"],
            "business_units": ["Engineering", "Product", "Sales", "Finance"],
            "risk_appetite": "medium",
            "employee_count": 850,
            "annual_revenue": "$120M",
        },
    },
    "retailco": {
        "name": "RetailCo",
        "industry": "Retail / E-commerce",
        "profile": {
            "name": "RetailCo",
            "industry": "Retail / E-commerce",
            "tech_stack": ["Azure", "Shopify", "Stripe", "Redis", "Elasticsearch"],
            "regions": ["US", "UK"],
            "regulatory_frameworks": ["PCI-DSS", "GDPR"],
            "key_vendors": ["Shopify", "Stripe", "Azure", "Twilio"],
            "business_units": ["Retail Operations", "E-commerce", "Logistics", "Marketing"],
            "risk_appetite": "low",
            "employee_count": 1200,
            "annual_revenue": "$340M",
        },
    },
    "financeinc": {
        "name": "FinanceInc",
        "industry": "Financial Services",
        "profile": {
            "name": "FinanceInc",
            "industry": "Financial Services",
            "tech_stack": ["AWS", "Oracle", "Kafka", "Elasticsearch", "Hadoop"],
            "regions": ["US", "EU", "APAC"],
            "regulatory_frameworks": ["SOC2", "PCI-DSS", "FINRA"],
            "key_vendors": ["Oracle", "Bloomberg", "AWS", "Palo Alto Networks"],
            "business_units": ["Trading", "Risk Management", "Compliance", "Operations"],
            "risk_appetite": "very_low",
            "employee_count": 2400,
            "annual_revenue": "$1.8B",
        },
    },
    "healthco": {
        "name": "HealthCo",
        "industry": "Healthcare",
        "profile": {
            "name": "HealthCo",
            "industry": "Healthcare",
            "tech_stack": ["Azure", "Epic", "HL7", "PostgreSQL", "FHIR API"],
            "regions": ["US"],
            "regulatory_frameworks": ["HIPAA", "SOC2"],
            "key_vendors": ["Epic", "Azure", "Microsoft", "Cisco"],
            "business_units": ["Clinical Operations", "IT", "Compliance", "Research"],
            "risk_appetite": "very_low",
            "employee_count": 5000,
            "annual_revenue": "$780M",
        },
    },
}


async def main() -> None:
    settings = get_settings()
    print(f"Initialising 4 demo tenants in {settings.TENANTS_DIR} ...")

    created_count = 0
    for tenant_id, meta in _TENANT_PROFILES.items():
        existing = await get_tenant(tenant_id)
        if existing:
            print(f"  [SKIP] Tenant '{tenant_id}' already exists.")
            continue

        try:
            tenant = await create_tenant(
                tenant_id=tenant_id,
                name=meta["name"],
                industry=meta["industry"],
            )

            # Overwrite the default profile with full demo data
            profile_path = Path(tenant.profile_path)
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(meta["profile"], f, indent=2)

            print(f"  [OK] {tenant.name:<12} ({tenant.industry})")
            print(f"         Collections: {tenant.signals_collection}, {tenant.memory_collection}, {tenant.feedback_collection}")
            created_count += 1

        except Exception as e:
            print(f"  [FAIL] {tenant_id}: {e}")

    # Also ensure the shared patterns collection exists
    shared_collection = settings.QDRANT_SHARED_COLLECTION
    await ensure_collection(shared_collection, vector_size=3072)
    print(f"  [OK] Shared collection '{shared_collection}' ready.")

    print(f"\nDone: {created_count} new tenants created, {len(_TENANT_PROFILES) - created_count} already existed.")
    print(f"Registry: {settings.TENANTS_DIR}/registry.json")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
