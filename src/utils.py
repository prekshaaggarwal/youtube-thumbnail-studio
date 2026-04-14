from __future__ import annotations

import datetime as dt
import os
from pathlib import Path


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def iso_to_datetime(iso_str: str) -> dt.datetime:
    # YouTube timestamps are usually in UTC with trailing Z
    try:
        if iso_str.endswith("Z"):
            iso_str = iso_str.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(iso_str)
    except Exception:
        return dt.datetime.now(dt.timezone.utc)


def days_since(iso_str: str) -> float:
    published = iso_to_datetime(iso_str)
    now = dt.datetime.now(dt.timezone.utc)
    delta = now - published.astimezone(dt.timezone.utc)
    return max(delta.total_seconds() / 86400.0, 0.1)


def get_api_key(cli_key: str | None = None) -> str:
    if cli_key:
        return cli_key
    env_key = os.getenv("YOUTUBE_API_KEY")
    if env_key:
        return env_key
    raise ValueError("No API key found. Pass --api-key or set YOUTUBE_API_KEY.")

