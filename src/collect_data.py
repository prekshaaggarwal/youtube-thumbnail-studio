from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import requests
from googleapiclient.discovery import build
from tqdm import tqdm

from src.config import THUMBNAIL_DIR, VIDEOS_CSV
from src.utils import ensure_dirs


def parse_duration_seconds(iso_duration: str) -> int:
    # Simple ISO 8601 parser for PT#H#M#S format
    iso_duration = iso_duration.replace("PT", "")
    hours, minutes, seconds = 0, 0, 0

    if "H" in iso_duration:
        parts = iso_duration.split("H")
        hours = int(parts[0] or 0)
        iso_duration = parts[1]
    if "M" in iso_duration:
        parts = iso_duration.split("M")
        minutes = int(parts[0] or 0)
        iso_duration = parts[1]
    if "S" in iso_duration:
        seconds = int(iso_duration.replace("S", "") or 0)
    return hours * 3600 + minutes * 60 + seconds


def _best_thumbnail_url(thumbnails: dict[str, Any]) -> str | None:
    for key in ("maxres", "standard", "high", "medium", "default"):
        item = thumbnails.get(key)
        if item and item.get("url"):
            return item["url"]
    return None


def _download_thumbnail(url: str, out_path: Path) -> None:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    out_path.write_bytes(response.content)


def _get_uploads_playlist_id(youtube: Any, channel_id: str) -> str:
    response = (
        youtube.channels()
        .list(part="contentDetails", id=channel_id, maxResults=1)
        .execute()
    )
    items = response.get("items", [])
    if not items:
        raise ValueError("No channel found for the given channel ID.")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _get_video_ids_from_playlist(
    youtube: Any, playlist_id: str, max_videos: int = 300
) -> list[str]:
    video_ids: list[str] = []
    next_page_token = None
    pbar = tqdm(total=max_videos, desc="Collecting video IDs")

    while len(video_ids) < max_videos:
        response = (
            youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token,
            )
            .execute()
        )

        items = response.get("items", [])
        if not items:
            break

        for item in items:
            if len(video_ids) >= max_videos:
                break
            video_ids.append(item["contentDetails"]["videoId"])
            pbar.update(1)

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    pbar.close()
    return video_ids


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _fetch_video_details(youtube: Any, video_ids: list[str]) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    for batch in tqdm(_chunked(video_ids, 50), desc="Fetching video details"):
        response = (
            youtube.videos()
            .list(
                part="snippet,statistics,contentDetails",
                id=",".join(batch),
                maxResults=50,
            )
            .execute()
        )
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            details = item.get("contentDetails", {})

            thumb_url = _best_thumbnail_url(snippet.get("thumbnails", {}))
            row = {
                "video_id": item.get("id", ""),
                "title": snippet.get("title", ""),
                "published_at": snippet.get("publishedAt", ""),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "duration_seconds": parse_duration_seconds(details.get("duration", "PT0S")),
                "thumbnail_url": thumb_url or "",
            }
            all_rows.append(row)
    return all_rows


def _save_rows(rows: list[dict[str, Any]], csv_path: Path) -> None:
    if not rows:
        raise ValueError("No videos found; cannot write CSV.")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def collect_channel_data(api_key: str, channel_id: str, max_videos: int = 300) -> None:
    ensure_dirs(THUMBNAIL_DIR, VIDEOS_CSV.parent)
    youtube = build("youtube", "v3", developerKey=api_key)

    uploads_id = _get_uploads_playlist_id(youtube, channel_id)
    video_ids = _get_video_ids_from_playlist(youtube, uploads_id, max_videos=max_videos)
    rows = _fetch_video_details(youtube, video_ids)

    for row in tqdm(rows, desc="Downloading thumbnails"):
        url = row.get("thumbnail_url", "")
        vid = row.get("video_id", "")
        if not url or not vid:
            row["thumbnail_path"] = ""
            continue
        out_path = THUMBNAIL_DIR / f"{vid}.jpg"
        try:
            _download_thumbnail(url, out_path)
            row["thumbnail_path"] = str(out_path.resolve())
        except Exception:
            row["thumbnail_path"] = ""

    _save_rows(rows, VIDEOS_CSV)

