# Slide Type Taxonomy — Full Database Exploration
> Agent: a8b784c | Date: 2026-02-20 | Source: lesson_slides table (521 rows)

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

---

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

| Type | Count | Category |
|------|-------|----------|
| `show-gratitude` | 4 | Interactive (guided) |
| `image2` | 4 | Media + Text |
| `image4` | 4 | Media + Text |
| `select-option7` | 3 | Interactive |
| `select-true-or-false` | 3 | Interactive (quiz) |
| `select-range` | 3 | Interactive (scale) |
| `select-option4` | 3 | Interactive |
| `image-with-content` | 3 | Media + Text |
| `three-word` | 2 | Interactive (word) |
| `question-answer3` | 2 | Interactive |
| `select-option` | 2 | Interactive |
| `choose-true-or-false` | 2 | Interactive (quiz) |
| `image1` | 2 | Media |
| `one-word-content-box` | 2 | Interactive (word) |
| `take-to-lunch` | 2 | Interactive (task) |
| `special-image` | 2 | Media + Text |
| `one-word-select-option` | 2 | Interactive (word) |
| `sparkle` | 2 | Decorative |
| `select-one-word` | 2 | Interactive (word) |

### Tier 4: Singleton Types (1 slide each, 24 types)

`decision2`, `image-with-radio`, `side-by-side-form`, `single-choice-with-message`, `stakeholders`, `image3`, `side-by-side-print`, `celebrate`, `video5`, `select-the-best`, `select-option-with-message`, `video-with-question`, `questions-example2`, `video2`, `people-you-would-like-to-thank`, `decision`, `chat-interface`, `video6`, `video4`, `answered-stakeholders`, `image-with-select-option`, `select-option-with-button`, `build-your-network`, `stakeholders-selected`, `side-by-side-form4`

---

## Content JSON Schema Per Type Family

### 1. VIDEO FAMILY (`video`, `video2`-`video6`, `video-with-question`)

**Video source**: All video types use `video_library_id` FK (not inline URLs). 94 of 94 `video` slides have `video_library_id` set.

**slide_content JSON fields**:
```json
{
  "slide_title": "string|null",
  "is_headsup": 0|1,
  "heads_up": "string|null"
}
```

**Video variants** (`video3`, `video4`, `video5`, `video6`) add:
```json
{
  "options": [{ "title": "string", "msg": "string" }]
}
```

**`video-with-question`** adds question fields.

**`video_libraries` table fields**: `id`, `title`, `transcript`, `video` (relative path like `Video/6/production*.mp4`), `thumbnail`, `assets` (Azure Media Services JSON), `job` (encoding job JSON), `locator` (streaming locator JSON), `url` (streaming paths: HLS + DASH).

**Rendering strategy**: Load `video_library_id` from `video_libraries`, extract HLS/DASH streaming URL from `url` JSON. Display `slide_title` as header. Show `heads_up` as a tip/callout if `is_headsup=1`. For variant types, render options cards below the video.

---

### 2. IMAGE FAMILY (`image`, `image1`-`image6`, `image-with-content`, `image-with-questions`, `image-with-question2`, `image-with-radio`, `image-with-select-option`, `special-image`, `special-image1`, `sparkle`)

**Common base fields**:
```json
{
  "background_image": "Image/YYYYMMDDHHMMSS.jpg|png",
  "slide_title": "string|null",
  "audio": "Audio/YYYYMMDDHHMMSS.mp3",
  "content": "string (HTML)",
  "short_description": "string",
  "is_headsup": 0|1,
  "heads_up": "string|null"
}
```

**Image path format**: Relative paths like `Image/20230912031906.jpg`. These are Azure Blob Storage paths under the `staging` container at `productionmynextory.blob.core.windows.net`.

**Audio path format**: Relative paths like `Audio/20250909015725.mp3`. Same blob storage.

**Variant-specific fields**:

| Variant | Additional Fields |
|---------|-------------------|
| `image` | `content`, `short_description` |
| `image2`/`image-with-content` | `content_count`, `content_description` (HTML), `content` (title text) |
| `image4` | Same as `image` with `imageExamples` array possible |
| `image5` | `options[{option, description}]`, `no_of_options`, `content_title`, `content`, `bonus_material` |
| `image6` | `content` (HTML), `content_title`, `font_size` ("Medium"/"Large") |
| `image-with-questions` | `questions[]` (string array), `content_title`, `dig_deeper` |
| `image-with-question2` | `options[{question, title, box, answer[]}]`, `content_on_image`, `note`, `is_message` |
| `special-image1` | `background_color`, `content1`, `content2`, `special_word` |
| `sparkle` | `content`, `content_title`, `font_size` -- decorative celebration slide |

**Rendering strategy**: Display `background_image` as full-bleed background (resolve against Azure Blob base URL). Overlay `slide_title`, `content`, `short_description` as text. If `audio` is present, show audio player. For `image-with-*` variants, render the interactive component (questions, options, radio) over the image.

---

### 3. QUESTION-ANSWER FAMILY (`question-answer`, `question-answer1`, `question-answer3`, `question-with-example`, `stakeholder-question`, `stakeholder-question-answer`)

**`question-answer`** schema:
```json
{
  "slide_title": "string",
  "is_headsup": 0|1,
  "heads_up": "string",
  "questions": ["string", "string", ...],
  "content_title": "string|null",
  "bulbExamples": [],
  "lhs_popup_header": "string|null",
  "is_backpack": true|false,
  "is_task": true|false,
  "task_name": "string",
  "is_message": true|false
}
```

**`question-answer1`** schema (structured questions with labels):
```json
{
  "slide_title": "string|null",
  "questions": [{ "question": "string", "word": "string (label)" }],
  "content_title": "string (HTML)",
  "is_backpack": true|false,
  "is_task": true|false,
  "task_name": "string"
}
```

**`question-with-example`** schema (questions with example answers):
```json
{
  "slide_title": "string|null",
  "card_title": "string",
  "card_content": "string",
  "question_count": "string (number)",
  "questions": [{ "title": "string", "question": "string", "header": "string" }],
  "examples": [["string", ...], ...],
  "is_backpack": true|false,
  "is_task": true|false,
  "task_name": "string",
  "is_message": true|false,
  "is_question_title": "string|null"
}
```

**`stakeholder-question`** schema:
```json
{
  "slide_title": "string",
  "question": "string (HTML)",
  "card_title": "string",
  "stakeholder_id": "string (number)",
  "stakeholder_name": "string (e.g. 'Your Boss', 'Direct Reports')",
  "is_backpack": true|false|null,
  "is_task": true|false|null,
  "task_name": "string|null"
}
```

**`stakeholder-question-answer`** schema:
```json
{
  "slide_title": "string",
  "questions": ["string", "string"],
  "placeholders": ["string", "string"],
  "saveButton": "string (0|1)",
  "stakeholder_id": "string (number)",
  "stakeholder_name": "string",
  "is_backpack": true,
  "is_task": true,
  "task_name": "string"
}
```

**Rendering strategy**: Present each question as a text input or textarea. If `examples` are provided, show them in a lightbulb/hint popup. If `stakeholder_name` is present, show it as context. Save responses to backpack if `is_backpack=true`. Create task if `is_task=true`.

---

### 4. SELECT/OPTION FAMILY (`select-option` through `select-option7`, `select-option-with-button`, `select-option-with-message`, `one-word-select-option`, `select-the-best`)

**`select-option3`** (primary pattern):
```json
{
  "slide_title": "string|null",
  "options": ["string", ...],
  "card_title": "string",
  "option_title1": "string (pre-options label)",
  "option_title2": "string (free-text label)",
  "message": "string",
  "is_headsup": 0|1,
  "heads_up": "string|null",
  "is_backpack": true,
  "is_task": true|null,
  "task_name": "string|null",
  "is_message": true|null
}
```

**`select-option2`** (with feedback):
```json
{
  "slide_title": "string",
  "content_title": "string",
  "content_description": "string",
  "no_of_options": "string (number)",
  "feedback": "string (free-text prompt after selection)",
  "options": ["string", ...],
  "is_backpack": true,
  "is_task": true|null,
  "task_name": "string"
}
```

**`select-option5`** (categorization):
```json
{
  "slide_title": "string",
  "no_of_questions": "string (number)",
  "content_title": "string",
  "options": ["string", ...],
  "questions": ["string", ...],
  "is_backpack": true
}
```

**`select-option6`** (checkbox list):
```json
{
  "options": ["string", ...],
  "card_title": "string",
  "option_title": "string",
  "is_backpack": true
}
```

**Rendering strategy**: For `select-option2`/`select-option3`, render options as selectable cards/chips with an optional free-text field. For `select-option5`, render as a matrix where each question row gets a category dropdown. For `select-option6`, render as checkboxes.

---

### 5. QUIZ/ASSESSMENT FAMILY (`multiple-choice`, `select-true-or-false`, `choose-true-or-false`, `check-yes-or-no`, `select-range`, `side-by-side-dropdown-selector`)

**`multiple-choice`** schema:
```json
{
  "slide_title": "string|null",
  "card_title": "string",
  "no_of_questions": "string (number)",
  "questions": [{
    "question": "string",
    "options": [{
      "option": "string",
      "is_true": true|false
    }]
  }],
  "is_headsup": 0|1,
  "is_backpack": true|null,
  "is_task": true|null
}
```

**`select-true-or-false`** schema:
```json
{
  "slide_title": "string|null",
  "content": "string",
  "content_title": "string",
  "no_of_questions": "string",
  "questions": [{
    "question": "string",
    "answer": "True|False",
    "true_statement": "string (explanation if correct)",
    "false_statement": "string (explanation if wrong, optional)"
  }],
  "font_size": "string",
  "is_backpack": true|false
}
```

**`check-yes-or-no`** schema:
```json
{
  "slide_title": "string",
  "question": ["string", ...],
  "content_title": "string",
  "content": "string",
  "moreThan2Message": "string",
  "lessThan2Message": "string",
  "option1": "Yes",
  "option2": "Not Yet|No",
  "is_backpack": true
}
```

**`select-range`** schema (Likert scale):
```json
{
  "slide_title": "string",
  "no_of_questions": "string (number)",
  "options": ["Never", "Rarely Ever", "Sometimes", "Often", "Very Often"],
  "heading": "string",
  "description": "string|null",
  "question_font": true|null,
  "response": "string|null (feedback after completion)",
  "questions": ["string", ...],
  "is_backpack": true
}
```

**`side-by-side-dropdown-selector`** schema:
```json
{
  "slide_title": "string|null",
  "no_of_questions": "string",
  "LHS_title": "string",
  "RHS_title": "string",
  "options": ["string", "string"],
  "questions": ["string", ...],
  "is_backpack": true|null
}
```

**Rendering strategy**: `multiple-choice` renders as radio/checkbox groups with correct-answer validation. `select-true-or-false` shows True/False buttons with explanation feedback. `check-yes-or-no` renders as a binary checklist with conditional messaging based on count. `select-range` renders as a horizontal Likert-scale matrix. `side-by-side-dropdown-selector` renders as a two-column layout with dropdown per question.

---

### 6. FORM FAMILY (`side-by-side-form`, `side-by-side-form2`, `side-by-side-form4`, `side-by-side-print`)

**`side-by-side-form2`** schema (primary pattern):
```json
{
  "slide_title": "string",
  "lhs_title": "string",
  "rhs_title": "string",
  "no_of_questions": "string (number)",
  "questions": {
    "LHS": ["string", ...],
    "RHS": ["string", ...],
    "placeholderLHS": ["string", ...],
    "placeholderRHS": ["string", ...]
  },
  "is_headsup": 0|1,
  "heads_up": "string",
  "is_backpack": true
}
```

**Rendering strategy**: Two-column form. LHS = current state, RHS = desired future state. Each row has a question label and a text input pre-filled with placeholder text. Save to backpack on submit.

---

### 7. WORD SELECTION FAMILY (`three-word`, `select-one-word`, `one-word-apprication`, `one-word-content-box`, `one-word-select-option`)

**`three-word`** schema:
```json
{
  "slide_title": "string",
  "words": "comma-separated string of 50-70+ words",
  "is_headsup": 0|1,
  "heads_up": "string",
  "no_of_words": "string (number, e.g. '3')",
  "is_backpack": true|false
}
```

**`select-one-word`** schema:
```json
{
  "slide_title": "string",
  "question": "string (contains |WORD| placeholder)",
  "new_word": "string|null (1 = allow custom word)",
  "is_backpack": true,
  "is_message": true|null
}
```

**`one-word-apprication`** schema:
```json
{
  "slide_title": "string",
  "appreciation": "string (contains DYNAMIC_WORD placeholder)",
  "is_backpack": true|false
}
```

**Rendering strategy**: `three-word` renders a word cloud or chip grid; user selects up to N words. `select-one-word` shows sentences generated from the three words; user picks one. `one-word-apprication` is a celebration/confirmation slide displaying the chosen word (substituted for `DYNAMIC_WORD`).

---

### 8. STAKEHOLDER FAMILY (`stakeholders`, `stakeholders-selected`, `answered-stakeholders`)

**`stakeholders`** schema:
```json
{
  "slide_title": "string",
  "select_count": "string (number)",
  "stakeholders": [{
    "name": "string (e.g. 'Your Boss', 'Direct Reports')",
    "image": "Image/stakeholderN*.png"
  }],
  "is_backpack": false
}
```

**`stakeholders-selected`** schema:
```json
{
  "slide_title": "string",
  "is_headsup": 0|1,
  "heads_up": "string"
}
```

**Rendering strategy**: `stakeholders` renders a visual picker with avatar images; user selects up to N stakeholders. `stakeholders-selected` is a confirmation/summary slide. `answered-stakeholders` shows previously submitted stakeholder answers.

---

### 9. SPECIAL/ENGAGEMENT TYPES

**`greetings`** schema:
```json
{
  "slide_title": "string (one word theme)",
  "greetings": "string (long-form message)",
  "advisor_content": "string (e.g. 'Your advisor at myNextory')",
  "advisor_name": "string (e.g. 'XOXO,')",
  "is_headsup": 0|1,
  "heads_up": "string|null"
}
```

**`take-away`** schema:
```json
{
  "slide_title": "string|null",
  "is_headsup": 0|1,
  "message": "string (key takeaway, may contain DYNAMIC_WORD)",
  "message_1": "string (feedback prompt 1)",
  "message_2": "string (feedback prompt 2)"
}
```

**`decision`** schema:
```json
{
  "slide_title": "string|null",
  "decision_count": 3,
  "card_title": "string",
  "decision": [{
    "title": "string",
    "content": "string"
  }],
  "is_backpack": true|null
}
```

**`celebrate`** schema:
```json
{
  "slide_title": "string",
  "content_title": "string",
  "content_description": "string (HTML)",
  "no_of_cards": 1,
  "content_heading": "string",
  "lhs_title": "string",
  "content_count": 3,
  "is_backpack": false
}
```

**`show-gratitude`** schema:
```json
{
  "slide_title": "string",
  "content_title": "string",
  "content_description": "string",
  "no_of_cards": 3,
  "card_title": "string",
  "lhs_popup_header": "string",
  "bulbExamples": { "LHS": ["string", ...] },
  "is_backpack": true,
  "is_task": true,
  "task_name": "string"
}
```

**`chat-interface`** schema:
```json
{
  "slide_title": "string",
  "options": [{ "question": "string", "answer": "string" }],
  "content_title": "string"
}
```

**`build-your-network`** schema:
```json
{
  "slide_title": "string|null",
  "content": "string",
  "content_title": "string",
  "options": [{
    "card_title": "string (category name)",
    "no_of_question": "string",
    "question": ["string", ...],
    "answer": ["string (HTML)", ...]
  }],
  "is_backpack": true
}
```

---

## Content Field Frequency Matrix

| Field | video | image | take-away | question-answer | greetings | image-with-question2 | image5 | image6 | select-option* | multiple-choice | select-range | side-by-side-* |
|-------|-------|-------|-----------|-----------------|-----------|---------------------|--------|--------|----------------|-----------------|-------------|----------------|
| `slide_title` | Y | Y | Y | Y | Y | Y | Y | -- | Y | -- | Y | Y |
| `is_headsup` | Y | Y | Y | Y | Y | -- | -- | Y | Y | Y | Y | Y |
| `heads_up` | Y | Y | -- | Y | -- | -- | -- | -- | Y | -- | -- | Y |
| `content` | -- | Y | -- | -- | -- | -- | Y | Y | -- | -- | -- | -- |
| `background_image` | -- | Y | -- | -- | -- | Y | Y | Y | -- | -- | -- | -- |
| `audio` | rare | Y | -- | -- | -- | -- | rare | Y | -- | -- | -- | -- |
| `options` | -- | -- | -- | -- | -- | Y | Y | -- | Y | Y | Y | Y |
| `questions` | -- | -- | -- | Y | -- | -- | -- | -- | Y | Y | Y | Y |
| `is_backpack` | -- | -- | -- | Y | -- | -- | -- | -- | Y | -- | Y | Y |
| `is_task` | -- | -- | -- | Y | -- | -- | -- | -- | Y | -- | -- | -- |
| `task_name` | -- | -- | -- | Y | -- | -- | -- | -- | Y | -- | Y | -- |
| `greetings` | -- | -- | -- | -- | Y | -- | -- | -- | -- | -- | -- | -- |
| `message` | -- | -- | Y | -- | -- | -- | -- | -- | Y | -- | -- | -- |
| `font_size` | -- | -- | -- | -- | -- | -- | -- | Y | -- | -- | -- | -- |

---

## Media Asset Patterns

### Image Assets
- **Path format**: `Image/YYYYMMDDHHMMSS.{jpg|png}` (relative to Azure Blob container)
- **Full URL**: `https://productionmynextory.blob.core.windows.net/staging/Image/20230912031906.jpg`
- **Used in**: `image`, `image1`-`image6`, `image-with-*`, `special-image*`, `sparkle`
- **Total slides with `background_image`**: 117 of 521

### Audio Assets
- **Path format**: `Audio/YYYYMMDDHHMMSS.mp3` (relative to Azure Blob container)
- **Full URL**: `https://productionmynextory.blob.core.windows.net/staging/Audio/20250909015725.mp3`
- **Used in**: `image`, `image2`, `image4`, `image6`, `image-with-content`, `special-image*`, `sparkle`
- **Total slides with `audio`**: 66 of 521

### Video Assets
- **Not stored in `slide_content`** -- referenced via `video_library_id` FK
- **Storage path in `video_libraries.video`**: `Video/6/production*.mp4`
- **Streaming delivery**: Azure Media Services (MediaKind) with HLS + DASH streaming paths in `url` JSON
- **104 slides** have `video_library_id` set (94 `video` + 5 `video3` + 5 singletons)

### Stakeholder Images
- **Path format**: `Image/stakeholderN*.png` (N = 0-9)

### Bonus Material
- Can contain external article links (e.g., Forbes, The Muse)
- Schema: `{ "is_enable": true, "type": "Article", "title": "string", "content": "HTML with links" }`

---

## Recommended Rendering Strategy by Category

### Category A: Media-Primary (render full-screen with overlay)
**Types**: `video`, `video2`-`video6`, `image`, `image1`-`image6`, `image-with-content`, `special-image`, `special-image1`, `sparkle`

- Full-bleed background image or video player
- Text overlay for `slide_title`, `content`, `short_description`
- Audio player widget when `audio` field is present
- For video types: resolve `video_library_id` -> `video_libraries` table -> extract HLS URL from `url` JSON -> render in adaptive streaming player (e.g., Video.js with HLS plugin)

### Category B: Interactive-Primary (render as card with inputs)
**Types**: `question-answer`, `question-answer1`, `question-answer3`, `question-with-example`, `stakeholder-question`, `stakeholder-question-answer`

- Card layout with `slide_title` as header
- Render each question as a labeled textarea
- Show `examples`/`bulbExamples` in expandable hint section
- If `is_backpack=true`, auto-save answers to user's backpack
- If `is_task=true`, register a task with `task_name`

### Category C: Selection-Primary (render as option picker)
**Types**: `select-option` through `select-option7`, `multiple-choice`, `select-true-or-false`, `choose-true-or-false`, `check-yes-or-no`, `select-range`, `side-by-side-dropdown-selector`, `select-one-word`, `three-word`, `one-word-select-option`

- Render options as selectable cards, chips, radio buttons, or checkboxes depending on variant
- For `select-range`, render as a horizontal Likert scale matrix
- For `multiple-choice`, show correct/incorrect feedback using `is_true` flags
- For `select-true-or-false`, show explanatory text after answer (`true_statement`/`false_statement`)
- For `three-word`, render word cloud; user selects N words
- For `check-yes-or-no`, show conditional message based on selection count

### Category D: Form-Primary (render as structured input)
**Types**: `side-by-side-form`, `side-by-side-form2`, `side-by-side-form4`, `side-by-side-print`

- Two-column form: LHS (present state) vs RHS (future state)
- Pre-populate with placeholder examples
- Save to backpack on submit

### Category E: Media + Interactive Hybrid (image background with interactive overlay)
**Types**: `image-with-question2`, `image-with-questions`, `image-with-radio`, `image-with-select-option`, `video3`, `video-with-question`

- Full-bleed image background
- Overlay interactive component (questions, radio buttons, options cards)
- For `video3`/`video-with-question`, render video player with interactive cards below

### Category F: Engagement/Narrative (render as themed content)
**Types**: `greetings`, `take-away`, `decision`, `decision2`, `celebrate`, `show-gratitude`, `take-to-lunch`, `people-you-would-like-to-thank`, `one-word-apprication`, `one-word-content-box`, `chat-interface`, `build-your-network`

- `greetings`: Styled letter/card layout with advisor attribution
- `take-away`: Summary card with key message + feedback prompts
- `decision`: Render branching paths as clickable cards (each `decision` item is a path)
- `celebrate`: Celebration animation/confetti with card content
- `chat-interface`: Render as simulated chat bubbles (Q&A pairs)
- `build-your-network`: Accordion/tabbed layout by category

### Category G: Stakeholder Management
**Types**: `stakeholders`, `stakeholders-selected`, `answered-stakeholders`

- `stakeholders`: Visual avatar picker grid
- `stakeholders-selected`: Summary/confirmation with selected stakeholder portraits
- `answered-stakeholders`: Display previously saved answers per stakeholder

---

## Key Design Notes

1. **DYNAMIC_WORD substitution**: Multiple slide types reference `DYNAMIC_WORD` or `|WORD|` as template variables. The viewer must substitute the user's selected "one word" into these placeholders at render time.

2. **Backpack integration**: 18+ slide types set `is_backpack: true`. The viewer must persist user responses to a "backpack" store.

3. **Task creation**: Many slides set `is_task: true` with a `task_name`. The viewer should create calendar reminders or todo items from these.

4. **HTML content**: Most text fields contain HTML entities (`&rsquo;`, `&mdash;`, `<br />`, `<ul>`, `<span>`) and must be rendered as HTML, not plain text.

5. **Content fragmentation**: The `slide_content` field is sometimes split across multiple rows for the same slide. The viewer must concatenate consecutive `slide_content` values.

6. **No blob.core.windows.net URLs in slide_content**: Media paths are stored as relative paths. The application must prepend the base Azure Blob URL at render time.
