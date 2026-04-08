"""Negotiation models — Level 9: SENTINEL Negotiates.

NegotiationSession, AlternativeSupplier, OutreachEmail.
Stored in Qdrant {tenant_id}_negotiations collection.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class NegotiationStatus(str, Enum):
    """Status of a negotiation session."""
    SEARCHING = "SEARCHING"
    DRAFTING = "DRAFTING"
    AWAITING_REPLY = "AWAITING_REPLY"
    SUMMARISING = "SUMMARISING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    DEMO = "DEMO"


class AlternativeSupplier(BaseModel):
    """A potential alternative supplier found via web search."""
    name: str = Field(..., description="Supplier company name")
    website: str = Field(default="", description="Supplier website URL")
    description: str = Field(default="", description="Brief description of offerings")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Match relevance 0-1")
    search_source: str = Field(default="", description="Where this result was found (serpapi/duckduckgo/demo)")


class OutreachEmail(BaseModel):
    """An outreach email drafted/sent to an alternative supplier."""
    supplier: AlternativeSupplier = Field(..., description="Target supplier")
    subject: str = Field(default="", description="Email subject line")
    body: str = Field(default="", description="Full email body text")
    sent_at: Optional[datetime] = Field(default=None, description="When email was sent")
    reply_received: bool = Field(default=False, description="Whether a reply was received")
    reply_body: Optional[str] = Field(default=None, description="Reply email body if received")
    reply_at: Optional[datetime] = Field(default=None, description="When reply was received")


class NegotiationSession(BaseModel):
    """A full negotiation session — from search to recommendation."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, description="Unique session ID")
    tenant_id: str = Field(default="default", description="Tenant this negotiation belongs to")
    signal_id: str = Field(default="", description="Originating signal ID")
    action_id: str = Field(default="", description="ActionEntry ID that triggered this")
    original_supplier: str = Field(default="", description="The at-risk supplier name")
    risk_reason: str = Field(default="", description="Why the supplier is at risk")
    alternatives_found: list[AlternativeSupplier] = Field(default_factory=list)
    outreach_emails: list[OutreachEmail] = Field(default_factory=list)
    recommendation: Optional[str] = Field(default=None, description="Recommended supplier name")
    recommendation_reasoning: Optional[str] = Field(default=None, description="Why this supplier is recommended")
    status: NegotiationStatus = Field(default=NegotiationStatus.SEARCHING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)

    def to_payload(self) -> dict[str, Any]:
        """Serialise for Qdrant storage / API response."""
        data = self.model_dump(mode="json")
        # Convert datetime to ISO string
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        # Convert enums
        data["status"] = self.status.value
        # Serialise nested models
        data["alternatives_found"] = [a.model_dump(mode="json") for a in self.alternatives_found]
        emails = []
        for e in self.outreach_emails:
            ed = e.model_dump(mode="json")
            ed["supplier"] = e.supplier.model_dump(mode="json")
            if e.sent_at:
                ed["sent_at"] = e.sent_at.isoformat()
            if e.reply_at:
                ed["reply_at"] = e.reply_at.isoformat()
            emails.append(ed)
        data["outreach_emails"] = emails
        return data

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> NegotiationSession:
        """Deserialise from Qdrant storage / API request."""
        d = dict(data)
        if isinstance(d.get("status"), str):
            d["status"] = NegotiationStatus(d["status"])
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])
        if isinstance(d.get("completed_at"), str):
            d["completed_at"] = datetime.fromisoformat(d["completed_at"])
        # Parse nested
        if "alternatives_found" in d:
            d["alternatives_found"] = [
                AlternativeSupplier(**a) if isinstance(a, dict) else a
                for a in d["alternatives_found"]
            ]
        if "outreach_emails" in d:
            emails = []
            for e in d["outreach_emails"]:
                if isinstance(e, dict):
                    if isinstance(e.get("supplier"), dict):
                        e["supplier"] = AlternativeSupplier(**e["supplier"])
                    if isinstance(e.get("sent_at"), str):
                        e["sent_at"] = datetime.fromisoformat(e["sent_at"])
                    if isinstance(e.get("reply_at"), str):
                        e["reply_at"] = datetime.fromisoformat(e["reply_at"])
                    emails.append(OutreachEmail(**e))
                else:
                    emails.append(e)
            d["outreach_emails"] = emails
        return cls(**d)

    def embed_text(self) -> str:
        """Generate text for embedding in Qdrant vector search."""
        parts = [
            f"Negotiation for {self.original_supplier}",
            f"Risk: {self.risk_reason}",
            f"Status: {self.status.value}",
        ]
        if self.alternatives_found:
            alt_names = ", ".join(a.name for a in self.alternatives_found[:5])
            parts.append(f"Alternatives: {alt_names}")
        if self.recommendation:
            parts.append(f"Recommendation: {self.recommendation}")
        return " | ".join(parts)
