from __future__ import annotations

import json
from typing import Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.config import (
    ARTIFACTS,
    FEATURE_COLUMNS_PATH,
    METRICS_PATH,
    MODEL_PATH,
    VIDEOS_CSV,
    VIDEOS_ENRICHED_CSV,
)
from src.features import build_training_frame
from src.utils import ensure_dirs


NUMERIC_COLS = [
    "title_len",
    "duration_seconds",
    "img_width",
    "img_height",
    "mean_r",
    "mean_g",
    "mean_b",
    "brightness",
    "contrast",
    "color_std",
    "edge_density",
]
TEXT_COL = "title"
TARGET_COL = "target_good"


def train() -> dict[str, Any]:
    ensure_dirs(ARTIFACTS)
    source_csv = VIDEOS_ENRICHED_CSV if VIDEOS_ENRICHED_CSV.exists() else VIDEOS_CSV
    if not source_csv.exists():
        raise FileNotFoundError("No dataset found. Run collect first.")

    raw_df = pd.read_csv(source_csv)
    df = build_training_frame(raw_df)

    if len(df) < 30:
        raise ValueError("Not enough data. Collect at least 30+ videos to train.")
    if df[TARGET_COL].nunique() < 2:
        raise ValueError(
            "Training data has only one target class. Add more varied historical data before training."
        )

    # Temporal split: train on older videos, test on newest ones.
    # This better approximates real future thumbnail decisions.
    df = df.sort_values("published_at").reset_index(drop=True)
    split_idx = max(int(len(df) * 0.8), 1)
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:] if split_idx < len(df) else df.iloc[-1:]

    # Fallback if temporal split collapses to one class in train/test.
    if train_df[TARGET_COL].nunique() < 2 or test_df[TARGET_COL].nunique() < 1:
        train_df, test_df = train_test_split(
            df,
            test_size=0.2,
            random_state=42,
            stratify=df[TARGET_COL],
        )

    X_train = train_df[NUMERIC_COLS + [TEXT_COL]]
    y_train = train_df[TARGET_COL]
    X_test = test_df[NUMERIC_COLS + [TEXT_COL]]
    y_test = test_df[TARGET_COL]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_COLS),
            ("txt", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=3000), TEXT_COL),
        ]
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            # LogisticRegression supports sparse matrices from TF-IDF.
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)),
        ]
    )

    pipeline.fit(X_train, y_train)
    proba = pipeline.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)

    metrics = {
        "samples": int(len(df)),
        "positive_rate": float(df[TARGET_COL].mean()),
        "data_source": str(source_csv),
        "accuracy": float(accuracy_score(y_test, pred)),
        "f1": float(f1_score(y_test, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, proba)) if len(set(y_test)) > 1 else 0.0,
    }

    joblib.dump(pipeline, MODEL_PATH)
    FEATURE_COLUMNS_PATH.write_text(
        json.dumps({"numeric": NUMERIC_COLS, "text": TEXT_COL, "target": TARGET_COL}, indent=2),
        encoding="utf-8",
    )
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics

