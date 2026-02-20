# Slide Data Model — Complete Type Taxonomy

> Generated 2026-02-20 from database exploration of `lesson_slides` table (521 rows, 68 types)

## Table Schema

| Column | Type | Notes |
|--------|------|-------|
| `id` | int(11) PK | auto_increment |
| `lesson_detail_id` | int(11) | FK to `lesson_details.id` |
| `type` | varchar(50) | Slide type discriminator |
| `slide_content` | longtext | JSON content blob |
| `video_library_id` | int(11) | FK to `video_libraries.id` |
| `priority` | int(11) | Display ordering |

## 7 Rendering Categories

### Category A: Media-Primary (full-screen with overlay)
**Types**: `video`, `video2`-`video6`, `image`, `image1`-`image6`, `image-with-content`, `special-image`, `special-image1`, `sparkle`

### Category B: Interactive-Primary (card with inputs)
**Types**: `question-answer`, `question-answer1`, `question-answer3`, `question-with-example`, `stakeholder-question`, `stakeholder-question-answer`

### Category C: Selection-Primary (option picker)
**Types**: `select-option` through `select-option7`, `multiple-choice`, `select-true-or-false`, `choose-true-or-false`, `check-yes-or-no`, `select-range`, `side-by-side-dropdown-selector`, `select-one-word`, `three-word`, `one-word-select-option`

### Category D: Form-Primary (structured input)
**Types**: `side-by-side-form`, `side-by-side-form2`, `side-by-side-form4`, `side-by-side-print`

### Category E: Media + Interactive Hybrid
**Types**: `image-with-question2`, `image-with-questions`, `image-with-radio`, `image-with-select-option`, `video3`, `video-with-question`

### Category F: Engagement/Narrative
**Types**: `greetings`, `take-away`, `decision`, `decision2`, `celebrate`, `show-gratitude`, `take-to-lunch`, `people-you-would-like-to-thank`, `one-word-apprication`, `one-word-content-box`, `chat-interface`, `build-your-network`

### Category G: Stakeholder Management
**Types**: `stakeholders`, `stakeholders-selected`, `answered-stakeholders`

## Type Distribution (top 15)

| Type | Count | Category |
|------|-------|----------|
| `video` | 94 | A |
| `image` | 39 | A |
| `take-away` | 33 | F |
| `question-answer` | 29 | B |
| `greetings` | 27 | F |
| `image-with-question2` | 16 | E |
| `image5` | 15 | A |
| `image6` | 14 | A |
| `stakeholder-question-answer` | 11 | G |
| `stakeholder-question` | 11 | G |
| `select-option3` | 9 | C |
| `special-image1` | 9 | A |
| `side-by-side-dropdown-selector` | 7 | C |
| `one-word-apprication` | 7 | F |
| `select-option2` | 6 | C |

## JSON Schema Per Type Family

### VIDEO FAMILY
```json
{
  "slide_title": "string|null",
  "is_headsup": 0|1,
  "heads_up": "string|null",
  "options": [{ "title": "string", "msg": "string" }]  // video3-6 only
}
```
Video source: `video_library_id` FK → `video_libraries.video` (path like `Video/6/production*.mp4`)
Streaming: `video_libraries.url` contains HLS + DASH paths

### IMAGE FAMILY
```json
{
  "background_image": "Image/YYYYMMDDHHMMSS.jpg|png",
  "slide_title": "string|null",
  "audio": "Audio/YYYYMMDDHHMMSS.mp3",
  "content": "string (HTML)",
  "short_description": "string",
  "is_headsup": 0|1,
  "heads_up": "string|null",
  "content_title": "string",  // image5, image6
  "font_size": "Medium|Large",  // image6
  "options": [{"option": "string", "description": "string"}],  // image5
  "no_of_options": "string"  // image5
}
```

### QUESTION-ANSWER FAMILY
```json
{
  "slide_title": "string",
  "questions": ["string", ...] | [{"question": "string", "word": "string"}],
  "content_title": "string",
  "is_backpack": true|false,
  "is_task": true|false,
  "task_name": "string",
  "bulbExamples": [],
  "is_message": true|false
}
```

### QUESTION-WITH-EXAMPLE
```json
{
  "card_title": "string",
  "card_content": "string",
  "question_count": "string",
  "questions": [{"title": "string", "question": "string", "header": "string"}],
  "examples": [["string", ...], ...],
  "is_backpack": true|false,
  "is_task": true|false
}
```

### SELECT-OPTION FAMILY
```json
{
  "slide_title": "string|null",
  "options": ["string", ...],
  "card_title": "string",
  "option_title1": "string",
  "option_title2": "string",
  "message": "string",
  "is_backpack": true,
  "no_of_options": "string",
  "feedback": "string"  // select-option2
}
```

### QUIZ/ASSESSMENT
```json
{
  "card_title": "string",
  "no_of_questions": "string",
  "questions": [{
    "question": "string",
    "options": [{"option": "string", "is_true": true|false}]
  }]
}
```

### FORM FAMILY
```json
{
  "lhs_title": "string",
  "rhs_title": "string",
  "no_of_questions": "string",
  "questions": {
    "LHS": ["string", ...],
    "RHS": ["string", ...],
    "placeholderLHS": ["string", ...],
    "placeholderRHS": ["string", ...]
  }
}
```

### GREETINGS
```json
{
  "slide_title": "string",
  "greetings": "string (long message)",
  "advisor_content": "string",
  "advisor_name": "string"
}
```

### TAKE-AWAY
```json
{
  "slide_title": "string|null",
  "message": "string (may contain DYNAMIC_WORD)",
  "message_1": "string",
  "message_2": "string"
}
```

### THREE-WORD / WORD SELECTION
```json
{
  "slide_title": "string",
  "words": "comma-separated string of 50+ words",
  "no_of_words": "string",
  "is_backpack": true
}
```

### STAKEHOLDERS
```json
{
  "slide_title": "string",
  "select_count": "string",
  "stakeholders": [{"name": "string", "image": "Image/stakeholderN*.png"}]
}
```

## Media Asset Reality

### Azure Blob Containers
| Container | Blobs | Size | Status |
|-----------|-------|------|--------|
| **staging** (configured) | 930 | 6.42 GB | App uses this |
| **production** | 1,332 | 4.57 GB | Has newer content |

### CRITICAL: Media Availability
| Asset Type | In DB | In staging | In production | Missing entirely |
|------------|-------|-----------|---------------|-----------------|
| Images | 45 | 20 (44%) | 25 (56%) | 0 |
| Audio | 15 | 8 (53%) | 7 (47%) | 0 |
| Video library | 101 IDs | 1 exists | 100 missing from DB | 100 |

**All "missing" images and audio exist in `production` container. None are truly missing.**
**Fix: SAS URL service must check `production` container as fallback when `staging` blob is 404.**

### Path Formats
- Image: `Image/YYYYMMDDHHMMSS.{jpg|png|webp}`
- Audio: `Audio/YYYYMMDDHHMMSS.mp3`
- Video: `Video/{n}/production*.mp4`
- Base URL: `https://productionmynextory.blob.core.windows.net/{container}/`

## Design Notes

1. **DYNAMIC_WORD**: Multiple types reference `DYNAMIC_WORD` or `|WORD|` — substitute user's selected word at render time
2. **HTML content**: Most text fields contain HTML entities and tags — render as HTML, not plain text
3. **Backpack**: 18+ types set `is_backpack: true` — persist user responses
4. **Tasks**: Many slides set `is_task: true` with `task_name` — create todo items
5. **Heads-up tips**: When `is_headsup=1`, show `heads_up` as a tip callout
