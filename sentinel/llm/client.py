"""LLM client — provider-switchable (OpenRouter / Groq).

ALL LLM + embedding calls go through here.
Embeddings always use OpenRouter regardless of LLM_PROVIDER.
"""

from __future__ import annotations

import structlog
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from sentinel.config import settings

logger = structlog.get_logger(__name__)

_llm_client: AsyncOpenAI | None = None
_embed_client: AsyncOpenAI | None = None

# ── resolved at first call ──────────────────────────────────────────
_provider: str = ""
_model: str = ""


def _resolve_provider() -> tuple[str, str, str, str]:
    """Return (provider, base_url, api_key, model) based on LLM_PROVIDER."""
    prov = settings.LLM_PROVIDER.strip().lower()
    if prov == "groq":
        return (
            "groq",
            "https://api.groq.com/openai/v1",
            settings.GROQ_API_KEY,
            settings.GROQ_MODEL,
        )
    # default — openrouter
    return (
        "openrouter",
        "https://openrouter.ai/api/v1",
        settings.OPENROUTER_API_KEY,
        settings.SENTINEL_PRIMARY_MODEL,
    )


def _get_llm_client() -> AsyncOpenAI:
    """Return (and lazily create) the LLM completion client."""
    global _llm_client, _provider, _model  # noqa: PLW0603
    if _llm_client is None:
        prov, base_url, api_key, model = _resolve_provider()
        _provider = prov
        _model = model

        headers = {}
        if prov == "openrouter":
            headers = {"HTTP-Referer": "sentinel", "X-Title": "SENTINEL"}

        _llm_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=headers or None,
        )

        logger.info(
            "llm.provider.active",
            provider=_provider,
            model=_model,
        )
    return _llm_client


def _get_embed_client() -> AsyncOpenAI:
    """Return (and lazily create) the embeddings client.

    Embeddings always go through OpenRouter regardless of LLM_PROVIDER
    because Groq has no embeddings endpoint.
    """
    global _embed_client  # noqa: PLW0603
    if _embed_client is None:
        _embed_client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "sentinel",
                "X-Title": "SENTINEL",
            },
        )
    return _embed_client


# ── public API ──────────────────────────────────────────────────────


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=60))
async def complete(prompt: str, *, thinking: bool = False) -> str:
    """Send a chat completion request via the active LLM provider.

    Args:
        prompt:   The user-role prompt text.
        thinking: If True, enable extended thinking (budget_tokens=8000).
                  Silently ignored when provider is groq.

    Returns:
        The assistant message content as a string.
    """
    client = _get_llm_client()
    model = _model

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    # Groq does not support extra_body thinking — silently skip
    if thinking and _provider != "groq":
        kwargs["extra_body"] = {
            "thinking": {"type": "enabled", "budget_tokens": 8000},
        }

    logger.info("llm.complete.start", provider=_provider, model=model, thinking=thinking)

    try:
        response = await client.chat.completions.create(**kwargs)
        content: str = response.choices[0].message.content or ""
        logger.info("llm.complete.ok", provider=_provider, model=model, chars=len(content))
        return content
    except Exception:
        logger.exception("llm.complete.error", provider=_provider, model=model)
        raise


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=60))
async def embed(text: str) -> list[float]:
    """Generate an embedding vector via OpenRouter.

    Embeddings always use OpenRouter regardless of LLM_PROVIDER
    because Groq has no embeddings endpoint.

    Args:
        text: The input text to embed.

    Returns:
        A list of floats representing the embedding vector.
    """
    client = _get_embed_client()
    model = settings.SENTINEL_EMBEDDING_MODEL

    logger.info("llm.embed.start", model=model, chars=len(text))

    try:
        response = await client.embeddings.create(model=model, input=text)
        vector: list[float] = response.data[0].embedding
        logger.info("llm.embed.ok", model=model, dims=len(vector))
        return vector
    except Exception:
        logger.exception("llm.embed.error", model=model)
        raise
