"""TenantContext — per-run tenant isolation context for the pipeline.

TenantContext is injected into PipelineState at pipeline start.
All agents read Qdrant collection names from TenantContext rather
than from global settings, enabling complete data isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from sentinel.models.company_profile import CompanyProfile


class TenantContext(BaseModel):
    """Tenant-scoped collection names injected into the pipeline.

    Passed as ``state["tenant_context"]`` to every agent.
    Agents must use these collection names for all Qdrant reads/writes.
    """

    tenant_id: str = Field(..., description="Tenant slug, e.g. 'techcorp'")
    tenant_name: str = Field(default="", description="Display name of the tenant")
    signals_collection: str = Field(..., description="Qdrant collection for signals")
    memory_collection: str = Field(..., description="Qdrant collection for memory")
    feedback_collection: str = Field(..., description="Qdrant collection for feedback")

    # Loaded company profile (can be None for lightweight runs)
    company_profile: dict[str, Any] = Field(
        default_factory=dict,
        description="Company profile dict loaded from data/tenants/{tenant_id}/company_profile.json",
    )

    @classmethod
    def from_tenant_id(cls, tenant_id: str) -> "TenantContext":
        """Build a TenantContext from a tenant_id slug (without loading profile).

        For lightweight construction — profile can be loaded separately.
        """
        return cls(
            tenant_id=tenant_id,
            signals_collection=f"{tenant_id}_signals",
            memory_collection=f"{tenant_id}_memory",
            feedback_collection=f"{tenant_id}_feedback",
        )

    @classmethod
    def default(cls) -> "TenantContext":
        """Return TenantContext for the legacy 'default' tenant (Level 1–5 compat)."""
        return cls(
            tenant_id="default",
            tenant_name="Default",
            signals_collection="sentinel_signals",
            memory_collection="sentinel_memory",
            feedback_collection="sentinel_feedback",
        )
