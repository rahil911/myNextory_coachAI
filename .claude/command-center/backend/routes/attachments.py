"""
routes/attachments.py — File upload and download.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from models import Attachment, AttachmentListResponse

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


def _get_attachment_service():
    from main import get_attachment_service
    return get_attachment_service()


@router.post("", response_model=Attachment)
async def upload_attachment(
    file: UploadFile = File(...),
    bead_id: str | None = Form(None),
):
    """Upload a file (screenshot paste, drag-drop)."""
    svc = _get_attachment_service()
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    return svc.save(file.filename or "upload", content, bead_id=bead_id)


@router.get("/{att_id}")
async def get_attachment(att_id: str):
    """Serve an attachment file."""
    svc = _get_attachment_service()
    att = svc.get(att_id)
    if not att:
        raise HTTPException(status_code=404, detail=f"Attachment '{att_id}' not found")
    file_path = svc.get_file_path(att_id)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(path=str(file_path), media_type=att.mime_type, filename=att.filename)


@router.get("", response_model=AttachmentListResponse)
async def list_attachments(bead_id: str | None = None):
    """List all attachments."""
    svc = _get_attachment_service()
    attachments = svc.list_all(bead_id=bead_id)
    return AttachmentListResponse(attachments=attachments, count=len(attachments))
