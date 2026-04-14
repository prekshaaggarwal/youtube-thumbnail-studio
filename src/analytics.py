from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.config import VIDEOS_CSV, VIDEOS_ENRICHED_CSV


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in {"video id", "video_id", "videoid"}:
            renamed[col] = "video_id"
        elif key in {"video", "video url", "url"}:
            renamed[col] = "video_url"
        elif key in {"impressions"}:
            renamed[col] = "impressions"
        elif key in {
            "impressions click-through rate (%)",
            "impressions click-through rate",
            "ctr",
            "click-through rate",
            "ctr (%)",
        }:
            renamed[col] = "ctr"
        elif key in {"views"}:
            renamed[col] = "views_analytics"
    df = df.rename(columns=renamed)
    return df


def _extract_video_id_from_url(url: str) -> str:
    # Handles both watch URLs and youtu.be short links
    if not isinstance(url, str) or not url:
        return ""
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url)
    return match.group(1) if match else ""


def merge_analytics_csv(analytics_csv: str) -> Path:
    if not VIDEOS_CSV.exists():
        raise FileNotFoundError("Run collect first so data/raw/videos.csv exists.")

    analytics_path = Path(analytics_csv)
    if not analytics_path.exists():
        raise FileNotFoundError(f"Analytics CSV not found: {analytics_csv}")

    videos = pd.read_csv(VIDEOS_CSV)
    analytics = pd.read_csv(analytics_path)
    analytics = _normalize_columns(analytics)

    if "video_id" not in analytics.columns:
        if "video_url" not in analytics.columns:
            raise ValueError("Analytics CSV must include Video ID or Video URL column.")
        analytics["video_id"] = analytics["video_url"].apply(_extract_video_id_from_url)

    keep_cols = ["video_id"]
    for col in ("impressions", "ctr", "views_analytics"):
        if col in analytics.columns:
            keep_cols.append(col)

    analytics_small = analytics[keep_cols].copy()
    analytics_small = analytics_small.drop_duplicates(subset=["video_id"], keep="first")

    for col in ("impressions", "views_analytics"):
        if col in analytics_small.columns:
            analytics_small[col] = pd.to_numeric(analytics_small[col], errors="coerce").fillna(0.0)

    if "ctr" in analytics_small.columns:
        analytics_small["ctr"] = (
            analytics_small["ctr"]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.strip()
            .replace("", "0")
        )
        analytics_small["ctr"] = pd.to_numeric(analytics_small["ctr"], errors="coerce").fillna(0.0)

    merged = videos.merge(analytics_small, how="left", on="video_id")
    merged.to_csv(VIDEOS_ENRICHED_CSV, index=False)
    return VIDEOS_ENRICHED_CSV

