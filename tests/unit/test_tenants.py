"""Unit tests for Level 6 Tenant infrastructure.

Tests:
  - Tenant model: field defaults, collection name properties, serialization
  - TenantManager: create, list, get, activate, delete
  - get_active_tenant: returns default when ACTIVE_TENANT not in registry
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sentinel.models.tenant import Tenant


# ---------------------------------------------------------------------------
# Tenant model unit tests
# ---------------------------------------------------------------------------


class TestTenantModel:
    def test_tenant_fields(self):
        tenant = Tenant(id="techcorp", name="TechCorp", industry="Technology / SaaS")
        assert tenant.id == "techcorp"
        assert tenant.name == "TechCorp"
        assert tenant.industry == "Technology / SaaS"
        assert isinstance(tenant.created_at, datetime)
        assert tenant.is_active is False
        assert tenant.profile_path == ""

    def test_collection_name_properties(self):
        tenant = Tenant(id="retailco", name="RetailCo", industry="Retail")
        assert tenant.signals_collection == "retailco_signals"
        assert tenant.memory_collection == "retailco_memory"
        assert tenant.feedback_collection == "retailco_feedback"

    def test_to_registry_dict_roundtrip(self):
        tenant = Tenant(
            id="financeinc",
            name="FinanceInc",
            industry="Financial Services",
            is_active=True,
            profile_path="data/tenants/financeinc/company_profile.json",
        )
        d = tenant.to_registry_dict()
        assert d["id"] == "financeinc"
        assert d["is_active"] is True
        assert isinstance(d["created_at"], str)

        reconstructed = Tenant.from_registry_dict(d)
        assert reconstructed.id == tenant.id
        assert reconstructed.name == tenant.name
        assert reconstructed.is_active is True
        assert isinstance(reconstructed.created_at, datetime)

    def test_collection_names_are_tenant_scoped(self):
        t1 = Tenant(id="alpha", name="Alpha", industry="Tech")
        t2 = Tenant(id="beta", name="Beta", industry="Retail")
        # Collection names must be unique per tenant
        assert t1.signals_collection != t2.signals_collection
        assert t1.memory_collection != t2.memory_collection
        assert t1.feedback_collection != t2.feedback_collection


# ---------------------------------------------------------------------------
# TenantManager integration-style tests (using tmp dir, mocked Qdrant)
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_tenants_dir(tmp_path):
    """Provides a temporary tenants dir and patches settings to use it."""
    tenants_dir = tmp_path / "tenants"
    tenants_dir.mkdir()
    (tenants_dir / "registry.json").write_text("[]", encoding="utf-8")
    return tenants_dir


@pytest.fixture
def patch_settings(tmp_tenants_dir):
    """Patch get_settings() to return a mock with the tmp tenants dir."""
    mock_settings = MagicMock()
    mock_settings.TENANTS_DIR = str(tmp_tenants_dir)
    mock_settings.ACTIVE_TENANT = "default"
    with patch("sentinel.tenants.manager.get_settings", return_value=mock_settings):
        with patch("sentinel.tenants.manager.ensure_collection", new_callable=AsyncMock):
            yield mock_settings


class TestTenantManager:
    @pytest.mark.asyncio
    async def test_create_tenant(self, patch_settings, tmp_tenants_dir):
        from sentinel.tenants.manager import create_tenant

        tenant = await create_tenant("testco", "TestCo", "Technology")
        assert tenant.id == "testco"
        assert tenant.name == "TestCo"
        assert tenant.industry == "Technology"
        assert tenant.signals_collection == "testco_signals"

        # profile_path should be set
        assert "testco" in tenant.profile_path

        # company_profile.json should be created
        profile_path = Path(tmp_tenants_dir) / "testco" / "company_profile.json"
        assert profile_path.exists()
        data = json.loads(profile_path.read_text())
        assert data["name"] == "TestCo"

    @pytest.mark.asyncio
    async def test_create_duplicate_tenant_raises(self, patch_settings):
        from sentinel.tenants.manager import create_tenant

        await create_tenant("dupco", "DupCo", "Finance")
        with pytest.raises(ValueError, match="already exists"):
            await create_tenant("dupco", "DupCo", "Finance")

    @pytest.mark.asyncio
    async def test_list_tenants(self, patch_settings):
        from sentinel.tenants.manager import create_tenant, list_tenants

        await create_tenant("alpha", "Alpha Co", "Healthcare")
        await create_tenant("beta", "Beta Co", "Retail")

        tenants = await list_tenants()
        assert len(tenants) == 2
        ids = {t.id for t in tenants}
        assert "alpha" in ids
        assert "beta" in ids

    @pytest.mark.asyncio
    async def test_get_tenant_returns_none_for_unknown(self, patch_settings):
        from sentinel.tenants.manager import get_tenant

        result = await get_tenant("doesnotexist")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_active_tenant_returns_default(self, patch_settings):
        """When ACTIVE_TENANT='default' is not in registry, falls back to first tenant."""
        from sentinel.tenants.manager import create_tenant, get_active_tenant

        await create_tenant("myco", "MyCo", "Tech")
        active = await get_active_tenant()
        assert active.id == "myco"  # First available tenant

    @pytest.mark.asyncio
    async def test_activate_tenant(self, patch_settings):
        from sentinel.tenants.manager import activate_tenant, create_tenant

        await create_tenant("co1", "Co One", "Tech")
        await create_tenant("co2", "Co Two", "Retail")

        result = await activate_tenant("co2")
        assert result.id == "co2"

    @pytest.mark.asyncio
    async def test_delete_tenant(self, patch_settings):
        from sentinel.tenants.manager import create_tenant, delete_tenant, list_tenants

        await create_tenant("delme", "Del Me", "Finance")
        tenants_before = await list_tenants()
        assert len(tenants_before) == 1

        await delete_tenant("delme")
        tenants_after = await list_tenants()
        assert len(tenants_after) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, patch_settings):
        from sentinel.tenants.manager import delete_tenant

        with pytest.raises(ValueError, match="not found"):
            await delete_tenant("ghost")
