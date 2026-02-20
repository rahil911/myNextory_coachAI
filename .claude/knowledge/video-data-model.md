# Video Data Model — MyNextory Lesson Slides

## SAFETY: Azure Blob Storage is PRODUCTION — READ-ONLY

**NEVER modify, delete, rename, or upload blobs.** All access is read-only via SAS URLs.
The production container (`productionmynextory`) contains real customer video content.

## Architecture

```
lesson_slides (type='video*')
  └── video_library_id (FK) ──> video_libraries
                                   ├── video (blob path: "Video/{coach_id}/production{title}-{ts}.mp4")
                                   ├── thumbnail (blob path: "Video/Thumbnail/Thumbnail-{coach_id}-{ts}.png")
                                   ├── transcript (text with HTML entities: &mdash; &rsquo; etc.)
                                   ├── url (JSON: HLS + DASH streaming paths)
                                   ├── assets (JSON: Azure Media Services asset metadata)
                                   ├── job (JSON: encoding job metadata)
                                   └── locator (JSON: streaming locator for AMS)
```

## DB Reality (from dump)

| Metric | Value |
|--------|-------|
| Total video_libraries rows | 3 (only 3 rows in dump) |
| Active (deleted_at IS NULL) | 1 (id=163) |
| Soft-deleted | 2 (id=110, id=152) |
| video_library_ids referenced by slides | 101 unique IDs (range: 14-181) |
| Slides with matching DB record | 1 (slide 735 → vlib 163) |
| Slides WITHOUT DB record | 103 (DB records lost from dump) |

## Azure Blob Storage Reality

| Container | MP4 Videos | Thumbnails | Total |
|-----------|-----------|------------|-------|
| production | 192 | 140 | 332 |
| staging | 134+ | 137+ | 271 |

### Blob Naming Patterns

**Old format (Coach 1, 2023):**
```
Video/1/App-{title-fragment}-{YYYYMMDDHHmmss}.mp4
Video/1/App-change-20230831021044.mp4
Video/1/App-empathy-so-20230831032527.mp4
```

**New format (Coach 6, 2024-2025):**
```
Video/6/production{title-fragment}-{YYYYMMDDHHmmss}.mp4
Video/6/productionreading-th-20250912133424.mp4
```

**Thumbnails:**
```
Video/Thumbnail/Thumbnail-{coach_id}-{YYYYMMDDHHmmss}.{jpg|png|PNG}
```

### Matching: 5 of 46 slides with titles matched blob keywords
Title-based fuzzy matching is unreliable (blob filenames truncate titles).
Timestamp matching requires video_libraries.created_at which is missing for 98 IDs.

## The ONE Working Video (id=163)

| Field | Value |
|-------|-------|
| video_library_id | 163 |
| slide_id | 735 |
| lesson_detail_id | 103 |
| title | "Reading the Room Video 2" |
| blob | `Video/6/productionreading-th-20250912133424.mp4` |
| thumbnail | `Video/Thumbnail/Thumbnail-6-20250912133425.png` |
| container | production |
| transcript | "The next week, Micah waited before speaking..." |
| created_at | 2025-09-12 13:34:25 |

## API Contract

### GET /api/tory/lesson/{id}/slides

Each video slide returns:
```json
{
  "id": 735,
  "type": "video",
  "content": {
    "slide_title": "Introduction",
    "is_headsup": 0,
    "heads_up": null
  },
  "priority": 2,
  "video_library": {          // ONLY present when DB record exists
    "id": 163,
    "title": "Reading the Room Video 2",
    "video_url": "https://...blob.core.windows.net/production/Video/...mp4?{SAS}",
    "thumbnail_url": "https://...blob.core.windows.net/production/Video/Thumbnail/...png?{SAS}",
    "transcript": "The next week, Micah waited..."
  }
}
```

When `video_library` is missing from DB: **dynamic blob inventory** resolves it from Azure.

## Dynamic Blob Inventory (Production-Grade Fallback)

When the DB `video_libraries` record is missing (100/101 referenced IDs lost from dump),
the backend scans Azure production container dynamically:

1. **Cache**: Lists all `Video/*.mp4` and `Video/Thumbnail/*` blobs on first request
2. **TTL**: 1 hour in-memory cache, auto-refreshes (new uploads picked up automatically)
3. **Matching**: Two-pass resolution:
   - **Pass 1 (Individual)**: Keyword prefix match + chronological proximity scoring per blob
   - **Pass 2 (Group)**: Uses DB-anchored videos in the same lesson to calculate ID offset,
     overrides incorrect individual matches (e.g. "Introduction" wrongly matching coach 1 blob)
4. **SAS URLs**: Generated on-the-fly from matched blob paths
5. **Result**: `video_library` object with `source: "blob_inventory"` (vs `source: "database"`)

### Coverage
- **104/104 video slides across 59 lessons** resolve to working video URLs (100%)
- Group matching correctly resolves adjacent blobs from same upload session
- Keyword matching handles 10-char filename truncation ("introduction" → "introducti")
- Chronological estimation provides fallback when slide_title is empty

### Known Gotcha: SAS URL Parsing
SAS signatures contain literal `/` characters (e.g. `sig=...SA/o4...`).
When extracting timestamps from URLs, **always strip the query string first**:
```python
path = url.split('?')[0]  # MUST strip ?... before splitting by /
```

## Frontend Rendering Contract

### When video_library.video_url exists (DB or blob_inventory):
- Render `<video>` element with Plyr.js player
- Use `poster` attribute for thumbnail
- Show transcript below video (when available from DB source)
- Show slide_title as header above video
- Show "Video matched from library" badge for blob_inventory source

### When no video can be resolved:
- Show SVG play icon (not camera emoji)
- Show slide_title and "Available in the MyNextory app"
- Show heads_up callout when present

## Plyr.js Setup (CDN already loaded)

```html
<!-- Already in index.html -->
<link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css">
<script src="https://cdn.plyr.io/3.7.8/plyr.js"></script>
```

### HTML structure:
```html
<video id="plyr-{slideId}" playsinline controls
       data-poster="{thumbnail_sas_url}">
  <source src="{video_sas_url}" type="video/mp4">
</video>
```

### Initialize:
```javascript
const player = new Plyr('#plyr-{slideId}', {
  controls: ['play-large', 'play', 'progress', 'current-time', 'mute', 'volume', 'fullscreen'],
});
```

### CSS Variables for dark theme:
```css
--plyr-color-main: var(--accent, #6366f1);
--plyr-video-controls-background: linear-gradient(transparent, rgba(0,0,0,0.7));
```

## slide_content Fields for Video Slides

| Field | Present in | Usage |
|-------|-----------|-------|
| slide_title | 42/104 slides | Header text above video |
| is_headsup | 2/104 = true | Show callout tip |
| heads_up | 2/104 non-null | Callout content text |
| finishing_slide_title | 1 slide | Alternative title for final video |
| bonus_material | 1 slide | Object with article/link content |
| options | 1 slide (video2) | Quiz questions shown after video |
| questions | 1 slide (video2) | Question text for options |
| answer | 1 slide (video2) | Correct answer flags |
