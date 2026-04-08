"""Tests for CompanyProfile model and profile manager."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from sentinel.models.company_profile import CompanyProfile


class TestCompanyProfileModel:
    """Tests for the CompanyProfile Pydantic model."""

    def test_default_profile(self):
        """Default profile has sensible empty values."""
        p = CompanyProfile()
        assert p.id == "default"
        assert p.name == ""
        assert p.industry == ""
        assert p.regions == []
        assert p.tech_stack == []
        assert p.suppliers == []
        assert p.competitors == []
        assert p.regulatory_scope == []
        assert p.keywords == []
        assert p.updated_at is not None

    def test_full_profile(self):
        """Profile with all fields set."""
        p = CompanyProfile(
            id="test",
            name="Acme Corp",
            industry="Technology",
            regions=["EU", "US"],
            tech_stack=["AWS", "Apache"],
            suppliers=["TSMC"],
            competitors=["CrowdStrike"],
            regulatory_scope=["GDPR", "SOC2"],
            keywords=["zero-day", "ransomware"],
        )
        assert p.name == "Acme Corp"
        assert "AWS" in p.tech_stack
        assert len(p.regions) == 2
        assert "GDPR" in p.regulatory_scope

    def test_json_roundtrip(self):
        """Profile can serialize and deserialize cleanly."""
        p = CompanyProfile(
            name="Meridian Technologies",
            industry="Technology",
            tech_stack=["AWS", "Apache", "Kubernetes"],
        )
        json_str = p.model_dump_json()
        loaded = CompanyProfile.model_validate_json(json_str)
        assert loaded.name == p.name
        assert loaded.tech_stack == p.tech_stack


class TestProfileManager:
    """Tests for the profile manager load/save/cache."""

    def test_load_from_file(self, tmp_path: Path):
        """Profile loads from a JSON file."""
        profile_data = {
            "id": "default",
            "name": "Test Corp",
            "industry": "Finance",
            "regions": ["US"],
            "tech_stack": ["PostgreSQL"],
            "suppliers": [],
            "competitors": [],
            "regulatory_scope": ["SOC2"],
            "keywords": ["fraud"],
        }
        file = tmp_path / "profile.json"
        file.write_text(json.dumps(profile_data), encoding="utf-8")

        # Patch settings to point to our temp file
        from unittest.mock import patch
        with patch("sentinel.profile.manager._profile_path", return_value=file):
            from sentinel.profile.manager import load_profile
            p = load_profile()
            assert p.name == "Test Corp"
            assert p.industry == "Finance"

    def test_load_missing_file(self, tmp_path: Path):
        """Missing file returns default empty profile."""
        missing = tmp_path / "nonexistent.json"

        from unittest.mock import patch
        with patch("sentinel.profile.manager._profile_path", return_value=missing):
            from sentinel.profile.manager import load_profile
            p = load_profile()
            assert p.id == "default"
            assert p.name == ""

    def test_save_and_reload(self, tmp_path: Path):
        """Save writes to disk and can be reloaded."""
        file = tmp_path / "profile.json"

        from unittest.mock import patch
        with patch("sentinel.profile.manager._profile_path", return_value=file):
            from sentinel.profile.manager import save_profile, load_profile

            original = CompanyProfile(
                name="Saved Corp",
                industry="Healthcare",
                tech_stack=["Docker"],
            )
            save_profile(original)

            assert file.exists()

            loaded = load_profile()
            assert loaded.name == "Saved Corp"
            assert loaded.industry == "Healthcare"
            assert "Docker" in loaded.tech_stack

    def test_demo_profile_loads(self):
        """The demo profile JSON file is valid and loads correctly."""
        demo_path = Path("data/company_profile.json")
        if not demo_path.exists():
            pytest.skip("Demo profile not found")

        raw = demo_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        p = CompanyProfile(**data)
        assert p.name == "Meridian Technologies"
        assert "AWS" in p.tech_stack
        assert "Apache" in p.tech_stack
        assert "EU" in p.regions
        assert "GDPR" in p.regulatory_scope
