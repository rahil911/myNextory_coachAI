"""
attachment_service.py — File upload storage with metadata index.
"""

import json
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import ATTACHMENTS_DIR
from models import Attachment


INDEX_FILE = ATTACHMENTS_DIR / "_index.json"


class AttachmentService:
    def __init__(self):
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        self._index = self._load_index()

    def _load_index(self) -> dict[str, dict]:
        if INDEX_FILE.exists():
            try:
                return json.loads(INDEX_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_index(self) -> None:
        INDEX_FILE.write_text(json.dumps(self._index, indent=2))

    def save(self, filename: str, content: bytes, bead_id: str | None = None) -> Attachment:
        """Save an uploaded file and return its metadata."""
        att_id = f"att_{uuid.uuid4().hex[:12]}"
        ext = Path(filename).suffix or ".bin"
        stored_name = f"{att_id}{ext}"
        file_path = ATTACHMENTS_DIR / stored_name

        file_path.write_bytes(content)

        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        attachment = Attachment(
            id=att_id,
            filename=filename,
            mime_type=mime,
            size_bytes=len(content),
            bead_id=bead_id,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
            path=stored_name,
        )

        self._index[att_id] = attachment.model_dump()
        self._save_index()

        return attachment

    def get(self, att_id: str) -> Attachment | None:
        """Get attachment metadata by ID."""
        data = self._index.get(att_id)
        if data:
            return Attachment(**data)
        return None

    def get_file_path(self, att_id: str) -> Path | None:
        """Get the full filesystem path for an attachment."""
        data = self._index.get(att_id)
        if data:
            return ATTACHMENTS_DIR / data["path"]
        return None

    def list_all(self, bead_id: str | None = None) -> list[Attachment]:
        """List all attachments, optionally filtered by bead."""
        attachments = [Attachment(**d) for d in self._index.values()]
        if bead_id:
            attachments = [a for a in attachments if a.bead_id == bead_id]
        return sorted(attachments, key=lambda a: a.uploaded_at, reverse=True)

    def delete(self, att_id: str) -> bool:
        """Delete an attachment file and its metadata."""
        data = self._index.pop(att_id, None)
        if data:
            file_path = ATTACHMENTS_DIR / data["path"]
            if file_path.exists():
                file_path.unlink()
            self._save_index()
            return True
        return False
