"""Application configuration, paths and user-editable settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

APP_NAME = "UPSC Daily"

if os.name == "nt":
    _BASE = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
else:
    _BASE = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

DATA_DIR = _BASE / "UPSCDaily"
DB_PATH = DATA_DIR / "upsc_daily.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
EXPORT_DIR = DATA_DIR / "exports"

DEFAULT_FEEDS: list[dict[str, str]] = [
    {"name": "PIB Press Releases", "url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "subject": "Mixed"},
    {"name": "The Hindu — National", "url": "https://www.thehindu.com/news/national/feeder/default.rss", "subject": "Mixed"},
    {"name": "The Hindu — Economy", "url": "https://www.thehindu.com/business/Economy/feeder/default.rss", "subject": "Economy"},
    {"name": "The Hindu — Sci & Tech", "url": "https://www.thehindu.com/sci-tech/feeder/default.rss", "subject": "Science & Technology"},
    {"name": "The Hindu — Energy & Environment", "url": "https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss", "subject": "Environment & Ecology"},
    {"name": "Indian Express — Explained", "url": "https://indianexpress.com/section/explained/feed/", "subject": "Mixed"},
    {"name": "Indian Express — India", "url": "https://indianexpress.com/section/india/feed/", "subject": "Mixed"},
    {"name": "Down To Earth", "url": "https://www.downtoearth.org.in/rss/environment", "subject": "Environment & Ecology"},
    {"name": "Mint — Economy", "url": "https://www.livemint.com/rss/economy", "subject": "Economy"},
    {"name": "ET — Economy Policy", "url": "https://economictimes.indiatimes.com/news/economy/policy/rssfeeds/1286551815.cms", "subject": "Economy"},
]


@dataclass
class Settings:
    """User-editable settings persisted as JSON."""

    feeds: list[dict[str, str]] = field(default_factory=lambda: [dict(f) for f in DEFAULT_FEEDS])
    articles_per_feed: int = 12
    prelims_count: int = 20
    mains_count: int = 5
    backend: str = "auto"          # auto | api | cli | offline
    model: str = "claude-sonnet-5"
    api_key_env: str = "ANTHROPIC_API_KEY"
    fetch_full_text: bool = True
    request_timeout: int = 20

    @classmethod
    def load(cls) -> "Settings":
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if SETTINGS_PATH.exists():
            try:
                raw: dict[str, Any] = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return cls()
            known = {f for f in cls.__dataclass_fields__}
            return cls(**{k: v for k, v in raw.items() if k in known})
        obj = cls()
        obj.save()
        return obj

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) or None
