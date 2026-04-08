"""Profile Manager — load, save, and cache the active CompanyProfile.

Reads/writes from the flat JSON file at COMPANY_PROFILE_PATH.
Uses an in-memory cache so repeated reads are free.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from sentinel.config import get_settings
from sentinel.models.company_profile import CompanyProfile

logger = structlog.get_logger(__name__)

# ── In-memory cache ──────────────────────────────────────────────────────
_cached_profile: Optional[CompanyProfile] = None


def _profile_path() -> Path:
    """Resolve the company profile JSON path from settings."""
    return Path(get_settings().COMPANY_PROFILE_PATH)


def load_profile() -> CompanyProfile:
    """Read CompanyProfile from JSON file on disk.

    Returns a default empty profile if the file doesn't exist
    or contains invalid JSON.
    """
    global _cached_profile

    path = _profile_path()
    if not path.exists():
        logger.warning("profile.file_not_found", path=str(path))
        _cached_profile = CompanyProfile()
        return _cached_profile

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        _cached_profile = CompanyProfile(**data)
        logger.info("profile.loaded", name=_cached_profile.name, path=str(path))
        return _cached_profile
    except (json.JSONDecodeError, Exception):
        logger.exception("profile.load_error", path=str(path))
        _cached_profile = CompanyProfile()
        return _cached_profile


def save_profile(profile: CompanyProfile) -> CompanyProfile:
    """Write CompanyProfile to JSON file and refresh cache.

    Automatically sets updated_at to now.
    """
    global _cached_profile

    profile.updated_at = datetime.now(timezone.utc)
    path = _profile_path()

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        profile.model_dump_json(indent=2),
        encoding="utf-8",
    )
    _cached_profile = profile
    logger.info("profile.saved", name=profile.name, path=str(path))
    return _cached_profile


def get_active_profile() -> CompanyProfile:
    """Return the cached profile, loading from disk on first call."""
    global _cached_profile
    if _cached_profile is None:
        return load_profile()
    return _cached_profile
