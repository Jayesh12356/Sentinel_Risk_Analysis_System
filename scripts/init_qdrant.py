"""Initialize the Qdrant collections for SENTINEL.

Usage:
    python scripts/init_qdrant.py

Creates all four Qdrant collections if they don't already exist.
Requires Qdrant to be running (docker-compose up -d).
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from sentinel.config import get_settings
from sentinel.db.qdrant_client import ensure_collection


async def main() -> None:
    settings = get_settings()
    print(f"Connecting to Qdrant at {settings.QDRANT_URL} ...")

    # Signals collection (Level 1)
    await ensure_collection(settings.QDRANT_COLLECTION)
    print(f"[OK] Collection '{settings.QDRANT_COLLECTION}' is ready.")

    # Memory collection (Level 3)
    await ensure_collection(settings.QDRANT_MEMORY_COLLECTION)
    print(f"[OK] Collection '{settings.QDRANT_MEMORY_COLLECTION}' is ready.")

    # Prompts collection (Level 4)
    await ensure_collection(settings.QDRANT_PROMPTS_COLLECTION)
    print(f"[OK] Collection '{settings.QDRANT_PROMPTS_COLLECTION}' is ready.")

    # Feedback collection (Level 5)
    await ensure_collection(settings.QDRANT_FEEDBACK_COLLECTION)
    print(f"[OK] Collection '{settings.QDRANT_FEEDBACK_COLLECTION}' is ready.")

    # Shared patterns collection (Level 6 — cross-tenant anonymised patterns)
    await ensure_collection(settings.QDRANT_SHARED_COLLECTION)
    print(f"[OK] Collection '{settings.QDRANT_SHARED_COLLECTION}' is ready.")

    # Forecast collections (Level 7 — per-tenant predictive intelligence)
    DEMO_TENANTS = ["default", "techcorp", "retailco", "financeinc", "healthco"]
    for tenant_id in DEMO_TENANTS:
        forecast_col = f"{tenant_id}_forecasts"
        await ensure_collection(forecast_col)
        print(f"[OK] Collection '{forecast_col}' is ready.")

    # Action collections (Level 8 — per-tenant autonomous actions)
    for tenant_id in DEMO_TENANTS:
        action_col = f"{tenant_id}_actions"
        await ensure_collection(action_col)
        print(f"[OK] Collection '{action_col}' is ready.")

    # Negotiation collections (Level 9 — per-tenant negotiation sessions)
    for tenant_id in DEMO_TENANTS:
        negotiation_col = f"{tenant_id}_negotiations"
        await ensure_collection(negotiation_col)
        print(f"[OK] Collection '{negotiation_col}' is ready.")

    # Meta + Governance collection (Level 10 — shared, not per-tenant)
    await ensure_collection("sentinel_meta")
    print("[OK] Collection 'sentinel_meta' is ready.")

    print("\nAll collections initialized successfully.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
