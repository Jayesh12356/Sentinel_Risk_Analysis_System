"""WebSearchAgent — finds alternative suppliers via web search (Level 9).

Uses SerpAPI (if key configured), DuckDuckGo httpx scraping (fallback),
or demo mode with data/demo_alternatives.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog

from sentinel.config import get_settings
from sentinel.models.negotiation import AlternativeSupplier

logger = structlog.get_logger(__name__)


class WebSearchAgent:
    """Finds alternative suppliers using web search or demo data."""

    def __init__(self, demo_mode: bool = False) -> None:
        self.demo_mode = demo_mode

    async def search(
        self,
        original_supplier: str,
        industry: str = "",
        company_profile: Any = None,
        max_results: int = 5,
    ) -> list[AlternativeSupplier]:
        """Find alternative suppliers.

        Args:
            original_supplier: The at-risk supplier name
            industry: Industry sector to search within
            company_profile: Optional company profile for context
            max_results: Max alternatives to return

        Returns:
            List of AlternativeSupplier objects
        """
        settings = get_settings()

        if self.demo_mode or settings.DEMO_MODE:
            return await self._load_demo_alternatives(max_results)

        # Generate search queries via LLM
        queries = await self._generate_queries(original_supplier, industry)

        # Try SerpAPI first, then DuckDuckGo
        results: list[AlternativeSupplier] = []
        if settings.SERPAPI_KEY:
            try:
                results = await self._search_serpapi(queries, max_results)
            except Exception as exc:
                logger.warning("web_search.serpapi_failed", error=str(exc))

        if not results:
            try:
                results = await self._search_duckduckgo(queries, max_results)
            except Exception as exc:
                logger.warning("web_search.duckduckgo_failed", error=str(exc))

        if not results:
            logger.warning("web_search.all_failed_using_demo")
            results = await self._load_demo_alternatives(max_results)

        logger.info("web_search.complete", count=len(results), source="live")
        return results[:max_results]

    async def _generate_queries(self, supplier: str, industry: str) -> list[str]:
        """Generate search queries via LLM (thinking=OFF)."""
        try:
            from sentinel.llm.client import get_chat_completion

            prompt = (
                f"Given supplier '{supplier}' in the '{industry or 'technology'}' industry, "
                f"generate 3 short search queries to find alternative suppliers or partners. "
                f"Return ONLY a JSON array of 3 strings, nothing else."
            )
            response = await get_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            content = response.choices[0].message.content.strip()
            # Parse JSON array
            if content.startswith("["):
                queries = json.loads(content)
                if isinstance(queries, list):
                    return queries[:3]
        except Exception as exc:
            logger.warning("web_search.query_gen_failed", error=str(exc))

        # Fallback queries
        return [
            f"alternatives to {supplier} {industry}",
            f"{industry or 'enterprise'} suppliers competitors to {supplier}",
            f"best {industry or 'technology'} service providers 2025",
        ]

    async def _search_serpapi(
        self, queries: list[str], max_results: int
    ) -> list[AlternativeSupplier]:
        """Search using SerpAPI Google Search API."""
        import httpx

        settings = get_settings()
        results: list[AlternativeSupplier] = []
        seen_names: set[str] = set()

        for query in queries[:2]:  # Limit API calls
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        "https://serpapi.com/search",
                        params={
                            "q": query,
                            "api_key": settings.SERPAPI_KEY,
                            "engine": "google",
                            "num": 5,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                for item in data.get("organic_results", [])[:5]:
                    name = item.get("title", "").split(" - ")[0].split(" | ")[0].strip()
                    if name and name not in seen_names:
                        seen_names.add(name)
                        results.append(AlternativeSupplier(
                            name=name,
                            website=item.get("link", ""),
                            description=item.get("snippet", "")[:200],
                            relevance_score=0.7,
                            search_source="serpapi",
                        ))
            except Exception as exc:
                logger.warning("web_search.serpapi_query_failed", query=query, error=str(exc))

        return results[:max_results]

    async def _search_duckduckgo(
        self, queries: list[str], max_results: int
    ) -> list[AlternativeSupplier]:
        """Search using DuckDuckGo HTML scraping (no API key needed)."""
        import httpx
        import re

        results: list[AlternativeSupplier] = []
        seen_names: set[str] = set()

        for query in queries[:2]:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        "https://html.duckduckgo.com/html/",
                        params={"q": query},
                        headers={"User-Agent": "Mozilla/5.0 (compatible; SENTINEL/9.0)"},
                    )
                    text = resp.text

                # Simple extraction of result titles and snippets
                title_pattern = r'class="result__a"[^>]*>([^<]+)</a>'
                snippet_pattern = r'class="result__snippet"[^>]*>([^<]+)'
                link_pattern = r'class="result__url"[^>]*href="([^"]+)"'

                titles = re.findall(title_pattern, text)
                snippets = re.findall(snippet_pattern, text)
                links = re.findall(link_pattern, text)

                for i, title in enumerate(titles[:5]):
                    name = title.strip().split(" - ")[0].split(" | ")[0].strip()
                    if name and name not in seen_names:
                        seen_names.add(name)
                        results.append(AlternativeSupplier(
                            name=name,
                            website=links[i] if i < len(links) else "",
                            description=snippets[i][:200] if i < len(snippets) else "",
                            relevance_score=0.6,
                            search_source="duckduckgo",
                        ))
            except Exception as exc:
                logger.warning("web_search.ddg_query_failed", query=query, error=str(exc))

        return results[:max_results]

    async def _load_demo_alternatives(
        self, max_results: int = 5
    ) -> list[AlternativeSupplier]:
        """Load mock alternatives from data/demo_alternatives.json."""
        demo_path = Path("data") / "demo_alternatives.json"
        if not demo_path.exists():
            # Check relative to project root
            project_root = Path(__file__).parent.parent.parent
            demo_path = project_root / "data" / "demo_alternatives.json"

        try:
            with open(demo_path, encoding="utf-8") as f:
                data = json.load(f)
            suppliers = [AlternativeSupplier(**item) for item in data[:max_results]]
            logger.info("web_search.demo_loaded", count=len(suppliers))
            return suppliers
        except Exception as exc:
            logger.error("web_search.demo_load_failed", error=str(exc))
            # Return hardcoded fallback
            return [
                AlternativeSupplier(
                    name="CloudScale Solutions",
                    website="https://cloudscale.io",
                    description="Enterprise cloud infrastructure provider",
                    relevance_score=0.9,
                    search_source="demo_fallback",
                ),
            ]
