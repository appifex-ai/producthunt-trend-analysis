from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_API_URL = "https://api.producthunt.com/v2/api/graphql"
DEFAULT_DB_PATH = Path("data/producthunt.sqlite3")


@dataclass(frozen=True)
class Settings:
    token: str
    api_url: str = DEFAULT_API_URL
    db_path: Path = DEFAULT_DB_PATH
    page_size: int = 20
    page_delay_seconds: float = 0.25
    rate_limit_reserve: int = 250
    max_retries: int = 6

    @classmethod
    def from_env(
        cls,
        *,
        db_path: str | Path | None = None,
        page_delay_seconds: float | None = None,
        rate_limit_reserve: int | None = None,
    ) -> Settings:
        token = os.environ.get("PRODUCT_HUNT_TOKEN", "").strip()
        if not token:
            raise ValueError("PRODUCT_HUNT_TOKEN is required for API sync")

        resolved_db = Path(db_path or os.environ.get("PH_TRENDS_DB", DEFAULT_DB_PATH))
        return cls(
            token=token,
            api_url=os.environ.get("PRODUCT_HUNT_API_URL", DEFAULT_API_URL).strip(),
            db_path=resolved_db,
            page_delay_seconds=(
                page_delay_seconds
                if page_delay_seconds is not None
                else float(os.environ.get("PH_TRENDS_PAGE_DELAY", "0.25"))
            ),
            rate_limit_reserve=(
                rate_limit_reserve
                if rate_limit_reserve is not None
                else int(os.environ.get("PH_TRENDS_RATE_RESERVE", "250"))
            ),
        )
