from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
THUMBNAIL_DIR = DATA_RAW / "thumbnails"
UPLOAD_DIR = DATA_RAW / "uploads"
ARTIFACTS = ROOT / "artifacts"

VIDEOS_CSV = DATA_RAW / "videos.csv"
VIDEOS_ENRICHED_CSV = DATA_RAW / "videos_enriched.csv"
MODEL_PATH = ARTIFACTS / "model.joblib"
METRICS_PATH = ARTIFACTS / "metrics.json"
FEATURE_COLUMNS_PATH = ARTIFACTS / "feature_columns.json"

