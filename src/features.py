from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageFilter

from src.utils import days_since


def _safe_open_rgb(path: str) -> Image.Image | None:
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        return None


def _image_features(path: str) -> dict[str, float]:
    img = _safe_open_rgb(path)
    if img is None:
        return {
            "img_width": 0.0,
            "img_height": 0.0,
            "mean_r": 0.0,
            "mean_g": 0.0,
            "mean_b": 0.0,
            "brightness": 0.0,
            "contrast": 0.0,
            "color_std": 0.0,
            "edge_density": 0.0,
        }

    arr = np.asarray(img, dtype=np.float32)
    h, w, _ = arr.shape
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    gray = 0.299 * r + 0.587 * g + 0.114 * b

    # Edge proxy from high-pass effect
    edge_img = img.filter(ImageFilter.FIND_EDGES)
    edge_arr = np.asarray(edge_img.convert("L"), dtype=np.float32)
    edge_density = float((edge_arr > 40.0).mean())

    return {
        "img_width": float(w),
        "img_height": float(h),
        "mean_r": float(r.mean()),
        "mean_g": float(g.mean()),
        "mean_b": float(b.mean()),
        "brightness": float(gray.mean()),
        "contrast": float(gray.std()),
        "color_std": float(arr.std()),
        "edge_density": edge_density,
    }


def _relative_performance(row: pd.Series) -> float:
    views = float(row.get("view_count", 0))
    likes = float(row.get("like_count", 0))
    comments = float(row.get("comment_count", 0))
    published_at = str(row.get("published_at", ""))

    age_days = days_since(published_at) if published_at else 1.0
    engagement = likes + 2.0 * comments

    # Proxy score: view velocity + lightweight engagement boost
    score = math.log1p(views) / math.sqrt(age_days + 2.0) + 0.05 * math.log1p(engagement)
    return float(score)


def _real_world_performance(row: pd.Series) -> float:
    # Prefer Studio-like metrics when present: CTR + impressions + observed views.
    ctr = pd.to_numeric(pd.Series([row.get("ctr", 0)]), errors="coerce").fillna(0.0).iloc[0]
    impressions = (
        pd.to_numeric(pd.Series([row.get("impressions", 0)]), errors="coerce").fillna(0.0).iloc[0]
    )
    views_analytics = (
        pd.to_numeric(pd.Series([row.get("views_analytics", 0)]), errors="coerce")
        .fillna(0.0)
        .iloc[0]
    )

    if ctr > 0 and impressions > 0:
        est_clicks = (ctr / 100.0) * impressions
        return float(math.log1p(est_clicks) + 0.25 * math.log1p(views_analytics))
    return _relative_performance(row)


def build_training_frame(videos_df: pd.DataFrame) -> pd.DataFrame:
    df = videos_df.copy()
    df["title"] = df["title"].fillna("").astype(str)
    df["title_len"] = df["title"].str.len().astype(float)
    df["duration_seconds"] = pd.to_numeric(df["duration_seconds"], errors="coerce").fillna(0.0)

    image_rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        thumb_path = str(row.get("thumbnail_path", ""))
        if thumb_path and Path(thumb_path).exists():
            image_rows.append(_image_features(thumb_path))
        else:
            image_rows.append(_image_features(""))

    image_df = pd.DataFrame(image_rows)
    df = pd.concat([df.reset_index(drop=True), image_df.reset_index(drop=True)], axis=1)
    df["perf_score"] = df.apply(_real_world_performance, axis=1)

    threshold = df["perf_score"].quantile(0.60)
    df["target_good"] = (df["perf_score"] >= threshold).astype(int)
    return df

