"""FinancialSignalAgent — Layer 0 sensor agent for financial intelligence.

Live mode:  SEC EDGAR EFTS full-text search API via httpx.
Demo mode:  Loads from data/sample_signals/financial.json.

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

import httpx
import structlog

from sentinel.agents.base import BaseAgent
from sentinel.models.signal import Signal, SignalSource

logger = structlog.get_logger(__name__)

# SEC EDGAR EFTS (full-text search) endpoint
EDGAR_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FILINGS_URL = "https://www.sec.gov/cgi-bin/browse-edgar"

# SEC requires a legitimate User-Agent with contact info
EDGAR_USER_AGENT = "SENTINEL/0.1.0 (sentinel-research@example.com)"

SAMPLE_DATA_PATH = Path("data/sample_signals/financial.json")

# Filing types to monitor for risk signals
MONITORED_FILING_TYPES = ["8-K", "10-K", "10-Q"]


class FinancialSignalAgent(BaseAgent):
    """Scans SEC EDGAR for financial risk signals from regulatory filings.

    Produces a list of Signal objects tagged with source=FINANCIAL.
    """

    agent_name: str = "FinancialSignalAgent"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute financial signal scanning — LangGraph node entry point."""
        self.log.info("financial_signal.start", demo_mode=self.demo_mode)

        if self.demo_mode:
            signals = await self._load_demo_data()
        else:
            signals = await self._fetch_live()

        # Merge with existing signals in state
        existing: list[Signal] = state.get("signals", [])
        existing.extend(signals)

        self.log.info(
            "financial_signal.done", new_signals=len(signals), total=len(existing)
        )
        return {"signals": existing}

    # ------------------------------------------------------------------
    # Demo mode
    # ------------------------------------------------------------------

    async def _load_demo_data(self) -> list[Signal]:
        """Load sample financial signals from JSON file."""
        self.log.info("financial_signal.demo.loading", path=str(SAMPLE_DATA_PATH))

        try:
            raw = SAMPLE_DATA_PATH.read_text(encoding="utf-8")
            items: list[dict] = json.loads(raw)
        except (FileNotFoundError, json.JSONDecodeError):
            self.log.exception("financial_signal.demo.error")
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

            # Build enriched content with filing metadata
            content_parts = [item.get("content", "")]
            if item.get("filing_type"):
                content_parts.append(f"Filing: {item['filing_type']}")
            if item.get("company"):
                content_parts.append(f"Company: {item['company']}")
            if item.get("ticker"):
                content_parts.append(f"Ticker: {item['ticker']}")
            if item.get("cik"):
                content_parts.append(f"CIK: {item['cik']}")

            signals.append(
                Signal(
                    source=SignalSource.FINANCIAL,
                    title=item.get("title", ""),
                    content=" | ".join(content_parts),
                    url=item.get("url", ""),
                    published_at=published,
                    demo=True,
                )
            )

        self.log.info("financial_signal.demo.loaded", count=len(signals))
        return signals

    # ------------------------------------------------------------------
    # Live mode
    # ------------------------------------------------------------------

    async def _fetch_live(self) -> list[Signal]:
        """Fetch recent SEC filings, with demo fallback on failure."""
        try:
            signals = await self._fetch_edgar()
            if signals:
                return signals
        except Exception:
            self.log.exception("financial_signal.edgar.error")

        # Fallback to demo data if live fetch fails
        self.log.warning("financial_signal.live.fallback_to_demo")
        return await self._load_demo_data()

    async def _fetch_edgar(self) -> list[Signal]:
        """Query SEC EDGAR full-text search for recent risk-relevant filings."""
        self.log.info("financial_signal.edgar.fetching")

        signals: list[Signal] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Use EDGAR full-text search API for recent filings
            resp = await client.get(
                "https://efts.sec.gov/LATEST/search-index",
                params={
                    "q": "risk material weakness cybersecurity impairment",
                    "dateRange": "custom",
                    "startdt": "2025-01-01",
                    "enddt": "2025-12-31",
                    "forms": ",".join(MONITORED_FILING_TYPES),
                },
                headers={
                    "User-Agent": EDGAR_USER_AGENT,
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()

            data = resp.json()
            hits: list[dict] = data.get("hits", {}).get("hits", [])

            for hit in hits[:20]:  # Cap at 20 results
                source = hit.get("_source", {})

                published = None
                date_str = source.get("file_date", "")
                if date_str:
                    try:
                        published = datetime.fromisoformat(date_str)
                    except ValueError:
                        pass

                company = source.get("display_names", ["Unknown"])[0]
                filing_type = source.get("form_type", "")
                file_num = source.get("file_num", "")

                title = f"{company} — {filing_type} Filing"
                content = (
                    f"{source.get('display_names', [''])[0]} filed {filing_type}. "
                    f"File Number: {file_num}"
                )

                signals.append(
                    Signal(
                        source=SignalSource.FINANCIAL,
                        title=title,
                        content=content,
                        url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={file_num}",
                        published_at=published,
                    )
                )

        self.log.info("financial_signal.edgar.fetched", count=len(signals))
        return signals
