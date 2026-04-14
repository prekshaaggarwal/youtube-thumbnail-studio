from __future__ import annotations

import argparse
import json

from src.analytics import merge_analytics_csv
from src.collect_data import collect_channel_data
from src.predict import compare_thumbnails, predict_thumbnail
from src.train_model import train
from src.utils import get_api_key


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YouTube thumbnail performance analyzer")
    sub = parser.add_subparsers(dest="command", required=True)

    collect_parser = sub.add_parser("collect", help="Collect historical video data from channel")
    collect_parser.add_argument("--channel-id", required=True, help="YouTube channel ID")
    collect_parser.add_argument("--api-key", default=None, help="YouTube Data API key")
    collect_parser.add_argument("--max-videos", type=int, default=300)

    enrich_parser = sub.add_parser(
        "enrich",
        help="Merge YouTube Studio analytics CSV (CTR/impressions) into dataset",
    )
    enrich_parser.add_argument("--analytics-csv", required=True, help="Path to Studio export CSV")

    sub.add_parser("train", help="Train thumbnail performance model")

    predict_parser = sub.add_parser("predict", help="Predict new thumbnail performance")
    predict_parser.add_argument("--image", required=True, help="Path to thumbnail image")
    predict_parser.add_argument("--title", default="", help="Video title for the new thumbnail")
    predict_parser.add_argument("--duration-seconds", type=int, default=0)

    compare_parser = sub.add_parser("compare", help="Compare current vs candidate thumbnail")
    compare_parser.add_argument("--current-image", required=True)
    compare_parser.add_argument("--candidate-image", required=True)
    compare_parser.add_argument("--title", default="", help="Video title for context")
    compare_parser.add_argument("--duration-seconds", type=int, default=0)

    return parser


def main() -> None:
    parser = make_parser()
    args = parser.parse_args()

    if args.command == "collect":
        api_key = get_api_key(args.api_key)
        collect_channel_data(api_key=api_key, channel_id=args.channel_id, max_videos=args.max_videos)
        print("Collection complete. Dataset saved to data/raw/videos.csv")
    elif args.command == "enrich":
        out_path = merge_analytics_csv(args.analytics_csv)
        print(f"Enriched dataset created: {out_path}")
    elif args.command == "train":
        metrics = train()
        print("Training complete.")
        print(json.dumps(metrics, indent=2))
    elif args.command == "predict":
        result = predict_thumbnail(
            image_path=args.image,
            title=args.title,
            duration_seconds=args.duration_seconds,
        )
        print(json.dumps(result, indent=2))
    elif args.command == "compare":
        result = compare_thumbnails(
            current_image_path=args.current_image,
            candidate_image_path=args.candidate_image,
            title=args.title,
            duration_seconds=args.duration_seconds,
        )
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

