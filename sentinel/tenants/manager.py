"""TenantManager — create, list, and switch SENTINEL tenants.

Tenants are stored in data/tenants/registry.json (flat file).
Each tenant gets its own Qdrant collections and company_profile.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

import structlog

from sentinel.config import get_settings
from sentinel.db.qdrant_client import ensure_collection
from sentinel.models.tenant import Tenant

logger = structlog.get_logger(__name__)

_VECTOR_SIZE = 3072  # gemini-embedding-001 output dimension


def _registry_path() -> Path:
    """Return Path to registry.json."""
    settings = get_settings()
    return Path(settings.TENANTS_DIR) / "registry.json"


def _load_registry() -> list[dict]:
    """Load the tenant registry from disk. Returns empty list if missing."""
    path = _registry_path()
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _save_registry(tenants: list[dict]) -> None:
    """Persist the tenant registry to disk."""
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tenants, f, indent=2)


def _default_company_profile(name: str, industry: str) -> dict:
    """Return a minimal default company profile dict."""
    return {
        "name": name,
        "industry": industry,
        "tech_stack": [],
        "regions": [],
        "regulatory_frameworks": [],
        "key_vendors": [],
        "business_units": [],
        "risk_appetite": "medium",
    }


async def create_tenant(
    tenant_id: str,
    name: str,
    industry: str,
) -> Tenant:
    """Create a new tenant with isolated Qdrant collections and data directory.

    Args:
        tenant_id: Unique slug (e.g. 'techcorp').  Must be alphanumeric + hyphens.
        name:      Display name.
        industry:  Industry sector string.

    Returns:
        The created Tenant.

    Raises:
        ValueError: If a tenant with this ID already exists.
    """
    settings = get_settings()
    registry = _load_registry()

    # Check for duplicates
    existing_ids = {t["id"] for t in registry}
    if tenant_id in existing_ids:
        raise ValueError(f"Tenant '{tenant_id}' already exists.")

    # Create data directory
    tenant_dir = Path(settings.TENANTS_DIR) / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)

    # Write default company_profile.json
    profile_path = tenant_dir / "company_profile.json"
    profile_dict = _default_company_profile(name, industry)
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile_dict, f, indent=2)

    # Build Tenant object
    relative_profile = str(Path(settings.TENANTS_DIR) / tenant_id / "company_profile.json")
    tenant = Tenant(
        id=tenant_id,
        name=name,
        industry=industry,
        is_active=False,
        profile_path=relative_profile,
    )

    # Create per-tenant Qdrant collections
    for collection_name in [
        tenant.signals_collection,
        tenant.memory_collection,
        tenant.feedback_collection,
    ]:
        await ensure_collection(collection_name, vector_size=_VECTOR_SIZE)
        logger.info("tenant.collection_created", tenant_id=tenant_id, collection=collection_name)

    # Persist to registry
    registry.append(tenant.to_registry_dict())
    _save_registry(registry)

    logger.info("tenant.created", tenant_id=tenant_id, name=name)
    return tenant


async def list_tenants() -> List[Tenant]:
    """Return all registered tenants from registry.json."""
    registry = _load_registry()
    return [Tenant.from_registry_dict(t) for t in registry]


async def get_tenant(tenant_id: str) -> Optional[Tenant]:
    """Return a single tenant by ID, or None if not found."""
    registry = _load_registry()
    for entry in registry:
        if entry["id"] == tenant_id:
            return Tenant.from_registry_dict(entry)
    return None


async def get_active_tenant() -> Tenant:
    """Return the currently active tenant based on ACTIVE_TENANT setting.

    Falls back to the first registered tenant, then creates a 'default' tenant
    if none exist.
    """
    settings = get_settings()
    active_id = settings.ACTIVE_TENANT

    tenant = await get_tenant(active_id)
    if tenant:
        return tenant

    # Fallback: first registered tenant
    all_tenants = await list_tenants()
    if all_tenants:
        logger.warning("tenant.active_not_found", active_id=active_id, fallback=all_tenants[0].id)
        return all_tenants[0]

    # Last resort: create default tenant on-the-fly
    logger.warning("tenant.no_tenants_found", creating="default")
    return await create_tenant("default", "Default Organization", "General")


async def activate_tenant(tenant_id: str) -> Tenant:
    """Mark a tenant as active in the registry (sets is_active=True, others False).

    Note: This updates registry.json only — ACTIVE_TENANT env var is separate.
    """
    registry = _load_registry()
    found = False
    for entry in registry:
        entry["is_active"] = entry["id"] == tenant_id
        if entry["id"] == tenant_id:
            found = True

    if not found:
        raise ValueError(f"Tenant '{tenant_id}' not found.")

    _save_registry(registry)
    tenant = await get_tenant(tenant_id)
    logger.info("tenant.activated", tenant_id=tenant_id)
    return tenant  # type: ignore[return-value]


async def delete_tenant(tenant_id: str) -> None:
    """Remove a tenant from the registry (Qdrant data is preserved).

    Does NOT delete Qdrant collections or data files.
    """
    registry = _load_registry()
    original_len = len(registry)
    registry = [t for t in registry if t["id"] != tenant_id]

    if len(registry) == original_len:
        raise ValueError(f"Tenant '{tenant_id}' not found.")

    _save_registry(registry)
    logger.info("tenant.deleted", tenant_id=tenant_id)
