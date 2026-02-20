"""
azure_blob_service.py — Azure Blob Storage SAS URL generation for lesson content viewing.

Generates time-limited Shared Access Signature (SAS) URLs for images, audio,
and video stored in Azure Blob Storage. Parses lesson_slides.slide_content JSON
and replaces relative blob paths with signed URLs.

Includes a dynamic blob inventory that caches the Azure listing in memory (1h TTL)
to resolve video slides whose video_library DB records are missing from the dump.
"""

import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

log = logging.getLogger(__name__)

DATABASE = "baap"
QUERY_TIMEOUT = 30
BLOB_INVENTORY_TTL = 3600  # 1 hour cache

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


def _decode_unicode_literals(obj):
    """Recursively decode bare Unicode escape sequences in string values.

    The DB stores sequences like 'u2019' (missing backslash prefix) that
    json.loads treats as literal text. This converts them to actual characters:
      doesnu2019t → doesn't
      u201cHellou201d → "Hello"
    """
    _UNICODE_BARE = re.compile(r'u([0-9a-fA-F]{4})')

    def _decode_str(s: str) -> str:
        return _UNICODE_BARE.sub(lambda m: chr(int(m.group(1), 16)), s)

    if isinstance(obj, str):
        return _decode_str(obj)
    if isinstance(obj, dict):
        return {k: _decode_unicode_literals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_unicode_literals(item) for item in obj]
    return obj


def _repair_json_quotes(s: str) -> str:
    """Fix unescaped double quotes inside JSON string values.

    16% of lesson_slides.slide_content has patterns like:
      "message":"Select "Seen It" or "Used It""
    where inner quotes are not escaped. This function uses a state machine
    to detect inner quotes (those not followed by JSON structural chars)
    and escapes them.
    """
    result = []
    i = 0
    in_string = False
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\' and in_string:
            result.append(c)
            i += 1
            if i < n:
                result.append(s[i])
            i += 1
            continue
        if c == '"':
            if not in_string:
                in_string = True
                result.append(c)
            else:
                # Check if this quote ends the string: must be followed by
                # a JSON structural char (:, ,, }, ]) after optional whitespace
                j = i + 1
                while j < n and s[j] in ' \t\r\n':
                    j += 1
                if j >= n or s[j] in ':,}]':
                    in_string = False
                    result.append(c)
                else:
                    result.append('\\"')
            i += 1
            continue
        result.append(c)
        i += 1
    return ''.join(result)


def _extract_blob_timestamp(name: str) -> str | None:
    """Extract 14-digit timestamp from blob filename.

    Handles both raw blob paths (Video/6/production...-20250912133424.mp4)
    and full SAS URLs (where the sig= parameter may contain literal / chars).
    """
    # Strip query string first — SAS signatures contain / that break path splitting
    path = name.split('?')[0]
    m = re.search(r'(\d{14})', path.split('/')[-1])
    return m.group(1) if m else None


def _extract_blob_coach(name: str) -> int | None:
    """Extract coach ID from blob path (Video/{coach_id}/...)."""
    m = re.match(r'Video/(\d+)/', name)
    return int(m.group(1)) if m else None


def _extract_blob_keywords(name: str) -> str:
    """Extract searchable keywords from blob filename."""
    fname = name.split('/')[-1]
    cleaned = re.sub(r'-?\d{14}\.\w+$', '', fname)
    cleaned = re.sub(r'^(App-|production-?)', '', cleaned)
    return cleaned.lower().replace('-', ' ').strip()


class AzureBlobService:
    """Service for generating time-limited SAS URLs for Azure Blob Storage content.

    Includes a dynamic blob inventory that caches the Azure Video/ listing
    to serve videos whose video_library DB records are missing.
    """

    # Class-level cache shared across instances (singleton-like for the inventory)
    _inventory: dict | None = None
    _inventory_expires: float = 0

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

    def _resolve_container(self, blob_path: str) -> str:
        """Find which container has the blob. Tries default first, then production fallback."""
        if self.check_blob_exists(blob_path, self.default_container):
            return self.default_container
        if self.default_container != "production" and self.check_blob_exists(blob_path, "production"):
            return "production"
        return self.default_container

    # ── Dynamic Blob Inventory ──

    def _get_blob_inventory(self) -> dict:
        """Return cached blob inventory, refreshing from Azure if stale.

        Inventory structure:
            videos: list[dict] sorted chronologically (path, ts, size, coach, keywords)
            thumbs: dict[timestamp → blob_path]
            keyword_index: dict[word → list[video_entry]]
        """
        now = time.time()
        if AzureBlobService._inventory and now < AzureBlobService._inventory_expires:
            return AzureBlobService._inventory

        log.info("Building blob inventory from Azure production container...")
        try:
            cc = self._client.get_container_client("production")
            all_blobs = list(cc.list_blobs(name_starts_with="Video/"))
        except Exception as e:
            log.error("Failed to list Azure blobs: %s", e)
            return {"videos": [], "thumbs": {}, "keyword_index": {}}

        videos = []
        thumbs = {}
        keyword_index: dict[str, list] = {}

        for b in all_blobs:
            if b.name.endswith(".mp4"):
                ts = _extract_blob_timestamp(b.name)
                coach = _extract_blob_coach(b.name)
                keywords = _extract_blob_keywords(b.name)
                entry = {
                    "path": b.name,
                    "ts": ts or "",
                    "size": b.size,
                    "coach": coach,
                    "keywords": keywords,
                }
                videos.append(entry)
                for word in keywords.split():
                    if len(word) >= 3:
                        keyword_index.setdefault(word, []).append(entry)
            elif "Thumbnail" in b.name:
                ts = _extract_blob_timestamp(b.name)
                if ts:
                    thumbs[ts] = b.name

        videos.sort(key=lambda v: v["ts"])

        inventory = {
            "videos": videos,
            "thumbs": thumbs,
            "keyword_index": keyword_index,
        }
        AzureBlobService._inventory = inventory
        AzureBlobService._inventory_expires = now + BLOB_INVENTORY_TTL
        log.info("Blob inventory built: %d videos, %d thumbnails", len(videos), len(thumbs))
        return inventory

    def _find_thumbnail(self, video_ts: str, inventory: dict) -> str | None:
        """Find thumbnail blob for a video by matching timestamps (±2 seconds)."""
        thumbs = inventory["thumbs"]
        t = int(video_ts)
        for delta in (0, 1, -1, 2, -2):
            candidate = str(t + delta)
            if candidate in thumbs:
                return thumbs[candidate]
        return None

    def _find_video_in_inventory(
        self, video_library_id: int, slide_title: str | None = None
    ) -> dict | None:
        """Find a video blob for a missing video_library DB record.

        Uses multiple matching signals:
        1. Keyword matching (slide_title words vs blob filename keywords)
        2. Chronological proximity to known anchors
        3. Coach-based filtering

        Returns dict with video_url, thumbnail_url, title (or None).
        IMPORTANT: Never modifies Azure blobs — read-only access.
        """
        inventory = self._get_blob_inventory()
        if not inventory["videos"]:
            return None

        videos = inventory["videos"]

        # Find anchor position for chronological estimation
        ANCHOR_ID = 163
        ANCHOR_TS = "20250912133424"
        anchor_pos = next((i for i, v in enumerate(videos) if v["ts"] == ANCHOR_TS), None)

        best_match = None
        best_score = -1.0

        # Compute per-blob score combining keyword match + chronological proximity
        title_words = set()
        if slide_title:
            title_words = set(re.findall(r"[a-z]{3,}", slide_title.lower()))
            title_words -= {"the", "and", "for", "with", "your", "you", "that", "this", "from", "are", "was", "has", "its"}

        for i, video in enumerate(videos):
            kw = video["keywords"]
            # Skip obvious test uploads
            if any(t in kw for t in ("test", "tet", "videotest")):
                continue

            score = 0.0

            # Signal 1: Keyword prefix matching (blob filenames truncate to ~10 chars)
            if title_words:
                kw_words = set(kw.split())
                for tw in title_words:
                    for kww in kw_words:
                        if tw.startswith(kww) or kww.startswith(tw):
                            match_len = min(len(tw), len(kww))
                            score += 2.0 + match_len / 10

            # Signal 2: Chronological proximity to estimated position
            if anchor_pos is not None:
                estimated_pos = anchor_pos - (ANCHOR_ID - video_library_id)
                distance = abs(i - estimated_pos)
                # Proximity bonus: max 1.5 at exact position, decays with distance
                if distance <= 15:
                    score += max(0, 1.5 - distance * 0.1)

            if score > best_score:
                best_score = score
                best_match = video

        if not best_match:
            return None

        # Generate SAS URLs
        video_url = None
        thumb_url = None
        try:
            video_url = self.generate_sas_url(best_match["path"], container="production")
        except Exception:
            return None

        if best_match["ts"]:
            thumb_path = self._find_thumbnail(best_match["ts"], inventory)
            if thumb_path:
                try:
                    thumb_url = self.generate_sas_url(thumb_path, container="production")
                except Exception:
                    pass

        # Derive title from blob filename
        title = _extract_blob_keywords(best_match["path"]).replace(" ", " ").title()

        return {
            "id": video_library_id,
            "title": title,
            "video_url": video_url,
            "thumbnail_url": thumb_url,
            "transcript": None,  # no transcript without DB record
            "source": "blob_inventory",
        }

    def _resolve_blob_urls(self, obj):
        """Recursively walk JSON and replace any blob path string with a SAS URL.

        Handles nested structures like imageExamples[].background_image,
        stakeholders[].image, etc. — not just top-level keys.
        """
        if isinstance(obj, str):
            if BLOB_PATH_PATTERN.match(obj):
                try:
                    container = self._resolve_container(obj)
                    return self.generate_sas_url(obj, container=container)
                except Exception:
                    return None
            return obj
        if isinstance(obj, dict):
            return {k: self._resolve_blob_urls(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve_blob_urls(item) for item in obj]
        return obj

    def parse_slide_content(self, slide_content_json: str) -> dict | None:
        """Parse lesson_slides.slide_content JSON and replace blob paths with SAS URLs.

        Recursively walks the entire JSON tree to resolve blob paths at any depth:
        top-level (background_image, audio), nested arrays (imageExamples[].image),
        and deeply nested objects (stakeholders[].image).
        """
        if not slide_content_json or slide_content_json == "NULL":
            return None
        try:
            data = json.loads(slide_content_json, strict=False)
        except (json.JSONDecodeError, TypeError):
            # 16% of slides have unescaped quotes inside JSON strings — try repair
            try:
                repaired = _repair_json_quotes(slide_content_json)
                data = json.loads(repaired, strict=False)
            except (json.JSONDecodeError, TypeError, ValueError):
                return None

        # Decode bare Unicode sequences (u2019 → ', u201c → ", etc.)
        data = _decode_unicode_literals(data)

        # Recursively resolve all blob paths to SAS URLs
        data = self._resolve_blob_urls(data)

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
                slide["_vlib_id"] = int(vid_lib_id)
                slide_title = None
                if parsed_content and isinstance(parsed_content, dict):
                    slide_title = parsed_content.get("slide_title")
                slide["_slide_title"] = slide_title

                # Primary: DB lookup
                video_info = self._get_video_library(int(vid_lib_id), slide_title=slide_title)
                if video_info:
                    slide["video_library"] = video_info

            slides.append(slide)

        # Group matching pass: for unresolved video slides, use nearby resolved blobs
        self._resolve_video_group(slides)

        # Clean up internal keys
        for slide in slides:
            slide.pop("_vlib_id", None)
            slide.pop("_slide_title", None)

        return slides

    def _resolve_video_group(self, slides: list[dict]) -> None:
        """Second pass: resolve unmatched video slides using nearby matched ones.

        Within a lesson, videos are uploaded in sequence. If vlib=163 resolved to
        blob at timestamp T, vlib=162 should be the blob just before T with the
        same filename prefix or from the same upload session.
        """
        inventory = self._get_blob_inventory()
        if not inventory["videos"]:
            return

        # Find anchor: a slide with a resolved DB-sourced video_library
        anchor_blob_ts = None
        anchor_vlib_id = None
        for slide in slides:
            vl = slide.get("video_library")
            if vl and vl.get("source") == "database" and vl.get("video_url"):
                # Extract timestamp from the video URL path
                url = vl["video_url"]
                ts = _extract_blob_timestamp(url)
                if ts:
                    anchor_blob_ts = ts
                    anchor_vlib_id = slide.get("_vlib_id")
                    break

        if not anchor_blob_ts or not anchor_vlib_id:
            return  # No anchor — individual matching is all we have

        # Find anchor position in sorted video list
        anchor_pos = None
        for i, v in enumerate(inventory["videos"]):
            if v["ts"] == anchor_blob_ts:
                anchor_pos = i
                break
        if anchor_pos is None:
            return

        log.debug("Video group matching: anchor vlib=%s at pos %d/%d", anchor_vlib_id, anchor_pos, len(inventory["videos"]))

        # For each unmatched or inventory-matched video slide, try group-based resolution
        for slide in slides:
            vlib_id = slide.get("_vlib_id")
            vl = slide.get("video_library")
            if not vlib_id:
                continue
            # Skip slides that already have DB-sourced data
            if vl and vl.get("source") == "database":
                continue

            # Calculate expected offset from anchor
            id_offset = anchor_vlib_id - vlib_id  # positive = this ID is before anchor
            target_pos = anchor_pos - id_offset
            log.debug("Video group: vlib=%s target_pos=%d", vlib_id, target_pos)

            # Search ±3 positions around target
            best = None
            best_dist = 999
            for i in range(max(0, target_pos - 3), min(len(inventory["videos"]), target_pos + 4)):
                v = inventory["videos"][i]
                # Skip test blobs
                if any(t in v["keywords"] for t in ("test", "tet", "videotest")):
                    continue
                dist = abs(i - target_pos)
                if dist < best_dist:
                    best_dist = dist
                    best = v

            if best:
                log.debug("Video group: vlib=%s → %s", vlib_id, best["path"])
                video_url = None
                thumb_url = None
                try:
                    video_url = self.generate_sas_url(best["path"], container="production")
                except Exception:
                    continue
                if best["ts"]:
                    thumb_path = self._find_thumbnail(best["ts"], inventory)
                    if thumb_path:
                        try:
                            thumb_url = self.generate_sas_url(thumb_path, container="production")
                        except Exception:
                            pass

                title = _extract_blob_keywords(best["path"]).replace(" ", " ").title()
                slide["video_library"] = {
                    "id": vlib_id,
                    "title": title,
                    "video_url": video_url,
                    "thumbnail_url": thumb_url,
                    "transcript": None,
                    "source": "blob_inventory",
                }
            else:
                log.debug("Video group: vlib=%s no match near pos %d", vlib_id, target_pos)

    def _get_video_library(self, video_library_id: int, slide_title: str | None = None) -> dict | None:
        """Fetch video library entry and generate SAS URLs for video + thumbnail.

        Falls back to dynamic blob inventory when DB record is missing (100/101 IDs
        lost from DB dump). The inventory scans Azure production container and matches
        blobs by keyword + chronological position.
        """
        vid = int(video_library_id)

        # Primary: DB lookup
        rows = _mysql_query(
            f"SELECT id, title, video, thumbnail, transcript "
            f"FROM video_libraries "
            f"WHERE id = {vid} AND deleted_at IS NULL "
            f"LIMIT 1"
        )
        if rows:
            row = rows[0]
            video_path = row.get("video")
            thumb_path = row.get("thumbnail")

            video_url = None
            thumb_url = None

            if video_path and video_path != "NULL" and BLOB_PATH_PATTERN.match(video_path):
                try:
                    container = self._resolve_container(video_path)
                    video_url = self.generate_sas_url(video_path, container=container)
                except Exception:
                    pass

            if thumb_path and thumb_path != "NULL" and BLOB_PATH_PATTERN.match(thumb_path):
                try:
                    container = self._resolve_container(thumb_path)
                    thumb_url = self.generate_sas_url(thumb_path, container=container)
                except Exception:
                    pass

            return {
                "id": vid,
                "title": row.get("title"),
                "video_url": video_url,
                "thumbnail_url": thumb_url,
                "transcript": row.get("transcript"),
                "source": "database",
            }

        # Fallback: dynamic blob inventory
        return self._find_video_in_inventory(vid, slide_title=slide_title)
