# Azure Blob Storage Inventory Report
> Agent: a7a7939 | Date: 2026-02-20 | Source: Azure Blob API + lesson_slides cross-reference

## Account Details
```
Account:   productionmynextory
URL:       https://productionmynextory.blob.core.windows.net/
```

---

## 1. Container Overview

| Container | Blobs | Size | Purpose |
|-----------|-------|------|---------|
| **staging** | 930 | 6.42 GB | **App's configured container** (.env CONTAINER=staging) |
| **production** | 1,332 | 4.57 GB | Production content (superset of newer content) |
| **dev** | 302 | 2.50 GB | Development environment |
| **demo** | 317 | 3.31 GB | Demo environment |
| **staging-production** | 54 | 124.8 MB | Staging-to-production transition? |
| **static** | 81 | 15.9 MB | Static assets |
| **media-kind** | 295 | 5.93 GB | MediaKind video platform integration |
| **db-copy** | thousands | small | Azure Data Factory copy activity logs |
| **asset-*** (645 containers) | varies | varies | Per-asset containers (UUID-named) |

Total named containers: 8 + 645 asset containers = **653 containers**

---

## 2. Staging Container Breakdown (Primary)

```
Container: staging
Total: 930 blobs, 6.42 GB
Date range: 2023-09-12 to 2026-01-09
```

| Folder | Files | Size | Types | Date Range |
|--------|-------|------|-------|------------|
| **Image/** | 262 | 114.8 MB | png:136, jpg:103, jpeg:23 | 2023-09-12 to 2026-01-09 |
| **Audio/** | 67 | 46.1 MB | mp3:67 | 2023-09-12 to 2026-01-09 |
| **Video/** | 271 | 3,916.8 MB | mp4:165, jpg:84, png:16, jpeg:6 | 2024-08-20 to 2026-01-09 |
| **Video-Old/** | 165 | 2,471.2 MB | mp4:85, jpg:72, png:8 | 2024-08-20 (single day) |
| **ChatBot/** | 107 | 9.2 MB | pdf:106, json:1 | 2024-11-12 to 2026-01-09 |
| **Uploads/** | 50 | 5.3 MB | pdf:50 | 2024-12-18 to 2025-03-19 |
| **chatgpt/** | 5 | 5.3 MB | pdf:4, png:1 | 2024-08-29 |
| **BonusMaterial/** | 1 | 3.1 MB | mp3:1 | 2025-12-30 |
| **staging/** | 2 | 0.2 MB | jpg:2 | 2025-12-02 |

### Video/ Subfolders (Staging)
```
Video/1/         - 137 mp4 files, 3,435.4 MB  (original app videos)
Video/4/         - 3 mp4 files, 34.1 MB
Video/6/         - 25 mp4 files, 430.6 MB      (production-prefixed videos)
Video/Thumbnail/ - 106 thumbnails (90 jpg + 16 png), 16.8 MB
```

---

## 3. Production Container Breakdown

```
Container: production
Total: 1,332 blobs, 4.57 GB
```

| Folder | Files | Size |
|--------|-------|------|
| Image/ | 363 | 163.6 MB |
| Audio/ | 72 | 26.7 MB |
| Video/ | 332 | 4,429.5 MB |
| Uploads/ | 458 | 49.0 MB |
| ChatBot/ | 106 | 9.1 MB |
| BonusMaterial/ | 1 | ~0 MB |

### Staging vs Production Overlap
```
In both containers:     486 blobs
Only in staging:        444 blobs (includes Video-Old/, chatgpt/, staging/)
Only in production:     846 blobs (newer content not synced to staging)
```

---

## 4. Database Cross-Reference

### lesson_slides Table
```
Total active slides:  450
  - With background_image: 45 slides
  - With audio:            15 slides
  - With video_library_id: 104 slides
  - With video_url:        0 slides
```

### Image Paths (background_image in slide_content JSON)
```
Unique image paths in DB:     45
Exist in staging blob:        20  (44%)
Missing from staging:         25  (56%)
Exist in production blob:     25  (ALL 25 missing from staging found in production)
```

**All 25 missing images are post-September 2023 files that were added to production but never synced to staging.**

### Audio Paths
```
Unique audio paths in DB:     15
Exist in staging blob:        8   (53%)
Missing from staging:         7   (47%)
Exist in production blob:     7   (ALL 7 missing from staging found in production)
```

**All 7 missing audio files have September 2025 timestamps — uploaded directly to production.**

### Video Library References
```
video_library_ids referenced by slides: 101 unique IDs
video_libraries records in DB:          3 total (1 active, 2 deleted)
video_libraries records that exist:     1 (id=163, "Reading the Room Video 2")
Missing video_library records:          100 (IDs referenced but not in video_libraries table)
```

**The only active video_library record (id=163) references:**
- Video: `Video/6/productionreading-th-20250912133424.mp4` -- NOT in staging, IS in production
- Thumbnail: `Video/Thumbnail/Thumbnail-6-20250912133425.png` -- NOT in staging, IS in production

### Orphan Analysis (blobs with no DB reference)
```
Image/ blobs in staging: 262     Referenced by DB: 45    Orphans: 242 (92%)
Audio/ blobs in staging: 67      Referenced by DB: 15    Orphans: 59  (88%)
```

---

## 5. SAS URL Service Analysis

File: `/home/rahil/Projects/baap/.claude/command-center/backend/services/azure_blob_service.py`

### How It Works
1. **AzureBlobService** loads credentials from `.env` on init
2. **generate_sas_url()** creates time-limited (1-hour default) read-only SAS URLs
3. **parse_slide_content()** scans slide_content JSON for keys: `background_image`, `audio`, `video`, `thumbnail`
4. **BLOB_PATH_PATTERN** matches: `^(Image|Audio|Video)/\S+\.\w{2,4}$`
5. URL format: `https://productionmynextory.blob.core.windows.net/staging/{blob_path}?{sas_token}`

### Key Behaviors
- SAS URLs are generated **regardless of whether the blob exists** -- no existence check
- `check_blob_exists()` method exists but is **not called** by `parse_slide_content()` or `get_lesson_slides_with_urls()`
- If a blob path fails SAS generation, the field is set to `None` (silent failure)
- **Container is hardcoded to "staging"** via .env CONTAINER variable

### CRITICAL ISSUE
The service generates SAS URLs pointing to the **staging** container, but **56% of image paths** and **47% of audio paths** referenced by lesson_slides exist only in the **production** container. These URLs will return HTTP 404.

---

## 6. Key Findings

### Finding 1: Staging/Production Drift
The DB references blob paths that mostly exist in `production` but not in `staging`. The SAS URL service is configured to use `staging`. **Over half of all media URLs served to users will be broken (404)**.

### Finding 2: Ghost Video Library
Of 104 slides referencing a `video_library_id`, only 1 ID (163) actually exists in the `video_libraries` table. The other 100 IDs point to records that were either hard-deleted or never existed in this database copy.

### Finding 3: Massive Orphan Content
92% of images and 88% of audio files in staging blob are not referenced by any current lesson_slide. 301 orphan files consuming storage.

### Finding 4: Video-Old/ is a Dead Copy
The `Video-Old/` folder (165 files, 2.47 GB) was created in a single batch on 2024-08-20 — appears to be a backup/migration artifact. Not referenced anywhere.

### Finding 5: 645 Asset Containers
The 645 `asset-{uuid}` containers appear to be from a CMS or video processing pipeline (possibly MediaKind integration). Separate asset management system from the `Image/`/`Audio/`/`Video/` folder structure.

---

## 7. Recommended Fixes

### Fix 1: Dual-Container Fallback (HIGH PRIORITY)
Modify `azure_blob_service.py` to try `staging` first, fall back to `production`:
```python
def generate_sas_url(self, blob_path, container=None):
    containers = [container or self.container, 'production']
    for c in containers:
        if self.check_blob_exists(blob_path, c):
            return self._generate_sas(blob_path, c)
    return None
```

### Fix 2: Video Library Gap (MEDIUM PRIORITY)
For the 100 missing video_library_ids, the videos likely exist in Azure blob but the DB records were lost. Could reconstruct from blob inventory matching `Video/` paths.

### Fix 3: Cleanup (LOW PRIORITY)
- Delete `Video-Old/` (saves 2.47 GB)
- Audit orphan blobs vs actual usage
