"""Application settings loaded from environment variables."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class SupabaseSettings:
    url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    service_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_KEY", ""))


@dataclass
class ScraperSettings:
    headless: bool = True
    locale: str = "it-IT"
    timezone_id: str = "Europe/Rome"
    viewport_width: int = 1920
    viewport_height: int = 1080
    request_delay_s: float = 1.5
    page_load_timeout_ms: int = 30_000
    scroll_timeout_s: int = 30
    scroll_pause_s: float = 2.0
    max_scroll_attempts: int = 5
    odds_format: str = "eu"  # eu = decimal


@dataclass
class SchedulerSettings:
    scrape_interval_minutes: int = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "30"))
    enabled: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"


@dataclass
class Settings:
    supabase: SupabaseSettings = field(default_factory=SupabaseSettings)
    scraper: ScraperSettings = field(default_factory=ScraperSettings)
    scheduler: SchedulerSettings = field(default_factory=SchedulerSettings)


settings = Settings()
