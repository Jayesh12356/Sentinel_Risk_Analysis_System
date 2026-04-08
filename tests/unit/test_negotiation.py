"""Unit tests for Level 9: Negotiation models and store.

Tests:
  1. NegotiationStatus enum values
  2. AlternativeSupplier creation
  3. OutreachEmail creation and reply
  4. NegotiationSession creation with all fields
  5. NegotiationSession serialisation (to_payload / from_payload)
  6. NegotiationSession embed_text
  7. NegotiationSession status transitions
  8. Demo data files are valid JSON
  9. Store in-memory save and retrieve
  10. Store in-memory update
  11. Store in-memory get_sessions with active_only filter
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import pytest

from sentinel.models.negotiation import (
    AlternativeSupplier,
    NegotiationSession,
    NegotiationStatus,
    OutreachEmail,
)


# ── Model Tests ──────────────────────────────────────────────────────────


def test_negotiation_status_values():
    """All 7 status values exist."""
    assert len(NegotiationStatus) == 7
    assert NegotiationStatus.SEARCHING == "SEARCHING"
    assert NegotiationStatus.DRAFTING == "DRAFTING"
    assert NegotiationStatus.AWAITING_REPLY == "AWAITING_REPLY"
    assert NegotiationStatus.SUMMARISING == "SUMMARISING"
    assert NegotiationStatus.COMPLETE == "COMPLETE"
    assert NegotiationStatus.FAILED == "FAILED"
    assert NegotiationStatus.DEMO == "DEMO"


def test_alternative_supplier_creation():
    """AlternativeSupplier model valid creation."""
    supplier = AlternativeSupplier(
        name="TestCorp",
        website="https://testcorp.com",
        description="A test supplier",
        relevance_score=0.85,
        search_source="serpapi",
    )
    assert supplier.name == "TestCorp"
    assert supplier.relevance_score == 0.85


def test_outreach_email_creation():
    """OutreachEmail model with reply."""
    supplier = AlternativeSupplier(name="TestCorp")
    email = OutreachEmail(
        supplier=supplier,
        subject="Partnership Inquiry",
        body="Dear TestCorp, ...",
        sent_at=datetime(2025, 3, 26, 10, 0, 0),
        reply_received=True,
        reply_body="Thank you for reaching out...",
        reply_at=datetime(2025, 3, 26, 14, 0, 0),
    )
    assert email.reply_received is True
    assert email.supplier.name == "TestCorp"


def test_negotiation_session_creation():
    """NegotiationSession full creation with nested models."""
    alt = AlternativeSupplier(name="CloudScale", relevance_score=0.92, search_source="demo")
    email = OutreachEmail(supplier=alt, subject="Inquiry", body="Hello...")
    session = NegotiationSession(
        tenant_id="techcorp",
        signal_id="sig-123",
        action_id="act-456",
        original_supplier="OldVendor",
        risk_reason="Bankruptcy filing",
        alternatives_found=[alt],
        outreach_emails=[email],
        status=NegotiationStatus.DRAFTING,
    )
    assert session.tenant_id == "techcorp"
    assert session.original_supplier == "OldVendor"
    assert len(session.alternatives_found) == 1
    assert session.status == NegotiationStatus.DRAFTING


def test_negotiation_session_serialisation():
    """to_payload → from_payload roundtrip."""
    alt = AlternativeSupplier(
        name="NovaTech", website="https://novatech.com",
        relevance_score=0.88, search_source="duckduckgo",
    )
    email = OutreachEmail(
        supplier=alt, subject="Re: Inquiry", body="Body text",
        sent_at=datetime(2025, 3, 26, 10, 0, 0),
    )
    session = NegotiationSession(
        tenant_id="default",
        original_supplier="OldCo",
        risk_reason="Supply chain disruption",
        alternatives_found=[alt],
        outreach_emails=[email],
        recommendation="NovaTech",
        recommendation_reasoning="Best pricing and SLA",
        status=NegotiationStatus.COMPLETE,
        completed_at=datetime(2025, 3, 27, 10, 0, 0),
    )
    payload = session.to_payload()
    assert isinstance(payload, dict)
    assert payload["status"] == "COMPLETE"
    assert payload["original_supplier"] == "OldCo"

    restored = NegotiationSession.from_payload(payload)
    assert restored.id == session.id
    assert restored.status == NegotiationStatus.COMPLETE
    assert restored.recommendation == "NovaTech"
    assert len(restored.alternatives_found) == 1
    assert restored.alternatives_found[0].name == "NovaTech"
    assert len(restored.outreach_emails) == 1


def test_negotiation_session_embed_text():
    """embed_text produces meaningful text for vector search."""
    alt = AlternativeSupplier(name="CloudScale", relevance_score=0.9)
    session = NegotiationSession(
        original_supplier="OldVendor",
        risk_reason="Bankruptcy",
        alternatives_found=[alt],
        recommendation="CloudScale",
        status=NegotiationStatus.COMPLETE,
    )
    text = session.embed_text()
    assert "OldVendor" in text
    assert "Bankruptcy" in text
    assert "CloudScale" in text
    assert "COMPLETE" in text


def test_negotiation_session_status_transitions():
    """Status can be changed through the workflow."""
    session = NegotiationSession(
        original_supplier="TestCo",
        status=NegotiationStatus.SEARCHING,
    )
    assert session.status == NegotiationStatus.SEARCHING
    session.status = NegotiationStatus.DRAFTING
    assert session.status == NegotiationStatus.DRAFTING
    session.status = NegotiationStatus.AWAITING_REPLY
    assert session.status == NegotiationStatus.AWAITING_REPLY
    session.status = NegotiationStatus.COMPLETE
    assert session.status == NegotiationStatus.COMPLETE


# ── Demo Data Tests ──────────────────────────────────────────────────────


def test_demo_alternatives_json_valid():
    """data/demo_alternatives.json is valid JSON with 5 suppliers."""
    path = os.path.join("data", "demo_alternatives.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == 5
    for item in data:
        assert "name" in item
        assert "relevance_score" in item
        # Verify we can create AlternativeSupplier from it
        supplier = AlternativeSupplier(**item)
        assert supplier.name


def test_demo_replies_json_valid():
    """data/demo_replies.json is valid JSON with 3 replies."""
    path = os.path.join("data", "demo_replies.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == 3
    for item in data:
        assert "supplier_name" in item
        assert "subject" in item
        assert "body" in item


# ── Store Tests (in-memory fallback) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_store_save_and_get():
    """Save and retrieve a NegotiationSession from in-memory store."""
    from sentinel.negotiation.store import _sessions, save_session, get_session

    _sessions.clear()
    session = NegotiationSession(
        tenant_id="default",
        original_supplier="TestVendor",
        status=NegotiationStatus.SEARCHING,
    )
    saved = await save_session(session)
    assert saved.id == session.id

    # Retrieve from in-memory
    retrieved = await get_session(session.id)
    assert retrieved is not None
    assert retrieved.original_supplier == "TestVendor"
    _sessions.clear()


@pytest.mark.asyncio
async def test_store_update_session():
    """Update a session changes status correctly."""
    from sentinel.negotiation.store import _sessions, save_session, update_session

    _sessions.clear()
    session = NegotiationSession(
        tenant_id="default",
        original_supplier="UpdateTest",
        status=NegotiationStatus.SEARCHING,
    )
    await save_session(session)

    updated = await update_session(session.id, {"status": NegotiationStatus.DRAFTING})
    assert updated is not None
    assert updated.status == NegotiationStatus.DRAFTING
    _sessions.clear()


@pytest.mark.asyncio
async def test_store_get_sessions_active_only():
    """get_sessions with active_only filters completed sessions."""
    from sentinel.negotiation.store import _sessions, save_session, get_sessions

    _sessions.clear()
    s1 = NegotiationSession(tenant_id="default", original_supplier="A", status=NegotiationStatus.SEARCHING)
    s2 = NegotiationSession(tenant_id="default", original_supplier="B", status=NegotiationStatus.COMPLETE)
    s3 = NegotiationSession(tenant_id="default", original_supplier="C", status=NegotiationStatus.DRAFTING)
    await save_session(s1)
    await save_session(s2)
    await save_session(s3)

    all_sessions = await get_sessions("default", active_only=False)
    assert len(all_sessions) == 3

    active_sessions = await get_sessions("default", active_only=True)
    assert len(active_sessions) == 2
    assert all(s.status not in (NegotiationStatus.COMPLETE, NegotiationStatus.FAILED) for s in active_sessions)
    _sessions.clear()
