"""Tenant Pydantic model — Level 6 Multi-Company Federated Intelligence.

A Tenant represents one company registered in SENTINEL.
Each tenant has fully isolated Qdrant collections and one company_profile.json.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class Tenant(BaseModel):
    """A registered company/organisation within SENTINEL."""

    id: str = Field(..., description="Tenant slug, e.g. 'techcorp', 'retailco'")
    name: str = Field(..., description="Display name of the company")
    industry: str = Field(..., description="Industry sector, e.g. 'Technology / SaaS'")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=False, description="Whether this tenant is currently active")
    profile_path: str = Field(
        default="",
        description="Relative path to company_profile.json, e.g. data/tenants/{id}/company_profile.json",
    )

    @property
    def signals_collection(self) -> str:
        """Qdrant collection name for this tenant's signals."""
        return f"{self.id}_signals"

    @property
    def memory_collection(self) -> str:
        """Qdrant collection name for this tenant's memory."""
        return f"{self.id}_memory"

    @property
    def feedback_collection(self) -> str:
        """Qdrant collection name for this tenant's feedback."""
        return f"{self.id}_feedback"

    def to_registry_dict(self) -> dict:
        """Serialise to a registry.json-compatible dict."""
        return {
            "id": self.id,
            "name": self.name,
            "industry": self.industry,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
            "profile_path": self.profile_path,
        }

    @classmethod
    def from_registry_dict(cls, data: dict) -> Tenant:
        """Reconstruct from a registry.json dict."""
        parsed = dict(data)
        if "created_at" in parsed and isinstance(parsed["created_at"], str):
            parsed["created_at"] = datetime.fromisoformat(parsed["created_at"])
        return cls(**parsed)
