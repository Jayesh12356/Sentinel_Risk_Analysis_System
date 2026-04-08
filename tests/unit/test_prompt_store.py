"""Unit tests for PromptVersion model and PromptStore (Level 4)."""

from __future__ import annotations

import datetime
import unittest

from sentinel.models.prompt_version import PromptVersion


class TestPromptVersion(unittest.TestCase):
    """Test the PromptVersion Pydantic model."""

    def test_creation_defaults(self):
        """PromptVersion should have sensible defaults."""
        pv = PromptVersion(
            agent_name="BriefWriter",
            prompt_text="You are a brief writer.",
        )
        self.assertEqual(pv.agent_name, "BriefWriter")
        self.assertEqual(pv.version, 1)
        self.assertTrue(pv.is_active)
        self.assertIsNone(pv.quality_score)
        self.assertIsInstance(pv.id, str)
        self.assertIsInstance(pv.created_at, datetime.datetime)

    def test_creation_full(self):
        """PromptVersion with all fields set."""
        pv = PromptVersion(
            agent_name="RedTeamAgent",
            version=3,
            prompt_text="You are an adversarial analyst.",
            quality_score=0.65,
            is_active=False,
        )
        self.assertEqual(pv.agent_name, "RedTeamAgent")
        self.assertEqual(pv.version, 3)
        self.assertEqual(pv.quality_score, 0.65)
        self.assertFalse(pv.is_active)

    def test_to_payload(self):
        """to_payload produces expected dict keys."""
        pv = PromptVersion(
            agent_name="BriefWriter",
            prompt_text="You are a brief writer.",
        )
        payload = pv.to_payload()
        required_keys = {
            "id", "agent_name", "version", "prompt_text",
            "quality_score", "created_at", "is_active",
        }
        self.assertEqual(set(payload.keys()), required_keys)
        self.assertEqual(payload["agent_name"], "BriefWriter")
        self.assertTrue(payload["is_active"])

    def test_from_payload_roundtrip(self):
        """to_payload → from_payload should preserve all fields."""
        pv1 = PromptVersion(
            agent_name="CausalChain",
            version=2,
            prompt_text="Analyse root causes.",
            quality_score=0.72,
            is_active=True,
        )
        payload = pv1.to_payload()
        pv2 = PromptVersion.from_payload(payload)
        self.assertEqual(pv1.agent_name, pv2.agent_name)
        self.assertEqual(pv1.version, pv2.version)
        self.assertEqual(pv1.prompt_text, pv2.prompt_text)
        self.assertEqual(pv1.quality_score, pv2.quality_score)
        self.assertEqual(pv1.is_active, pv2.is_active)

    def test_version_must_be_positive(self):
        """Version must be >= 1."""
        with self.assertRaises(Exception):
            PromptVersion(
                agent_name="Test",
                version=0,
                prompt_text="test",
            )

    def test_prompt_text_required(self):
        """prompt_text is a required field."""
        with self.assertRaises(Exception):
            PromptVersion(agent_name="Test")  # type: ignore


if __name__ == "__main__":
    unittest.main()
