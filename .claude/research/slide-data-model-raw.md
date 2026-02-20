# Lesson Slides Data Model Report (Raw Agent Output)
> Agent: a8b784c | Date: 2026-02-20

## Table Schema

**Table**: `lesson_slides` (521 total rows, InnoDB)

| Column | Type | Notes |
|--------|------|-------|
| `id` | int(11) PK auto_increment | |
| `lesson_detail_id` | int(11) nullable | FK to `lesson_details.id` |
| `type` | varchar(50) nullable | Slide type discriminator |
| `slide_content` | longtext nullable | JSON content blob |
| `video_library_id` | int(11) nullable | FK to `video_libraries.id` |
| `priority` | int(11) nullable | Display ordering |
| `created_at` | datetime nullable | |
| `updated_at` | datetime nullable | |
| `deleted_at` | datetime nullable | Soft delete |

## Complete Type Taxonomy (68 unique types, 521 active rows)

### Tier 1: Primary Types (10+ slides)

| Type | Count | Category |
|------|-------|----------|
| `video` | 94 | Media |
| `image` | 39 | Media + Text |
| `take-away` | 33 | Text |
| `question-answer` | 29 | Interactive (free-text) |
| `greetings` | 27 | Text |
| `image-with-question2` | 16 | Media + Interactive |
| `image5` | 15 | Media + Interactive |
| `image6` | 14 | Media + Text |
| `stakeholder-question-answer` | 11 | Interactive (stakeholder) |
| `stakeholder-question` | 11 | Interactive (stakeholder) |

### Tier 2: Secondary Types (5-9 slides)

| Type | Count | Category |
|------|-------|----------|
| `select-option3` | 9 | Interactive (selection) |
| `special-image1` | 9 | Media + Text |
| `side-by-side-dropdown-selector` | 7 | Interactive (dropdown) |
| `one-word-apprication` | 7 | Interactive (word) |
| `select-option2` | 6 | Interactive (selection) |
| `question-answer1` | 6 | Interactive (free-text) |
| `side-by-side-form2` | 6 | Interactive (form) |
| `multiple-choice` | 6 | Interactive (quiz) |
| `image-with-questions` | 6 | Media + Interactive |
| `check-yes-or-no` | 5 | Interactive (binary) |
| `video3` | 5 | Media + Interactive |
| `select-option5` | 5 | Interactive (selection) |
| `question-with-example` | 5 | Interactive (guided) |
| `select-option6` | 5 | Interactive (selection) |

### Tier 3: Low-Frequency Types (2-4 slides)

`show-gratitude` (4), `image2` (4), `image4` (4), `select-option7` (3), `select-true-or-false` (3), `select-range` (3), `select-option4` (3), `image-with-content` (3), `three-word` (2), `question-answer3` (2), `select-option` (2), `choose-true-or-false` (2), `image1` (2), `one-word-content-box` (2), `take-to-lunch` (2), `special-image` (2), `one-word-select-option` (2), `sparkle` (2), `select-one-word` (2)

### Tier 4: Singleton Types (1 each, 24 types)

`decision2`, `image-with-radio`, `side-by-side-form`, `single-choice-with-message`, `stakeholders`, `image3`, `side-by-side-print`, `celebrate`, `video5`, `select-the-best`, `select-option-with-message`, `video-with-question`, `questions-example2`, `video2`, `people-you-would-like-to-thank`, `decision`, `chat-interface`, `video6`, `video4`, `answered-stakeholders`, `image-with-select-option`, `select-option-with-button`, `build-your-network`, `stakeholders-selected`, `side-by-side-form4`

## Content JSON Schemas Per Type Family

### 1. VIDEO FAMILY
```json
{ "slide_title": "string|null", "is_headsup": 0|1, "heads_up": "string|null" }
```
Video variants (video3-6) add: `"options": [{ "title": "string", "msg": "string" }]`
Video source: `video_library_id` FK -> `video_libraries.video` path + `url` (HLS/DASH)

### 2. IMAGE FAMILY
```json
{
  "background_image": "Image/YYYYMMDDHHMMSS.jpg|png",
  "slide_title": "string|null",
  "audio": "Audio/YYYYMMDDHHMMSS.mp3",
  "content": "string (HTML)",
  "short_description": "string",
  "is_headsup": 0|1, "heads_up": "string|null"
}
```
Variants: image2 has `content_description`; image5 has `options[{option,description}]`, `content_title`, `bonus_material`; image6 has `content_title`, `font_size`

### 3. QUESTION-ANSWER FAMILY
```json
{
  "slide_title": "string",
  "questions": ["string", ...] | [{"question":"string","word":"string"}],
  "content_title": "string|null",
  "is_backpack": true|false, "is_task": true|false, "task_name": "string"
}
```
question-with-example adds: `card_title`, `card_content`, `examples: [["string",...],...]`
stakeholder-question adds: `stakeholder_id`, `stakeholder_name`

### 4. SELECT-OPTION FAMILY
```json
{
  "slide_title": "string|null",
  "options": ["string", ...],
  "card_title": "string",
  "is_backpack": true, "no_of_options": "string"
}
```
select-option2 adds `feedback`; select-option5 has category assignment; select-option6 is checkboxes

### 5. QUIZ/ASSESSMENT FAMILY
```json
{
  "card_title": "string",
  "no_of_questions": "string",
  "questions": [{ "question": "string", "options": [{ "option": "string", "is_true": true|false }] }]
}
```
select-true-or-false: `answer: "True|False"`, `true_statement`, `false_statement`
check-yes-or-no: `moreThan2Message`, `lessThan2Message`
select-range (Likert): `options: ["Never","Rarely","Sometimes","Often","Very Often"]`

### 6. FORM FAMILY
```json
{
  "lhs_title": "string", "rhs_title": "string",
  "no_of_questions": "string",
  "questions": { "LHS": [...], "RHS": [...], "placeholderLHS": [...], "placeholderRHS": [...] }
}
```

### 7. WORD SELECTION FAMILY
three-word: `words: "comma-separated 50-70+ words"`, `no_of_words: "3"`
select-one-word: `question: "string (contains |WORD| placeholder)"`
one-word-apprication: `appreciation: "string (contains DYNAMIC_WORD)"`

### 8. STAKEHOLDER FAMILY
```json
{
  "slide_title": "string",
  "select_count": "string",
  "stakeholders": [{ "name": "string", "image": "Image/stakeholderN*.png" }]
}
```

### 9. SPECIAL/ENGAGEMENT TYPES
- greetings: `greetings` (long message), `advisor_name`, `advisor_content`
- take-away: `message` (may have DYNAMIC_WORD), `message_1`, `message_2`
- decision: `decision: [{title, content}]`, `decision_count`
- celebrate: `content_title`, `content_description` (HTML)
- chat-interface: `options: [{question, answer}]`
- build-your-network: `options: [{card_title, question[], answer[]}]`

## Content Field Frequency Matrix

| Field | video | image | take-away | question-answer | greetings | select-option* | multiple-choice |
|-------|-------|-------|-----------|-----------------|-----------|----------------|-----------------|
| slide_title | Y | Y | Y | Y | Y | Y | -- |
| is_headsup | Y | Y | Y | Y | Y | Y | Y |
| background_image | -- | Y | -- | -- | -- | -- | -- |
| audio | rare | Y | -- | -- | -- | -- | -- |
| options | -- | -- | -- | -- | -- | Y | Y |
| questions | -- | -- | -- | Y | -- | Y | Y |
| is_backpack | -- | -- | -- | Y | -- | Y | -- |
| greetings | -- | -- | -- | -- | Y | -- | -- |
| message | -- | -- | Y | -- | -- | Y | -- |

## Media Asset Patterns

- **Image**: `Image/YYYYMMDDHHMMSS.{jpg|png}` — 117 of 521 slides have background_image
- **Audio**: `Audio/YYYYMMDDHHMMSS.mp3` — 66 of 521 slides have audio
- **Video**: via `video_library_id` FK — 104 slides (94 video + 5 video3 + 5 singletons)
- **Stakeholder**: `Image/stakeholderN*.png`
- Paths are relative; prepend `https://productionmynextory.blob.core.windows.net/staging/`

## Key Design Notes

1. **DYNAMIC_WORD**: Template variable for user's selected word from three-word -> select-one-word flow
2. **HTML content**: Most text has HTML entities — render as innerHTML, not plain text
3. **Backpack**: 18+ types set `is_backpack: true` — persist responses
4. **Tasks**: Many slides set `is_task: true` with `task_name` — create todo items
5. **Content fragmentation**: slide_content sometimes split across multiple rows (concatenate by lesson_detail_id + type)
6. **No absolute URLs in slide_content**: All paths are relative, app prepends base URL at render time
