"""BaseAgent — abstract base class for all SENTINEL agents.

Every agent in Layers 0–4 inherits from BaseAgent.  It provides:
- Structured logging via structlog
- Access to the LLM client (complete / embed)
- Access to the Qdrant vector store
- A standard async `run()` interface for LangGraph nodes
- Demo-mode awareness via settings.DEMO_MODE
"""

from __future__ import annotations

import abc
from typing import Any

import structlog

from sentinel.config import get_settings
from sentinel.llm import client as llm


class BaseAgent(abc.ABC):
    """Abstract base for every SENTINEL pipeline agent.

    Subclasses MUST implement ``run()``.  They MAY override
    ``agent_name`` for cleaner log output.
    """

    # Override in subclass for nicer logging (e.g. "NewsScanner")
    agent_name: str = "BaseAgent"

    def __init__(self, *, demo_mode: bool | None = None) -> None:
        self.log = structlog.get_logger(agent=self.agent_name)
        if demo_mode is not None:
            self.demo_mode = demo_mode
        else:
            self.demo_mode = get_settings().DEMO_MODE

    # ------------------------------------------------------------------
    # LLM helpers — thin wrappers so agents never import llm directly
    # ------------------------------------------------------------------

    async def llm_complete(self, prompt: str, *, thinking: bool = False) -> str:
        """Call the shared LLM client for chat completion.

        Args:
            prompt:   User-role prompt text.
            thinking: Enable extended thinking (budget_tokens=8000).
        """
        self.log.debug("agent.llm_complete", thinking=thinking)
        return await llm.complete(prompt, thinking=thinking)

    async def llm_embed(self, text: str) -> list[float]:
        """Generate an embedding vector via the shared LLM client."""
        self.log.debug("agent.llm_embed", chars=len(text))
        return await llm.embed(text)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute this agent's logic as a LangGraph node.

        Args:
            state: The shared LangGraph pipeline state dict.

        Returns:
            Updated state dict with this agent's contributions.
        """
        ...

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<{self.agent_name} demo_mode={self.demo_mode}>"
