"""
azure_blob_service.py — Azure Blob Storage SAS URL generation for lesson content viewing.

Generates time-limited Shared Access Signature (SAS) URLs for images, audio,
and video stored in Azure Blob Storage. Parses lesson_slides.slide_content JSON
and replaces relative blob paths with signed URLs.
"""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

DATABASE = "baap"
QUERY_TIMEOUT = 30

# Known blob path keys in slide_content JSON
BLOB_PATH_KEYS = {"background_image", "audio", "video", "thumbnail"}

# Pattern to detect relative blob paths (Image/..., Audio/..., Video/...)
BLOB_PATH_PATTERN = re.compile(r"^(Image|Audio|Video)/\S+\.\w{2,4}$")

# .env location
ENV_PATH = Path("/home/rahil/Projects/baap/.env")


def _load_env() -> dict[str, str]:
    """Load key=value pairs from the .env file."""
    env = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _mysql_query(sql: str) -> list[dict]:
    """Execute a read-only MySQL query, return list of row dicts."""
    result = subprocess.run(
        ["mysql", DATABASE, "--batch", "--raw", "-e", sql],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise Exception(f"MySQL error: {result.stderr.strip()}")
    output = result.stdout.strip()
    if not output:
        return []
    lines = output.split("\n")
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        rows.append({h: (values[i] if i < len(values) else None) for i, h in enumerate(headers)})
    return rows


class AzureBlobService:
    """Service for generating time-limited SAS URLs for Azure Blob Storage content."""

    def __init__(self):
        env = _load_env()

        self.account_name = env.get("AZURE_STORAGE_NAME", "")
        self.account_key = env.get("AZURE_STORAGE_KEY", "")
        self.account_url = env.get("AZURE_STORAGE_URL", "")
        self.connection_string = env.get("AZURE_STORAGE_CONNECTION_STRING", "")
        self.default_container = env.get("CONTAINER", "staging")

        if not self.account_name or not self.account_key:
            raise ValueError(
                "Missing AZURE_STORAGE_NAME or AZURE_STORAGE_KEY in .env. "
                f"Checked: {ENV_PATH}"
            )

        self._client = BlobServiceClient(
            account_url=self.account_url,
            credential=self.account_key,
        )

    def generate_sas_url(
        self,
        blob_path: str,
        container: str | None = None,
        expiry_hours: int = 1,
    ) -> str:
        """Generate a time-limited SAS URL for a blob.

        Args:
            blob_path: Relative path like "Image/20230912031906.jpg"
            container: Override container (default from env: staging)
            expiry_hours: How long the SAS token is valid (default 1 hour)

        Returns:
            Full URL with SAS token.
        """
        container = container or self.default_container

        sas_token = generate_blob_sas(
            account_name=self.account_name,
            container_name=container,
            blob_name=blob_path,
            account_key=self.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        )

        return f"{self.account_url.rstrip('/')}/{container}/{blob_path}?{sas_token}"

    def check_blob_exists(self, blob_path: str, container: str | None = None) -> bool:
        """Check if a blob exists in storage."""
        container = container or self.default_container
        try:
            blob_client = self._client.get_blob_client(container=container, blob=blob_path)
            blob_client.get_blob_properties()
            return True
        except Exception:
            return False

    def parse_slide_content(self, slide_content_json: str) -> dict | None:
        """Parse lesson_slides.slide_content JSON and replace blob paths with SAS URLs.

        Finds keys like background_image, audio, video, thumbnail and generates
        SAS URLs for each that matches the blob path pattern.
        """
        if not slide_content_json or slide_content_json == "NULL":
            return None
        try:
            data = json.loads(slide_content_json, strict=False)
        except (json.JSONDecodeError, TypeError):
            return None

        for key in BLOB_PATH_KEYS:
            val = data.get(key)
            if val and isinstance(val, str) and BLOB_PATH_PATTERN.match(val):
                try:
                    data[key] = self.generate_sas_url(val)
                except Exception:
                    data[key] = None

        return data

    def get_lesson_slides_with_urls(self, lesson_detail_id: int) -> list[dict]:
        """Fetch all slides for a lesson_detail_id, parse content, generate SAS URLs.

        Returns list of slide objects with type, parsed content (URLs resolved),
        priority, and video_library info if present.
        """
        lid = int(lesson_detail_id)

        # Use HEX() for slide_content to avoid TSV parsing issues with embedded newlines
        rows = _mysql_query(
            f"SELECT id, type, "
            f"HEX(slide_content) AS slide_content_hex, "
            f"video_library_id, priority "
            f"FROM lesson_slides "
            f"WHERE lesson_detail_id = {lid} AND deleted_at IS NULL "
            f"ORDER BY priority, id"
        )

        slides = []
        for row in rows:
            slide_id = row.get("id")
            if not slide_id or not slide_id.isdigit():
                continue

            # Decode hex-encoded slide_content back to original JSON
            hex_content = row.get("slide_content_hex")
            slide_content = None
            if hex_content and hex_content != "NULL":
                try:
                    slide_content = bytes.fromhex(hex_content).decode("utf-8")
                except (ValueError, UnicodeDecodeError):
                    slide_content = None

            parsed_content = self.parse_slide_content(slide_content)

            slide: dict[str, Any] = {
                "id": int(slide_id),
                "type": row.get("type"),
                "content": parsed_content,
                "priority": int(row["priority"]) if row.get("priority") and row["priority"].isdigit() else None,
            }

            # If there's a video_library reference, fetch video + thumbnail paths
            vid_lib_id = row.get("video_library_id")
            if vid_lib_id and vid_lib_id != "NULL" and vid_lib_id.isdigit():
                video_info = self._get_video_library(int(vid_lib_id))
                if video_info:
                    slide["video_library"] = video_info

            slides.append(slide)

        return slides

    def _get_video_library(self, video_library_id: int) -> dict | None:
        """Fetch video library entry and generate SAS URLs for video + thumbnail."""
        rows = _mysql_query(
            f"SELECT id, title, video, thumbnail, transcript "
            f"FROM video_libraries "
            f"WHERE id = {int(video_library_id)} AND deleted_at IS NULL "
            f"LIMIT 1"
        )
        if not rows:
            return None

        row = rows[0]
        video_path = row.get("video")
        thumb_path = row.get("thumbnail")

        video_url = None
        thumb_url = None

        if video_path and video_path != "NULL" and BLOB_PATH_PATTERN.match(video_path):
            try:
                video_url = self.generate_sas_url(video_path)
            except Exception:
                pass

        if thumb_path and thumb_path != "NULL" and BLOB_PATH_PATTERN.match(thumb_path):
            try:
                thumb_url = self.generate_sas_url(thumb_path)
            except Exception:
                pass

        return {
            "id": int(row["id"]),
            "title": row.get("title"),
            "video_url": video_url,
            "thumbnail_url": thumb_url,
            "transcript": row.get("transcript"),
        }
