from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from src.config import METRICS_PATH, MODEL_PATH
from src.features import _image_features


def _confidence_from_proba(proba: float) -> str:
    if proba >= 0.70:
        return "high"
    if proba >= 0.55:
        return "medium"
    return "low"


def _factor_insights(title: str, duration_seconds: int, img_feats: dict[str, float]) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    brightness = float(img_feats.get("brightness", 0.0))
    contrast = float(img_feats.get("contrast", 0.0))
    edge_density = float(img_feats.get("edge_density", 0.0))
    title_len = float(len(title or ""))
    duration = float(max(duration_seconds, 0))

    if 80 <= brightness <= 185:
        insights.append({"kind": "positive", "text": "Brightness is in a strong range for feed visibility."})
    else:
        insights.append({"kind": "negative", "text": "Brightness may be too dark or too washed out."})

    if contrast >= 40:
        insights.append({"kind": "positive", "text": "Contrast is high enough to separate key elements."})
    else:
        insights.append({"kind": "negative", "text": "Low contrast can reduce scroll-stopping effect."})

    if 0.03 <= edge_density <= 0.25:
        insights.append({"kind": "positive", "text": "Detail density looks balanced (not too flat/noisy)."})
    else:
        insights.append({"kind": "negative", "text": "Visual complexity may be too low or too cluttered."})

    if 30 <= title_len <= 70:
        insights.append({"kind": "positive", "text": "Title length is in a generally effective range."})
    else:
        insights.append({"kind": "negative", "text": "Title length may be suboptimal for click intent."})

    if duration <= 0:
        insights.append({"kind": "neutral", "text": "Duration missing; score uses image/title only."})
    elif 120 <= duration <= 1200:
        insights.append({"kind": "positive", "text": "Duration aligns with common high-retention windows."})
    else:
        insights.append({"kind": "neutral", "text": "Duration is outside common window; impact varies by niche."})

    return insights


def _global_baseline_score(title: str, duration_seconds: int, img_feats: dict[str, float]) -> float:
    # Channel-agnostic baseline so new users can still get usable output.
    brightness = float(img_feats.get("brightness", 0.0))
    contrast = float(img_feats.get("contrast", 0.0))
    edge_density = float(img_feats.get("edge_density", 0.0))
    title_len = float(len(title or ""))
    duration = float(max(duration_seconds, 0))

    score = 0.50
    if 80 <= brightness <= 185:
        score += 0.05
    if contrast >= 40:
        score += 0.06
    if 0.03 <= edge_density <= 0.25:
        score += 0.04
    if 30 <= title_len <= 70:
        score += 0.05
    if 120 <= duration <= 1200:
        score += 0.03

    return max(0.05, min(0.95, score))


def _channel_weight() -> float:
    if not METRICS_PATH.exists():
        return 0.0
    try:
        metrics = pd.read_json(METRICS_PATH, typ="series")
        samples = float(metrics.get("samples", 0))
        # Gradually trust personalized model more as data grows.
        return max(0.0, min(0.8, samples / 500.0))
    except Exception:
        return 0.0


def _predict_with_model(row: dict[str, Any]) -> float | None:
    if not MODEL_PATH.exists():
        return None
    try:
        model = joblib.load(MODEL_PATH)
        X = pd.DataFrame([row])
        return float(model.predict_proba(X)[:, 1][0])
    except Exception:
        return None


def predict_thumbnail(image_path: str, title: str = "", duration_seconds: int = 0) -> dict[str, Any]:
    image_path_obj = Path(image_path)
    if not image_path_obj.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    img_feats = _image_features(str(image_path_obj))
    row = {
        "title": title or "",
        "title_len": float(len(title or "")),
        "duration_seconds": float(duration_seconds),
        **img_feats,
    }

    base_proba = _global_baseline_score(title=title, duration_seconds=duration_seconds, img_feats=img_feats)
    channel_proba = _predict_with_model(row)
    weight = _channel_weight() if channel_proba is not None else 0.0
    proba = (1.0 - weight) * base_proba + weight * float(channel_proba or 0.0)
    confidence = _confidence_from_proba(proba)
    insights = _factor_insights(title=title, duration_seconds=duration_seconds, img_feats=img_feats)

    return {
        "probability_good": round(proba, 4),
        "verdict": "likely_good" if proba >= 0.60 else "likely_weak",
        "confidence": confidence,
        "model_mode": "hybrid" if channel_proba is not None else "global_baseline",
        "channel_model_weight": round(weight, 3),
        "insights": insights,
        "features": {
            "brightness": round(float(img_feats.get("brightness", 0.0)), 1),
            "contrast": round(float(img_feats.get("contrast", 0.0)), 1),
            "edge_density": round(float(img_feats.get("edge_density", 0.0)), 3),
            "title_length": int(len(title or "")),
        },
    }


def compare_thumbnails(
    current_image_path: str,
    candidate_image_path: str,
    title: str = "",
    duration_seconds: int = 0,
) -> dict[str, Any]:
    current = predict_thumbnail(current_image_path, title=title, duration_seconds=duration_seconds)
    candidate = predict_thumbnail(candidate_image_path, title=title, duration_seconds=duration_seconds)

    delta = round(candidate["probability_good"] - current["probability_good"], 4)
    recommendation = "use_candidate" if delta >= 0.03 else "keep_current"

    return {
        "current": current,
        "candidate": candidate,
        "probability_delta": delta,
        "recommendation": recommendation,
    }

