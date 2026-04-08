"""ABTestManager — silent A/B testing for prompt variants (Level 10).

Manages parallel evaluation of current vs challenger prompts.
After AB_TEST_MIN_RUNS, declares a winner and activates it.
"""

from __future__ import annotations

import json
import uuid as uuid_mod
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from pydantic import BaseModel, Field

from sentinel.config import get_settings

logger = structlog.get_logger(__name__)

# In-memory test store (persisted to JSON)
_AB_TESTS_PATH = Path("data/ab_tests.json")


class ABTestConfig(BaseModel):
    """Configuration and state for a single A/B test."""
    id: str = Field(default_factory=lambda: str(uuid_mod.uuid4()))
    agent_name: str
    variant_a: str  # current active prompt version ID
    variant_b: str  # challenger prompt version ID
    start_time: datetime = Field(default_factory=datetime.utcnow)
    run_count_a: int = 0
    run_count_b: int = 0
    quality_sum_a: float = 0.0
    quality_sum_b: float = 0.0
    status: str = "RUNNING"  # RUNNING / COMPLETE / WINNER_A / WINNER_B
    winner: Optional[str] = None

    @property
    def avg_quality_a(self) -> float:
        return self.quality_sum_a / max(self.run_count_a, 1)

    @property
    def avg_quality_b(self) -> float:
        return self.quality_sum_b / max(self.run_count_b, 1)


class ABTestManager:
    """Manages silent A/B tests between prompt variants."""

    def __init__(self) -> None:
        self._tests: dict[str, ABTestConfig] = {}
        self._load()

    def _load(self) -> None:
        """Load tests from JSON file."""
        path = self._resolve_path()
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    if isinstance(item.get("start_time"), str):
                        item["start_time"] = datetime.fromisoformat(item["start_time"])
                    test = ABTestConfig(**item)
                    self._tests[test.agent_name] = test
            except Exception as exc:
                logger.warning("ab_test.load_failed", error=str(exc))

    def _save(self) -> None:
        """Persist tests to JSON file."""
        path = self._resolve_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = []
            for test in self._tests.values():
                d = test.model_dump()
                d["start_time"] = test.start_time.isoformat()
                data.append(d)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            logger.warning("ab_test.save_failed", error=str(exc))

    def _resolve_path(self) -> Path:
        path = _AB_TESTS_PATH
        if not path.exists():
            project_root = Path(__file__).parent.parent.parent
            path = project_root / _AB_TESTS_PATH
        return path

    def start_test(
        self, agent_name: str, variant_a: str, variant_b: str
    ) -> ABTestConfig:
        """Start a new A/B test for an agent's prompt."""
        settings = get_settings()
        if not settings.AB_TEST_ENABLED:
            logger.info("ab_test.disabled", agent=agent_name)
            return ABTestConfig(
                agent_name=agent_name, variant_a=variant_a,
                variant_b=variant_b, status="COMPLETE", winner=variant_b,
            )

        # Cancel any existing test for this agent
        if agent_name in self._tests:
            self._tests[agent_name].status = "COMPLETE"

        test = ABTestConfig(
            agent_name=agent_name,
            variant_a=variant_a,
            variant_b=variant_b,
        )
        self._tests[agent_name] = test
        self._save()

        logger.info(
            "ab_test.started",
            agent=agent_name,
            variant_a=variant_a,
            variant_b=variant_b,
        )
        return test

    def get_prompt_for_run(self, agent_name: str, run_number: int) -> Optional[str]:
        """Get which prompt variant to use for this run.

        Returns variant ID or None if no test is running.
        Odd runs = variant_a, even runs = variant_b.
        """
        test = self._tests.get(agent_name)
        if not test or test.status != "RUNNING":
            return None

        if run_number % 2 == 1:
            return test.variant_a
        else:
            return test.variant_b

    def record_result(
        self, agent_name: str, variant: str, quality_score: float
    ) -> Optional[ABTestConfig]:
        """Record a quality result for a test variant.

        Returns updated test config or None if no test found.
        """
        test = self._tests.get(agent_name)
        if not test or test.status != "RUNNING":
            return None

        if variant == test.variant_a:
            test.run_count_a += 1
            test.quality_sum_a += quality_score
        elif variant == test.variant_b:
            test.run_count_b += 1
            test.quality_sum_b += quality_score
        else:
            return None

        self._save()
        return test

    async def evaluate_test(self, agent_name: str) -> Optional[ABTestConfig]:
        """Evaluate if an A/B test has enough data to declare a winner.

        Returns test config with winner set, or None.
        """
        settings = get_settings()
        test = self._tests.get(agent_name)
        if not test or test.status != "RUNNING":
            return None

        total_runs = test.run_count_a + test.run_count_b
        if total_runs < settings.AB_TEST_MIN_RUNS:
            return None  # Not enough data yet

        # Compare averages
        avg_a = test.avg_quality_a
        avg_b = test.avg_quality_b

        if avg_b > avg_a * 1.02:  # B needs to be >2% better
            test.status = "WINNER_B"
            test.winner = test.variant_b
        elif avg_a > avg_b * 1.02:
            test.status = "WINNER_A"
            test.winner = test.variant_a
        else:
            # Tie — keep current (variant A)
            test.status = "WINNER_A"
            test.winner = test.variant_a

        self._save()

        # Log to governance
        try:
            from sentinel.meta.governance import log_event
            await log_event(
                event_type="AB_TEST_RESULT",
                agent_name=agent_name,
                description=(
                    f"A/B test complete: {test.status}. "
                    f"A={avg_a:.3f} ({test.run_count_a} runs), "
                    f"B={avg_b:.3f} ({test.run_count_b} runs)"
                ),
                reasoning=f"Winner: {test.winner}",
                confidence=max(avg_a, avg_b),
            )
        except Exception:
            pass

        logger.info(
            "ab_test.evaluated",
            agent=agent_name,
            winner=test.winner,
            avg_a=avg_a,
            avg_b=avg_b,
        )
        return test

    def get_all_tests(self) -> list[ABTestConfig]:
        """Get all tests."""
        return list(self._tests.values())

    def get_active_tests(self) -> list[ABTestConfig]:
        """Get only running tests."""
        return [t for t in self._tests.values() if t.status == "RUNNING"]

    def get_test(self, test_id: str) -> Optional[ABTestConfig]:
        """Get a test by ID."""
        for t in self._tests.values():
            if t.id == test_id:
                return t
        return None
