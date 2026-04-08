"""Seed the sentinel_prompts Qdrant collection with v1 of all agent prompts.

Usage:
    python scripts/init_prompts.py

Reads the current hardcoded prompt templates from each agent file
and stores them as version 1 in the sentinel_prompts collection.
Requires Qdrant to be running (docker-compose up -d).
Run AFTER init_qdrant.py.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from sentinel.config import get_settings
from sentinel.db.qdrant_client import ensure_collection
from sentinel.optimiser.prompt_store import get_active_prompt, save_prompt_version


# Map of agent_name -> (module_path, variable_name)
AGENT_PROMPTS: dict[str, tuple[str, str]] = {
    "EntityExtractor": (
        "sentinel.agents.layer1_processing.entity_extractor",
        "NER_PROMPT_TEMPLATE",
    ),
    "SignalClassifier": (
        "sentinel.agents.layer1_processing.signal_classifier",
        "CLASSIFY_PROMPT_TEMPLATE",
    ),
    "RouterAgent": (
        "sentinel.agents.layer1_processing.router",
        "_SYSTEM_PROMPT",  # class attribute - handled specially
    ),
    "RiskAssessor": (
        "sentinel.agents.layer2_reasoning.risk_assessor",
        "RISK_PROMPT_TEMPLATE",
    ),
    "CausalChainBuilder": (
        "sentinel.agents.layer2_reasoning.causal_chain",
        "CAUSAL_PROMPT_TEMPLATE",
    ),
    "RedTeamAgent": (
        "sentinel.agents.layer3_deliberation.red_team",
        "RED_TEAM_PROMPT_TEMPLATE",
    ),
    "BlueTeamAgent": (
        "sentinel.agents.layer3_deliberation.blue_team",
        "BLUE_TEAM_PROMPT_TEMPLATE",
    ),
    "ArbiterAgent": (
        "sentinel.agents.layer3_deliberation.arbiter",
        "ARBITER_PROMPT_TEMPLATE",
    ),
    "BriefWriter": (
        "sentinel.agents.layer4_output.brief_writer",
        "BRIEF_PROMPT_TEMPLATE",
    ),
}


def _load_prompt(module_path: str, var_name: str) -> str:
    """Import and extract a prompt template from an agent module."""
    import importlib

    mod = importlib.import_module(module_path)

    # For RouterAgent, the prompt is a class attribute
    if var_name == "_SYSTEM_PROMPT":
        cls = getattr(mod, "RouterAgent", None)
        if cls:
            return getattr(cls, "_SYSTEM_PROMPT", "")
        return ""

    return getattr(mod, var_name, "")


async def main() -> None:
    settings = get_settings()
    collection = settings.QDRANT_PROMPTS_COLLECTION
    print(f"Connecting to Qdrant at {settings.QDRANT_URL} ...")

    # Ensure collection exists
    await ensure_collection(collection)
    print(f"Collection '{collection}' is ready.")

    # Check if already seeded
    from sentinel.db.qdrant_client import _get_client

    client = _get_client()
    result = await client.scroll(
        collection_name=collection,
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    points, _ = result
    if points:
        print(f"Collection already has {len(points)}+ entries. Skipping seed.")
        print("To re-seed, delete the collection first: DELETE /memory")
        return

    # Seed v1 of each agent prompt
    seeded = 0
    for agent_name, (module_path, var_name) in AGENT_PROMPTS.items():
        try:
            prompt_text = _load_prompt(module_path, var_name)
            if not prompt_text:
                print(f"  [WARN] Empty prompt for {agent_name}, skipping.")
                continue

            pv = await save_prompt_version(
                agent_name=agent_name,
                prompt_text=prompt_text,
                quality_score=None,  # initial seed, no score
            )
            print(f"  [OK] {agent_name} v{pv.version} seeded ({len(prompt_text)} chars)")
            seeded += 1
        except Exception as e:
            print(f"  [FAIL] {agent_name} FAILED: {e}")

    print(f"\nSeeded {seeded}/{len(AGENT_PROMPTS)} agent prompts into '{collection}'.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
