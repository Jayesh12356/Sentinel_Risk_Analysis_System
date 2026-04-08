"""NewsScanner — Layer 0 sensor agent for news intelligence.

Live mode:  RSS feeds via feedparser + NewsAPI via httpx.
Demo mode:  Loads from data/sample_signals/news.json.

Per CONTEXT.md conventions:
- Inherits BaseAgent
- Async throughout
- All external calls wrapped in try/except with demo fallback
- structlog only (no print)
- Thinking OFF (Layer 0 default)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import feedparser
import httpx
import structlog

from sentinel.agents.base import BaseAgent
from sentinel.config import settings
from sentinel.models.signal import Signal, SignalSource

logger = structlog.get_logger(__name__)

# Default RSS feeds for live mode
DEFAULT_RSS_FEEDS: list[str] = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
]

SAMPLE_DATA_PATH = Path("data/sample_signals/news.json")


class NewsScanner(BaseAgent):
    """Scans RSS feeds and NewsAPI for intelligence signals.

    Produces a list of Signal objects tagged with source=NEWS.
    """

    agent_name: str = "NewsScanner"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute news scanning — LangGraph node entry point."""
        self.log.info("news_scanner.start", demo_mode=self.demo_mode)

        if self.demo_mode:
            signals = await self._load_demo_data()
        else:
            signals = await self._fetch_live()

        # Merge with any existing signals in state
        existing: list[Signal] = state.get("signals", [])
        existing.extend(signals)

        self.log.info("news_scanner.done", new_signals=len(signals), total=len(existing))
        return {"signals": existing}

    # ------------------------------------------------------------------
    # Demo mode
    # ------------------------------------------------------------------

    async def _load_demo_data(self) -> list[Signal]:
        """Load sample news signals from JSON file."""
        self.log.info("news_scanner.demo.loading", path=str(SAMPLE_DATA_PATH))

        try:
            raw = SAMPLE_DATA_PATH.read_text(encoding="utf-8")
            items: list[dict] = json.loads(raw)
        except (FileNotFoundError, json.JSONDecodeError):
            self.log.exception("news_scanner.demo.error")
            return []

        signals: list[Signal] = []
        for item in items:
            published = None
            if item.get("published_at"):
                try:
                    published = datetime.fromisoformat(
                        item["published_at"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            signals.append(
                Signal(
                    source=SignalSource.NEWS,
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    url=item.get("url", ""),
                    published_at=published,
                    demo=True,
                )
            )

        self.log.info("news_scanner.demo.loaded", count=len(signals))
        return signals

    # ------------------------------------------------------------------
    # Live mode
    # ------------------------------------------------------------------

    async def _fetch_live(self) -> list[Signal]:
        """Fetch from RSS feeds + NewsAPI, with demo fallback on failure."""
        signals: list[Signal] = []

        # --- RSS feeds ---
        try:
            rss_signals = await self._fetch_rss()
            signals.extend(rss_signals)
        except Exception:
            self.log.exception("news_scanner.rss.error")

        # --- NewsAPI ---
        try:
            api_signals = await self._fetch_newsapi()
            signals.extend(api_signals)
        except Exception:
            self.log.exception("news_scanner.newsapi.error")

        # Fallback to demo data if live fetch returned nothing
        if not signals:
            self.log.warning("news_scanner.live.empty_fallback_to_demo")
            signals = await self._load_demo_data()

        return signals

    async def _fetch_rss(self) -> list[Signal]:
        """Parse RSS feeds via feedparser."""
        signals: list[Signal] = []

        for feed_url in DEFAULT_RSS_FEEDS:
            self.log.info("news_scanner.rss.fetching", url=feed_url)
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(feed_url)
                    resp.raise_for_status()

                feed = feedparser.parse(resp.text)

                for entry in feed.entries[:10]:  # Cap at 10 per feed
                    published = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            tp = entry.published_parsed  # type: ignore[union-attr]
                            published = datetime(
                                tp[0], tp[1], tp[2], tp[3], tp[4], tp[5],  # type: ignore[arg-type]
                            )
                        except (TypeError, ValueError, IndexError):
                            pass

                    signals.append(
                        Signal(
                            source=SignalSource.NEWS,
                            title=getattr(entry, "title", ""),
                            content=getattr(entry, "summary", ""),
                            url=getattr(entry, "link", ""),
                            published_at=published,
                        )
                    )

                self.log.info(
                    "news_scanner.rss.parsed",
                    url=feed_url,
                    entries=len(feed.entries),
                )
            except Exception:
                self.log.exception("news_scanner.rss.feed_error", url=feed_url)

        return signals

    async def _fetch_newsapi(self) -> list[Signal]:
        """Fetch top headlines from NewsAPI."""
        api_key = settings.NEWSAPI_KEY
        if not api_key:
            self.log.warning("news_scanner.newsapi.no_key")
            return []

        self.log.info("news_scanner.newsapi.fetching")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://newsapi.org/v2/top-headlines",
                params={
                    "language": "en",
                    "pageSize": 20,
                    "apiKey": api_key,
                },
            )
            resp.raise_for_status()

        data = resp.json()
        articles: list[dict] = data.get("articles", [])

        signals: list[Signal] = []
        for article in articles:
            published = None
            if article.get("publishedAt"):
                try:
                    published = datetime.fromisoformat(
                        article["publishedAt"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            signals.append(
                Signal(
                    source=SignalSource.NEWS,
                    title=article.get("title", ""),
                    content=article.get("description", "") or article.get("content", ""),
                    url=article.get("url", ""),
                    published_at=published,
                )
            )

        self.log.info("news_scanner.newsapi.fetched", count=len(signals))
        return signals
