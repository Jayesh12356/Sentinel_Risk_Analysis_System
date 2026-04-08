"""CyberThreatAgent — Layer 0 sensor agent for cyber threat intelligence.

Live mode:  NVD (National Vulnerability Database) CVE API via httpx.
Demo mode:  Loads from data/sample_signals/cyber.json.

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

# NVD API v2.0 endpoint (free, no key required for basic use)
NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

SAMPLE_DATA_PATH = Path("data/sample_signals/cyber.json")


class CyberThreatAgent(BaseAgent):
    """Scans NVD/CVE database for cyber threat signals.

    Produces a list of Signal objects tagged with source=CYBER.
    """

    agent_name: str = "CyberThreatAgent"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute cyber threat scanning — LangGraph node entry point."""
        self.log.info("cyber_threat.start", demo_mode=self.demo_mode)

        if self.demo_mode:
            signals = await self._load_demo_data()
        else:
            signals = await self._fetch_live()

        # Merge with existing signals in state
        existing: list[Signal] = state.get("signals", [])
        existing.extend(signals)

        self.log.info("cyber_threat.done", new_signals=len(signals), total=len(existing))
        return {"signals": existing}

    # ------------------------------------------------------------------
    # Demo mode
    # ------------------------------------------------------------------

    async def _load_demo_data(self) -> list[Signal]:
        """Load sample cyber threat signals from JSON file."""
        self.log.info("cyber_threat.demo.loading", path=str(SAMPLE_DATA_PATH))

        try:
            raw = SAMPLE_DATA_PATH.read_text(encoding="utf-8")
            items: list[dict] = json.loads(raw)
        except (FileNotFoundError, json.JSONDecodeError):
            self.log.exception("cyber_threat.demo.error")
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

            # Build enriched content with CVE metadata
            content_parts = [item.get("content", "")]
            if item.get("cvss_score"):
                content_parts.append(f"CVSS Score: {item['cvss_score']}")
            if item.get("severity"):
                content_parts.append(f"Severity: {item['severity']}")
            if item.get("cwe_id"):
                content_parts.append(f"CWE: {item['cwe_id']}")
            if item.get("affected_products"):
                content_parts.append(
                    f"Affected: {', '.join(item['affected_products'])}"
                )

            signals.append(
                Signal(
                    source=SignalSource.CYBER,
                    title=item.get("title", ""),
                    content=" | ".join(content_parts),
                    url=item.get("url", ""),
                    published_at=published,
                    demo=True,
                )
            )

        self.log.info("cyber_threat.demo.loaded", count=len(signals))
        return signals

    # ------------------------------------------------------------------
    # Live mode
    # ------------------------------------------------------------------

    async def _fetch_live(self) -> list[Signal]:
        """Fetch recent CVEs from NVD API, with demo fallback on failure."""
        try:
            signals = await self._fetch_nvd()
            if signals:
                return signals
        except Exception:
            self.log.exception("cyber_threat.nvd.error")

        # Fallback to demo data if live fetch fails
        self.log.warning("cyber_threat.live.fallback_to_demo")
        return await self._load_demo_data()

    async def _fetch_nvd(self) -> list[Signal]:
        """Query NVD API v2.0 for recent critical/high CVEs."""
        self.log.info("cyber_threat.nvd.fetching")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                NVD_API_URL,
                params={
                    "resultsPerPage": 20,
                    "cvssV3Severity": "CRITICAL",
                },
                headers={
                    "User-Agent": "SENTINEL/0.1.0",
                },
            )
            resp.raise_for_status()

        data = resp.json()
        vulnerabilities: list[dict] = data.get("vulnerabilities", [])

        signals: list[Signal] = []
        for vuln_wrapper in vulnerabilities:
            cve = vuln_wrapper.get("cve", {})
            cve_id = cve.get("id", "")

            # Extract description (English preferred)
            descriptions = cve.get("descriptions", [])
            description = ""
            for desc in descriptions:
                if desc.get("lang") == "en":
                    description = desc.get("value", "")
                    break
            if not description and descriptions:
                description = descriptions[0].get("value", "")

            # Extract CVSS v3.1 score
            metrics = cve.get("metrics", {})
            cvss_data = metrics.get("cvssMetricV31", [])
            cvss_score = 0.0
            severity = "UNKNOWN"
            if cvss_data:
                primary = cvss_data[0].get("cvssData", {})
                cvss_score = primary.get("baseScore", 0.0)
                severity = primary.get("baseSeverity", "UNKNOWN")

            # Extract published date
            published = None
            pub_str = cve.get("published", "")
            if pub_str:
                try:
                    published = datetime.fromisoformat(
                        pub_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            # Build enriched content
            content = (
                f"{description} | CVSS: {cvss_score} | Severity: {severity}"
            )

            signals.append(
                Signal(
                    source=SignalSource.CYBER,
                    title=f"{cve_id} — {severity} (CVSS {cvss_score})",
                    content=content,
                    url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                    published_at=published,
                )
            )

        self.log.info("cyber_threat.nvd.fetched", count=len(signals))
        return signals
