# Azure Blob SAS Service Analysis
> Agent: a3a463a | Date: 2026-02-20 | Source: azure_blob_service.py + DB cross-reference

## Service Configuration

**Code Location:** `.claude/command-center/backend/services/azure_blob_service.py`

| Parameter | Value |
|-----------|-------|
| Storage Account | `productionmynextory` |
| Primary Container | `staging` (from CONTAINER env var) |
| Access Credentials | `AZURE_STORAGE_KEY` + `AZURE_STORAGE_NAME` |
| Account URL | `https://productionmynextory.blob.core.windows.net` |
| SAS Token Expiry | 1 hour (default, configurable) |
| Permission Mode | `BlobSasPermissions(read=True)` |

## SAS URL Generation

**Function:** `AzureBlobService.generate_sas_url(blob_path, container=None, expiry_hours=1)`

**Output Format:**
```
https://productionmynextory.blob.core.windows.net/{container}/{blob_path}?{sas_token}
```

**Known Blob Path Keys in slide_content JSON:**
- `background_image` - Static background image
- `audio` - Lesson narration audio
- `video` - Video content reference
- `thumbnail` - Video thumbnail image

**Blob Path Detection Pattern:** `^(Image|Audio|Video|BonusMaterial)/\S+\.\w{2,4}$`

## Media Distribution

| Type | Count | % |
|------|-------|---|
| Image | 150 | 74.3% |
| Audio | 51 | 25.2% |
| BonusMaterial | 1 | 0.5% |
| **TOTAL** | **202** | **100%** |

## File Extensions

| Extension | Count |
|-----------|-------|
| `.jpg` | 95 |
| `.png` | 52 |
| `.mp3` | 51 |
| `.webp` | 3 |
| `.pdf` | 1 |

## Storage Path Patterns

```
staging/
  ├── Image/
  │   ├── {YYYYMMDDHHMMSS}.jpg
  │   ├── {YYYYMMDDHHMMSS}.png
  │   ├── {YYYYMMDDHHMMSS}.webp
  │   └── stakeholder{N}{YYYYMMDDHHMMSS}.png
  ├── Audio/
  │   └── {YYYYMMDDHHMMSS}.mp3
  ├── Video/
  │   ├── {coach_id}/production{name}-{YYYYMMDDHHMMSS}.mp4
  │   └── Thumbnail/Thumbnail-{coach_id}-{YYYYMMDDHHMMSS}.png
  └── BonusMaterial/
      └── Document/{YYYYMMDDHHMMSS}.pdf
```

## Lesson Media Density

**Total Slides:** 1,290
**Slides with Media:** 115 (8.9%)
**Slides Text-Only:** 1,175 (91.1%)

**Top Lessons by Media:**

| Lesson ID | Unique Blobs | Total Slides |
|-----------|-------------|-------------|
| 34 | 15 | 3 |
| 18 | 12 | 29 |
| 85 | 11 | 15 |
| 61 | 10 | 11 |
| 118 | 10 | 10 |
| 88 | 9 | 13 |
| 8 | 8 | 13 |

## Video Libraries Status

- 3 rows total, 1 active (id=163)
- Active: "Reading the Room Video 2" → `Video/6/productionreading-th-20250912133424.mp4`
- 100+ video_library_ids referenced by slides but missing from DB table

## Security Model

- SAS tokens are read-only (no write/delete)
- 1-hour expiry per token
- HMAC-SHA256 signed URLs (tamper-proof)
- No public access — all blobs require valid SAS
