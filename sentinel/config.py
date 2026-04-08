"""SENTINEL configuration — pydantic-settings BaseSettings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # --- API Keys ---
    OPENROUTER_API_KEY: str = ""
    NEWSAPI_KEY: str = ""

    # --- Model Routing ---
    SENTINEL_PRIMARY_MODEL: str = "google/gemini-3-flash-preview"
    SENTINEL_EMBEDDING_MODEL: str = "google/gemini-embedding-001"

    # --- LLM Provider Switching ---
    LLM_PROVIDER: str = "openrouter"  # "openrouter" or "groq"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # --- Qdrant ---
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "sentinel_signals"

    # --- Runtime ---
    DEMO_MODE: bool = False
    LOG_LEVEL: str = "INFO"

    # --- Company Profile (Level 2) ---
    COMPANY_PROFILE_PATH: str = "data/company_profile.json"

    # --- Memory (Level 3) ---
    QDRANT_MEMORY_COLLECTION: str = "sentinel_memory"

    # --- Alerts (Level 3) ---
    ALERT_DEMO_MODE: bool = True
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_EMAIL_TO: str = ""
    SLACK_WEBHOOK_URL: str = ""

    # --- Prompt Optimisation (Level 4) ---
    QDRANT_PROMPTS_COLLECTION: str = "sentinel_prompts"
    QUALITY_THRESHOLD: float = 0.70
    OPTIMISER_ENABLED: bool = True
    OPTIMISER_MIN_RUNS: int = 3

    # --- Human Feedback (Level 5) ---
    QDRANT_FEEDBACK_COLLECTION: str = "sentinel_feedback"
    FEEDBACK_BASE_URL: str = "http://localhost:8000"
    FEEDBACK_WINDOW_DAYS: int = 30
    FEEDBACK_MIN_ENTRIES: int = 5
    ALERTS_ENABLED: bool = True

    # --- Multi-Tenant Federated Intelligence (Level 6) ---
    ACTIVE_TENANT: str = "default"                            # which tenant is active
    TENANTS_DIR: str = "data/tenants"                        # tenant data root dir
    QDRANT_SHARED_COLLECTION: str = "sentinel_shared_patterns"  # cross-tenant anonymised patterns

    # --- Predictive Risk Intelligence (Level 7) ---
    FORECAST_ENABLED: bool = True                    # master switch for ForecastAgent
    FORECAST_ALERT_THRESHOLD: float = 0.80           # fire predictive alert if probability > this
    FORECAST_MIN_PROBABILITY: float = 0.40           # minimum probability to store a forecast
    FORECAST_MIN_HISTORY: int = 5                    # min past signals needed before forecasting
    FORECAST_HORIZON_DEFAULT: str = "H72"            # default forecast horizon

    # --- Autonomous Actions (Level 8) ---
    ACTION_DEMO_MODE: bool = True                    # log actions instead of executing
    ACTION_AUTO_THRESHOLD: float = 0.85              # auto-execute if confidence >= this
    ACTION_APPROVAL_THRESHOLD: float = 0.60          # require approval if confidence >= this
    JIRA_BASE_URL: str = ""                          # e.g. https://yoursite.atlassian.net
    JIRA_EMAIL: str = ""
    JIRA_API_TOKEN: str = ""
    JIRA_PROJECT_KEY: str = "SEC"
    PAGERDUTY_INTEGRATION_KEY: str = ""
    ACTION_WEBHOOK_URL: str = ""                     # default webhook URL

    # --- Negotiation (Level 9) ---
    SERPAPI_KEY: str = ""                             # optional, DuckDuckGo fallback if empty
    NEGOTIATION_ENABLED: bool = True                  # master switch
    NEGOTIATION_AUTO_SEND: bool = False               # false = human approves emails before send
    NEGOTIATION_TIMEOUT_HOURS: int = 24               # max time to wait for replies
    REPLY_POLL_INTERVAL_MINUTES: int = 30             # how often to check inbox for replies
    NEGOTIATION_MAX_ALTERNATIVES: int = 5             # max suppliers to contact

    # --- Meta + Governance (Level 10) ---
    META_RUN_INTERVAL_RUNS: int = 5                   # run MetaAgent every N pipeline runs
    META_ENABLED: bool = True                         # master switch for MetaAgent
    AB_TEST_ENABLED: bool = True                      # enable A/B testing for prompts
    AB_TEST_MIN_RUNS: int = 10                        # runs before declaring A/B winner
    GOVERNANCE_ENABLED: bool = True                   # enable immutable governance log
    OVERRIDE_RULES_PATH: str = "data/override_rules.json"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

    @property
    def demo_mode(self) -> bool:
        """Alias for DEMO_MODE for convenience."""
        return self.DEMO_MODE


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton pattern)."""
    return Settings()


class _SettingsProxy(Settings):
    """Lazy proxy so `from sentinel.config import settings` works
    without eagerly creating Settings at import time.

    Inherits from Settings purely for type-checking — Pylance sees all
    fields.  At runtime __getattr__ delegates to the cached singleton.
    """

    def __init__(self) -> None:  # noqa: D107
        # Skip Settings.__init__ — never actually constructed as a real Settings
        pass

    def __getattr__(self, name: str):
        return getattr(get_settings(), name)


# Module-level alias — lazy, defers to get_settings() on first access
settings: Settings = _SettingsProxy()  # type: ignore[assignment]
