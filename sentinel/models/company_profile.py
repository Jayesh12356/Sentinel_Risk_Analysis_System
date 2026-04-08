"""CompanyProfile — Pydantic model for company DNA.

Defines who the company is, what tech they run, their suppliers,
regions, regulatory scope, and custom watch terms.  Used by
RouterAgent and RiskAssessor for personalised risk scoring.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field


class CompanyProfile(BaseModel):
    """Company identity & exposure surface for personalised risk scoring."""

    id: str = Field(default="default", description="Profile identifier")
    name: str = Field(default="", description="Company name")
    industry: str = Field(default="", description="Primary industry")
    regions: List[str] = Field(
        default_factory=list,
        description="Operating regions (e.g. EU, US, APAC)",
    )
    tech_stack: List[str] = Field(
        default_factory=list,
        description="Technologies in use (e.g. AWS, Apache, Kubernetes)",
    )
    suppliers: List[str] = Field(
        default_factory=list,
        description="Key suppliers / third-party dependencies",
    )
    competitors: List[str] = Field(
        default_factory=list,
        description="Known competitors",
    )
    regulatory_scope: List[str] = Field(
        default_factory=list,
        description="Applicable regulations (e.g. GDPR, SOC2, HIPAA)",
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Custom watch terms for signal matching",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last profile update timestamp",
    )
