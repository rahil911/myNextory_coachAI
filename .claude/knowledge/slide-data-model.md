# Slide Data Model — Complete Type Taxonomy (Real Data)

> Updated 2026-02-20 from FULLY RESTORED database. 620 active slides, 68 types, 0 orphans.
> ALL video_libraries restored (158 rows), ALL lesson_details restored (86 rows).

## Table Schema: `lesson_slides`

| Column | Type | Notes |
|--------|------|-------|
| `id` | int(11) PK | auto_increment |
| `lesson_detail_id` | int(11) | FK → `lesson_details.id` (0 orphans after restoration) |
| `type` | varchar(50) | Slide type — 68 distinct values |
| `slide_content` | longtext | JSON blob with type-specific fields |
| `video_library_id` | int(11) | FK → `video_libraries.id` (0 orphans, 118 slides reference videos) |
| `priority` | int(11) | Sort order within a lesson |
| `created_at` | datetime | |
| `updated_at` | datetime | |
| `deleted_at` | datetime | Soft-delete |

## RENDERING MANDATE

**100% of content must render. Zero fallbacks. Zero placeholders. Zero "unavailable" messages.**

- All 112 video slides have DB records with blob paths — render with Plyr
- All images must resolve via Azure SAS URL (try staging, then production container)
- All 68 types must have dedicated renderers — no "unknown type" JSON dumps
- HTML content fields render as HTML (innerHTML), not escaped text
- `DYNAMIC_WORD` token in strings gets replaced with user's selected One Word

---

## Cross-Cutting Common Fields

These fields appear across many slide types with consistent semantics:

| Field | Type | Meaning | Renderer Action |
|-------|------|---------|-----------------|
| `slide_title` | string\|null | Main headline | Render as `<h2>` header |
| `is_headsup` | 0\|1 | Show heads-up banner? | Render callout box if 1 |
| `heads_up` | string\|null | Banner content (HTML) | Render as styled callout |
| `is_backpack` | bool\|null | Save response to backpack? | Show backpack badge icon |
| `is_task` | bool\|null | Add to user's task list? | Show task badge icon |
| `task_name` | string\|null | Task label | Show with task badge |
| `is_message` | bool\|null | Show reveal message after answer? | Toggle message on submit |
| `no_of_questions` | string\|int | How many question rows | Use to size form |
| `options` | array | Choice options | Render as chips/cards/radio |
| `questions` | array\|object | Question text(s) | Render as labels + inputs |
| `content` | string | Instructional text (may be HTML) | Render as innerHTML |
| `content_title` | string | Section subheading | Render as `<h3>` |
| `content_description` | string | Descriptive paragraph | Render as `<p>` |
| `background_image` | string | Azure Blob path (`Image/...`) | SAS URL → `background-image` |
| `audio` | string | Azure Blob path (`Audio/...`) | SAS URL → Plyr audio player |
| `bonus_material` | object | Supplemental doc: `{is_enable, type, title, content, document}` | Expandable attachment card |
| `bulbExamples` | array\|object | Popup examples (LHS/RHS for two-col) | Lightbulb icon → popup |
| `lhs_popup_header` / `rhs_popup_header` | string | Labels for popup panels | Popup header text |
| `DYNAMIC_WORD` | token in strings | User's selected "One Word" | Replace at render time |

---

## Category A: VIDEO (7 types, 112 slides)

All video slides have `video_library_id` → `video_libraries` with blob paths. Render with Plyr.

### `video` — 102 slides
Standard video playback with optional title.
```json
{
  "slide_title": "David's Shift",
  "finishing_slide_title": "Lead the Way with AI",
  "is_headsup": 0,
  "heads_up": null
}
```
**Keys**: `slide_title`, `finishing_slide_title`, `is_headsup`, `heads_up`
**Also common**: embedded `bonus_material` object in some slides (HTML content may break JSON_VALID)
**Render**: Plyr video player → SAS URL from `video_libraries.video` blob path. Show `slide_title` above, `finishing_slide_title` on completion.

### `video2` — 1 slide
Video + emotion-selection quiz after watching.
```json
{
  "options": [["Angry","Irritated","Frustrated","Offended","Embarrassed"], ["Dismissed","Valued","Honored","Disrespected","Supported"]],
  "answer": [["0","0","1","0","1"], ["1","0","0","1","0"]],
  "no_of_options": "2",
  "question_title": ["Select two emotions.", "Select two emotions."],
  "questions": ["How do you think Sam was feeling?", "How do you think Jaime felt?"],
  "no_of_questions": 2,
  "is_backpack": true, "is_task": false, "task_name": "Self Awareness 1"
}
```
**Render**: Plyr video → then show emotion grid quiz. `options` is 2D array (options per question). `answer` marks correct ones.

### `video3` — 5 slides
Video + expandable tip/strategy cards.
```json
{
  "options": [
    {"title": "Turn Off the Spotlight", "msg": "Avoid correcting publicly..."},
    {"title": "Provide a Plan", "msg": "Provide meeting agendas..."}
  ]
}
```
**Render**: Plyr video → then card grid from `options[{title, msg}]`.

### `video4` — 1 slide
Video + Likert-scale rating survey.
```json
{
  "no_of_questions": "6", "no_of_ranges": 2,
  "content_title": "Rate your experience, skill, or concept.",
  "questions": ["I think aloud often.", "I need time to decide..."],
  "options": ["Strongly disagree","Disagree","Undecided","Agree","Strongly Agree"],
  "is_backpack": true
}
```
**Render**: Plyr video → Likert scale matrix. `options` = scale labels, `questions` = row items.

### `video5` — 1 slide
Video + conversation/reflection scenario cards.
```json
{
  "options": [
    {"title1": "A direct report asks...", "question": "If I'm highly successful...", "title2": "As their boss, you would say..."}
  ],
  "is_message": true, "is_backpack": true
}
```
**Render**: Plyr video → scenario cards with `title1` (situation), `question` (reflection), `title2` (response prompt).

### `video6` — 1 slide
Video + star-rating selection with response text.
```json
{
  "question": "If your relationship with your boss was a movie, how would you rate it?",
  "sub_title": "Don't worry: your selection will be for your eyes only...",
  "options": [
    {"title": "We are partners...", "star_count": "4", "response": "This is great!"},
    {"title": "Sometimes we get along...", "star_count": "3", "response": "..."}
  ],
  "is_backpack": true
}
```
**Render**: Plyr video → star rating cards. Each option shows stars + title. On select, reveal `response`.

### `video-with-question` — 1 slide
Video + C.A.R.E. structured reflection prompts.
```json
{
  "content_title": "Think about a disappointment...",
  "questions": [
    {"word": "Cause", "question1": "What happened?", "question2": "Why do you think it happened?"},
    {"word": "Assess", "question1": "...", "question2": "..."}
  ],
  "is_backpack": true
}
```
**Render**: Plyr video → accordion with `word` as header, two textareas per section.

---

## Category B: IMAGE (14 types, 136 slides)

Images use `background_image` field → Azure Blob SAS URL. Try staging container first, then production.

### `image` — 45 slides
Full-bleed background image with optional audio, text overlay.
```json
{
  "background_image": "Image/20230912060107.png",
  "audio": "Audio/20250911104654.mp3",
  "slide_title": null,
  "content": "Once you figure out what you're grateful for, take a moment to celebrate it.",
  "short_description": null,
  "is_headsup": 0, "heads_up": null
}
```
**Render**: Full-bleed `background_image`, text overlay (`slide_title`, `content` as HTML, `short_description`), Plyr audio if `audio` present.

### `image1` — 5 slides
Same as `image` but without audio field.
**Keys**: `background_image`, `content`, `slide_title`, `short_description`, `is_headsup`, `heads_up`
**Render**: Same as `image`, no audio.

### `image2` — 5 slides
Carousel of image cards.
```json
{
  "imageExamples": [
    {"image_title": "Friction Finder", "name": " ", "description": "...", "background_image": "Image/...", "audio": null}
  ],
  "no_of_images": 4,
  "slide_title": "The Mindset of an AI-Savvy Leader"
}
```
**Render**: Card carousel from `imageExamples[]`. Each card: image bg + `image_title` + `description`.

### `image3` — 1 slide
Image with content block and backpack save.
**Keys**: `background_image`, `content`, `content_title`, `slide_title`, `is_backpack`, `is_task`, `task_name`
**Render**: Same as `image` + `content_title` heading + backpack/task badges.

### `image4` — 6 slides
Expandable cards with dependent (reveal) images.
```json
{
  "background_image": "Image/...",
  "audio": "Audio/...",
  "imageExamples": [
    {"image": "Image/...", "image_title": "Tools for the Head", "description": "...", "dependent_image": "Image/...", "audio": "..."}
  ],
  "no_of_cards": "3",
  "content_title": "Open each skill set",
  "content": "...",
  "dependent": "1"
}
```
**Render**: Background image + expandable cards. Each card shows `image`, `image_title`, `description`. When `dependent`=1, clicking reveals `dependent_image`.

### `image5` — 25 slides
Image with expandable options list.
```json
{
  "background_image": "Image/...",
  "slide_title": "Tools for the Head",
  "options": [{"description": "...", "option": "Online Course"}, ...],
  "no_of_options": "5",
  "content_title": "Guess what?",
  "content": "..."
}
```
**Render**: Full-bleed image + `slide_title` + expandable cards from `options[{option, description}]`.

### `image6` — 16 slides
Image with styled content block (font_size control).
```json
{
  "background_image": "Image/...",
  "content": "<div>...</div>",
  "content_title": "The Three Types of Employees",
  "font_size": "Large",
  "slide_title": null, "short_description": null
}
```
**Render**: Full-bleed image + `content_title` + `content` as HTML. Apply `font_size` ("Large"/"Small"/null).

### `image-with-content` — 3 slides
Image with multiple content blocks.
```json
{
  "background_image": "Image/...",
  "audio": "Audio/...",
  "content": "<p>...</p>",
  "content_count": 3,
  "content_description": "...",
  "slide_title": "..."
}
```
**Render**: Full-bleed image + audio + `slide_title` + `content` (HTML) + `content_description`.

### `image-with-question2` — 17 slides
Image with interactive action/answer tiles overlay.
```json
{
  "background_image": "Image/...",
  "slide_title": "Skill Building Journey",
  "options": [
    {"question": "...", "title": "Tools for the Head"},
    {"question": "...", "title": "Tools for the Heart", "box": "2", "answer": ["..."]}
  ],
  "content_on_image": "...",
  "note": "...",
  "is_message": true
}
```
**Render**: Image background + semi-transparent overlay. Cards from `options[{title, question, answer[]}]`. `content_on_image` as header text. `note` as footer.

### `image-with-questions` — 7 slides
Image with question list overlay.
```json
{
  "background_image": "Image/...",
  "slide_title": "10 Tips for Overcoming Imposter Syndrome",
  "content_title": "...",
  "questions": ["1. Reframe negative thoughts.", "2. Practice mindfulness..."],
  "dig_deeper": null
}
```
**Render**: Image background + `slide_title` + numbered list from `questions[]`.

### `image-with-radio` — 1 slide
Image + radio-button cognitive distortion quiz.
```json
{
  "image": "Image/...",
  "card_title": "Carla is disappointed...",
  "card_content": "Select the thoughts that might occur...",
  "message": "Great job identifying unhealthy negative thought habits.",
  "options": ["Healthy", "Filtering", "Personalizing", "Catastrophizing", "Blaming"],
  "questions": ["If they didn't select me...", "All I can think about..."]
}
```
**Render**: Image (not full-bleed — uses `image` not `background_image`) + `card_title`/`card_content` + radio per question from `options`.

### `image-with-select-option` — 1 slide
Image + multi-select with right/wrong feedback.
```json
{
  "image": "Image/...",
  "card_title": "Now let's turn this around.",
  "card_content": "Select the strategies that Carla could use...",
  "right_answer_message": "Try some of these strategies...",
  "wrong_answer_message": "You are getting there!",
  "right_answer_message_title": "Great work!",
  "wrong_answer_message_title": "Good Job!",
  "options": [{"option": "Plan to send a thank-you email...", "answer": "Right"}, ...]
}
```
**Render**: Image + `card_title`/`card_content` + selectable option chips. On submit, show `right_answer_message` or `wrong_answer_message`.

### `sparkle` — 2 slides
Celebration image with styled text.
```json
{
  "background_image": "Image/...",
  "audio": "Audio/...",
  "content_title": "Good Work!",
  "content": "Let's do another one!",
  "font_size": "Large"
}
```
**Render**: Full-bleed image + audio + `content_title` (large) + `content`. Celebratory styling.

### `special-image` — 2 slides
Image with dynamic personality word insertion.
```json
{
  "background_image": "Image/...",
  "audio": "Audio/...",
  "content": "Thank you, based on your survey results, it seems you lean more toward.",
  "content_title": "Let's explore some strategies...",
  "special_word": "introversion"
}
```
**Render**: Full-bleed image + audio + `content`/`content_title` with `special_word` highlighted.

### `special-image1` — 9 slides
Two-column content with colored background.
```json
{
  "background_image": "Image/...",
  "audio": "Audio/...",
  "slide_title": "Active Listening: Is there room for improvement?",
  "background_color": "#6DC3FF",
  "content1": "",
  "content2": "<div>...</div>",
  "special_word": "(optional)"
}
```
**Render**: Background with `background_color` tint + image + `content1`/`content2` (both HTML). `special_word` highlighted if present.

---

## Category C: QUESTION / INTERACTIVE (9 types, 78 slides)

### `question-answer` — 39 slides
Open text answer fields.
```json
{
  "slide_title": "Tell us your answers to each of these life questions.",
  "questions": ["What do you want your life to be like?", "Who do you want to be spending time with?"],
  "bulbExamples": [],
  "lhs_popup_header": null,
  "content_title": null,
  "is_message": null,
  "is_backpack": null, "is_task": null, "task_name": null
}
```
**Render**: `slide_title` header + textarea per `questions[]` string. Lightbulb popup if `bulbExamples` present.

### `question-answer1` — 6 slides
Structured prompts with word-labeled fields (e.g. N.E.X.T. acronym).
```json
{
  "questions": [
    {"question": "What is your new goal?", "word": "New Goal"},
    {"word": "Examine Options", "question": "What are the options?"}
  ],
  "content_title": "Now that you've practiced productive strategies, try our planning tool...",
  "is_backpack": true
}
```
**Render**: `content_title` header + card per question with `word` as bold label + textarea.

### `question-answer3` — 2 slides
Single open text story submission.
```json
{
  "content": "We'd love to hear the story behind your Superpower...",
  "content_title": "Care to Share?",
  "is_backpack": true
}
```
**Render**: `content_title` header + `content` paragraph + single large textarea.

### `question-with-example` — 5 slides
SAY/DO/BE commitment form with expandable example hints.
```json
{
  "card_title": "Make Life Changes",
  "card_content": "You may need to make some changes to live those principles.",
  "question_count": "3",
  "questions": [
    {"title": "Say", "question": "What will you commit to SAY every day?", "header": "Say Examples"},
    {"title": "Do", "question": "What is ONE thing you're going to DO?", "header": "Do Examples"},
    {"title": "BE", "question": "Who are you going to BE?", "header": "Be Examples"}
  ],
  "examples": [["What can I do to help you?", ...], ["I'm spending 30 minutes a day...", ...], [...]],
  "is_message": false, "is_question_title": "1"
}
```
**Render**: `card_title`/`card_content` header + per-question card with `title` tab, `question` label, textarea, expandable `examples` linked via index.

### `questions-example2` — 1 slide
Dual-column Q&A with popup examples. NOTE: typo `questionss` (double-s).
```json
{
  "slide_title": "Still not sure what makes you YOU? Ask Questions!",
  "content_title": "Ask Your Friends! Ask Your Family! Ask Your Colleagues!",
  "lhs_popup_header": "Soft Skills Examples",
  "rhs_popup_header": "Risk-taking Examples",
  "questionss": {"LHS": "What am I passionate about?...", "RHS": "..."}
}
```
**Render**: Two columns from `questionss.LHS` / `questionss.RHS` (handle typo). Popup buttons for each side.

### `choose-true-or-false` — 2 slides
True/false quiz per statement.
```json
{
  "slide_title": "Test your understanding...",
  "label_true": "TRUE", "label_false": "FALSE",
  "no_of_questions": "8",
  "questions": [
    {"question": "I'd speak up if this principle was violated", "answer": "True"}
  ]
}
```
**Render**: List of statements with True/False button pair each. Check against `answer`.

### `check-yes-or-no` — 5 slides
Checklist with conditional threshold feedback.
```json
{
  "question": ["Presented your work at a company event", "Attended a company event AND met 6+ people"],
  "content_title": "It's a myth that you can succeed based on performance alone...",
  "content": "Check the box for everything you've done in the last 12 months:",
  "moreThan2Message": "Well done! Keep it up!",
  "lessThan2Message": "Let's see how you can increase your visibility!",
  "option1": "Yes", "option2": "Not Yet",
  "is_backpack": true
}
```
**Render**: Checklist with `option1`/`option2` toggle per item. Show `moreThan2Message` or `lessThan2Message` based on count.

### `multiple-choice` — 6 slides
Multi-section quiz with nested options per category + bonus document.
```json
{
  "bonus_material": {"is_enable": true, "type": "Document", "document": "BonusMaterial/Document/...", "title": "Supercharge Your Career Checklist"},
  "card_title": "Select at least one action from each category below",
  "no_of_questions": "6",
  "questions": [
    {"question": "1) Proactively Communicate", "options": [{"option": "Check-in regularly...", "is_true": true}]}
  ]
}
```
**Render**: `card_title` + per-question section with radio/checkbox from `options[{option, is_true}]`. Download button if `bonus_material.is_enable`.

### `single-choice-with-message` — 1 slide
Scenario quiz with per-answer explanation.
```json
{
  "card_title": "In each scenario, choose the answer that an empathetic person would choose:",
  "no_of_questions": "3",
  "questions": [
    {
      "question": "Scenario 1: You notice a co-worker who appears overworked...",
      "options": [{"option": "Offer to help", "is_true": true}, {"option": "Leave them alone"}],
      "message": "When someone is struggling, offering to help is a bonding opportunity..."
    }
  ]
}
```
**Render**: Scenario text + radio options. On select, reveal `message` explanation.

---

## Category D: SELECTION (15 types, 73 slides)

### `select-option` — 2 slides
Free multi-select from option list.
```json
{
  "options": ["Ensure your work supports key business goals.", "Ask for feedback to refine and improve."],
  "card_title": "Review each action below and select the ones you are currently doing",
  "content_title": "Here are ideas for ways to celebrate:",
  "sparkle": "0", "font_size": "0"
}
```
**Render**: `card_title` header + selectable chip/card per option string.

### `select-option2` — 11 slides
Select from options with feedback text.
```json
{
  "content_title": "Where would you use AI to boost visibility this week?",
  "content_description": "Look at the options below and choose the one you would want to try.",
  "no_of_options": "5",
  "feedback": "Pick one and try it. What could you say that you normally wouldn't?",
  "options": ["Summarizing project updates for your manager", "Writing a reflection on what went well"]
}
```
**Render**: `content_title`/`content_description` + selectable options. On select, show `feedback`.

### `select-option3` — 9 slides
Multi-select + text input for custom answer.
```json
{
  "options": ["Good communication", "Feeling respected", "Feeling valued", "Feeling heard"],
  "card_title": "What do YOU believe makes a strong relationship?",
  "option_title1": "You can choose more than one option.",
  "option_title2": "What else may positively impact a relationship?",
  "message": "If you're stuck on an answer, reflect on your favorite relationships..."
}
```
**Render**: `card_title` + chips from `options` + free-text input (`option_title2` as label). `message` as hint.

### `select-option4` — 3 slides
Multi-select with right/wrong outcome message.
```json
{
  "card_title": "Choose 3 Awareness-Based Actions to Focus On:",
  "right_answer_message": "Great work!",
  "wrong_answer_message": "",
  "options": [{"option": "Pause and scan the room before speaking", "answer": "Right"}]
}
```
**Render**: `card_title` + selectable options. On submit, show right/wrong message based on selections.

### `select-option5` — 13 slides
Matching quiz — pair questions with options.
```json
{
  "no_of_questions": "4",
  "content_title": "Choose an AI strategy to solve each visibility challenge.",
  "options": ["Use AI to summarize key milestones.", "Use AI to rewrite updates."],
  "questions": ["I repeat tasks over and over.", "I'm nervous in meetings."]
}
```
**Render**: Left column: `questions[]`, right column: dropdown per question from `options[]`.

### `select-option6` — 7 slides
Single/multi-select from descriptive list.
```json
{
  "options": ["The Perfectionist: ...", "The Expert: ...", "The Natural Genius: ..."],
  "card_title": "We've discussed several recognized types of Imposter Syndrome.",
  "option_title": "Select the Imposter Syndrome type that fits you best. You can choose more than one!"
}
```
**Render**: `card_title` + `option_title` + selectable cards with descriptions.

### `select-option7` — 3 slides
Image + select with right/wrong feedback.
```json
{
  "image": "Image/...",
  "card_content": "Select all that apply",
  "content_on_image": "Which option(s) are best for developing your public speaking skills?",
  "right_answer_message": "Learning about public speaking is ideally delivered in a hands-on environment...",
  "wrong_answer_message": "The best way to master your public speaking skills is by taking a good class...",
  "options": [{"option": "Online Courses", "answer": "Wrong"}, {"option": "Instructor-led Classes", "answer": "Right"}]
}
```
**Render**: Image + `content_on_image` overlay + selectable options. Submit → right/wrong feedback.

### `select-option-with-button` — 5 slides
Scale/rating selector with button-style options.
```json
{
  "options": ["1️⃣ No one really knows", "2️⃣ A few people might", "3️⃣ My manager sees it", "4️⃣ My team knows", "5️⃣ My visibility is strong"],
  "card_title": "On a scale of 1–5, how clearly do others understand your current contributions?"
}
```
**Render**: `card_title` + large button per option (scale style).

### `select-option-with-message` — 1 slide
Paired right/wrong options with per-pair explanation.
```json
{
  "card_title": "Pick the attributes that leaders use to judge your readiness for growth:",
  "card_content": "Choose from the answers you think are success factors:",
  "message_count": "3",
  "data": [
    {"right_option": "I consistently deliver results...", "wrong_option": "I let my interest be known by applying for a job opening", "message": "Mere interest in a job isn't the same as demonstrating you are ready..."}
  ]
}
```
**Render**: Side-by-side option pairs from `data[]`. On select, reveal `message`.

### `select-one-word` — 2 slides
The core "One Word" selector exercise.
```json
{
  "slide_title": "Select the sentence with the WORD that will inspire you...",
  "question": "What decisions would I make if |WORD| was my frame to live the life I described?",
  "new_word": null, "is_message": null
}
```
**Render**: Prominent `slide_title` + `question` with `|WORD|` highlighted. Word selection interface.

### `select-range` — 3 slides
Likert-style range rating per scenario.
```json
{
  "no_of_questions": "3",
  "options": ["Forget It.", "Do I Have To?", "Just Get It Done.", "I Can Do This.", "Let's Do This!!"],
  "heading": "In each scenario, rate how motivated you feel...",
  "questions": ["Your boss approaches you and says: 'I can't believe management is making us do this...'"]
}
```
**Render**: `heading` + matrix: rows = `questions[]`, columns = `options[]` as scale labels.

### `select-the-best` — 1 slide
Image-pick quiz (choose the correct image).
```json
{
  "images": ["Image/202309120543300.png", "Image/202309120543301.png", "Image/202309120543302.png", "Image/202309120543303.jpg"],
  "slide_title": "Imagine that your boss assigned you to select the best drawing of a dog...",
  "right_message": "That's right: the dog in a field!",
  "wrong_message": "WRONG! Your boss was looking for a dog in a field.",
  "right_answer": "4"
}
```
**Render**: `slide_title` + image grid (4 images via SAS URL). Click → check vs `right_answer` index → show right/wrong message.

### `select-true-or-false` — 3 slides
True/false with per-answer explanation text.
```json
{
  "content": "Determine if each statement about Extraverts is True or False.",
  "content_title": "Select True or False for each statement about Extraverts.",
  "no_of_questions": "3", "font_size": "1",
  "questions": [
    {"question": "Extraverts avoid social interactions.", "answer": "False", "true_statement": "Actually, Extraverts love social interactions.", "false_statement": "You got it! Extraverts love social interactions."}
  ]
}
```
**Render**: `content_title` + per-question True/False buttons. On answer, show `true_statement` or `false_statement`.

### `three-word` — 2 slides
Select N words from a word bank.
```json
{
  "slide_title": "Which three words would frame your ideal life?",
  "words": "Joy, Calm, Rise, Growth, Grace, Trust, Courage, Light, Fearless, Finish, Possibility, Drive, Life, Love, Sad, Sorrow",
  "no_of_words": 3
}
```
**Render**: `slide_title` + word cloud chips from comma-split `words`. Max `no_of_words` selections.

### `one-word-select-option` — 2 slides
Pick how to activate "your word" in daily life.
```json
{
  "slide_title": "Select at least one thing you can do right now to have DYNAMIC_WORD begin to impact your life.",
  "options": ["Change your screensaver to DYNAMIC_WORD", "Put a sticky note with DYNAMIC_WORD on your mirror.", "NX DYNAMIC_WORD"]
}
```
**Render**: `slide_title` (replace DYNAMIC_WORD) + selectable action chips.

---

## Category E: FORM (5 types, 16 slides)

### `side-by-side-dropdown-selector` — 7 slides
Classify items via dropdown (e.g. Trigger vs Glimmer).
```json
{
  "no_of_questions": "10",
  "LHS_title": "Choose whether this activity is a TRIGGER or a GLIMMER",
  "RHS_title": "Trigger or Glimmer",
  "options": ["Trigger", "Glimmer"],
  "questions": ["Acceptance", "Loss of Control", "Appreciation", "Criticism", "Praise"]
}
```
**Render**: `LHS_title` header + table: left column = `questions[]`, right column = dropdown from `options[]` per row.

### `side-by-side-form` — 1 slide
Two free-text columns (Must Have / Won't Accept) with popup examples.
```json
{
  "slide_title": "Only you can decide what you MUST have in order to be happy...",
  "lhs_title": "3 Things I MUST HAVE", "rhs_title": "3 Things I WON'T ACCEPT",
  "lhs_placeholder": "Things I must have", "rhs_placeholder": "Things I won't accept",
  "no_of_answers": 3,
  "note": "We've seen many people write powerful Principles—click on the Bulb to see examples.",
  "lhs_popup_header": "Must have Examples", "rhs_popup_header": "Won't Accept Examples",
  "bulbExamples": {"LHS": ["I want to work with people I trust."], "RHS": ["I won't work for a bully..."]}
}
```
**Render**: Two-column layout. LHS/RHS each get `no_of_answers` textareas with placeholders. Lightbulb popup per side.

### `side-by-side-form2` — 6 slides
Two-column text input with placeholder questions.
```json
{
  "slide_title": "Introspection: Positive and Negative Self-Talk",
  "lhs_title": "Fill out 3 'negative self-talk' words or phrases...",
  "rhs_title": "Fill out 3 'positive affirmation self-talk' words or phrases...",
  "no_of_questions": "3",
  "questions": {
    "placeholderLHS": ["'I didn't get the job/promotion and didn't deserve it'"],
    "LHS": [" ", " ", " "],
    "RHS": [" ", " ", " "],
    "placeholderRHS": ["'I trust the universe and it wasn't the right time'"]
  }
}
```
**Render**: `slide_title` + two columns. LHS/RHS headers + textareas with `placeholderLHS`/`placeholderRHS`.

### `side-by-side-form4` — 1 slide
Two-column form with popup examples per side.
```json
{
  "slide_title": "Using DYNAMIC_WORD to propel you forward",
  "lhs_title": "What are 2 things you can do to leverage your DYNAMIC_WORD more at work:",
  "rhs_title": "What are 2 things you can do to leverage your DYNAMIC_WORD more in personal life:",
  "no_of_answers": 2,
  "lhs_popup_header": "Examples", "rhs_popup_header": "Examples",
  "bulbExamples": {"LHS": ["I will say 'no' to things that don't align with my superpower"], "RHS": ["..."]}
}
```
**Render**: Like `side-by-side-form` but with DYNAMIC_WORD replacement in titles.

### `side-by-side-print` — 1 slide
Read-only two-column layout for boss conversations.
```json
{
  "slide_title": "Have an 'Expectations' discussion with your boss...",
  "lhs_title": "Find out exactly WHAT measures will define your success. Ask your boss:",
  "rhs_title": "Find out exactly HOW your boss wants you to achieve those metrics. Ask your boss:",
  "no_of_questions": "6",
  "questions": {
    "LHS": ["What are the Key Performance Indicators (KPIs)...?"],
    "RHS": ["When should it be achieved?", "How should it be reported?"]
  }
}
```
**Render**: Two-column read-only list (no inputs). `LHS`/`RHS` as bullet lists.

---

## Category F: ENGAGEMENT / NARRATIVE (14 types, 107 slides)

### `greetings` — 34 slides
Coach letter with advisor attribution.
```json
{
  "greetings": "Gratitude works best when it's genuine. If you're grateful, say it.",
  "advisor_content": "Your advisor at myNextory",
  "advisor_name": "XOXO,"
}
```
**Render**: Styled letter card — `greetings` as body text, `advisor_name` as sign-off, `advisor_content` as role line.

### `take-away` — 44 slides
Key lesson takeaway with rating prompt.
```json
{
  "message": "Make celebration the best kind of habit. And do it every day—for little things and big ones.",
  "message_1": "Your opinion matters to us!",
  "message_2": "Was this a meaningful and worthwhile exercise?"
}
```
**Render**: Summary card — `message` as key takeaway (large text), `message_1`/`message_2` as rating prompt. Replace `DYNAMIC_WORD` if present.

### `decision` — 1 slide
Branching choice cards (2-3 paths).
```json
{
  "decision_count": 3,
  "card_title": "If you're like most of us, your real life may not look exactly like your Principles right now.",
  "decision": [
    {"title": "Make Life Changes", "content": "You may need to make some changes..."},
    {"title": "Accept Less than Ideal Circumstances", "content": "You may need to accept..."},
    {"title": "I'm aligned with my Principles.", "content": "If your life aligns well..."}
  ]
}
```
**Render**: `card_title` header + clickable path cards from `decision[{title, content}]`.

### `decision2` — 1 slide
Two-path choice card.
```json
{
  "content_description": "Perhaps you still don't have clear expectations or measures of your success...",
  "no_of_cards": 2,
  "cards_titles": ["Let's dig deeper on expectations", "I'm clear on my expectations—what's next"]
}
```
**Render**: `content_description` + two clickable cards from `cards_titles[]`.

### `celebrate` — 1 slide
Celebration with action prompt.
```json
{
  "content_title": "Celebrate",
  "content_description": "At your next team meeting, call out ONE thing worth celebrating.",
  "content_heading": "Be a force for GOOD:",
  "lhs_title": "One thing worth celebrating at our next meeting.",
  "no_of_cards": 1, "content_count": 3
}
```
**Render**: Celebration styling + `content_title`/`content_heading`/`content_description` + textarea for `lhs_title`.

### `chat-interface` — 1 slide
Simulated dialogue Q&A bubbles.
```json
{
  "content_title": "Informal learning opportunities at your company",
  "options": [
    {"question": "Formal and informal learning benefit the head and the heart. That's it, right?", "answer": "NOT SO FAST. Another way we learn is by doing."},
    {"question": "I AM doing…a lot already!", "answer": "Yes, but a raised bar for your skills means doing more..."}
  ]
}
```
**Render**: Chat bubble layout — alternating question (user) and answer (bot) bubbles from `options[]`.

### `one-word-apprication` — 13 slides
Display user's chosen word with affirmation text.
```json
{
  "slide_title": "Consistent choices that will cut through the clutter...",
  "appreciation": "The word DYNAMIC_WORD will guide you as you make decisions..."
}
```
**Render**: Large styled display of DYNAMIC_WORD + `appreciation` text (replace DYNAMIC_WORD token).

### `one-word-content-box` — 2 slides
Three info boxes about the word.
```json
{
  "content1": "The WORD that will inspire, guide and reframe the next year of your life: DYNAMIC_WORD",
  "content2": "myNextory will help you by tracking your answers to questions in the weeks and months ahead.",
  "content3": "We can't wait to be on this journey with you."
}
```
**Render**: Three styled info cards — `content1`, `content2`, `content3` (replace DYNAMIC_WORD).

### `show-gratitude` — 4 slides
Gratitude action cards with popup examples.
```json
{
  "content_title": "Show gratitude to your family.",
  "content_description": "Our family members are often the reason why we work so hard.",
  "no_of_cards": 3,
  "card_title": "Ways to show gratitude to your family:",
  "lhs_popup_header": "Ways to show gratitude",
  "bulbExamples": {"LHS": ["More than anything, your child craves your time and approval."]}
}
```
**Render**: `content_title`/`content_description` + `no_of_cards` textareas + lightbulb popup from `bulbExamples`.

### `people-you-would-like-to-thank` — 1 slide
List 3 people to thank.
```json
{
  "content_title": "The 3-Minute Magnifying Glass",
  "content_description": "Send a text message to three colleagues...",
  "no_of_cards": "3",
  "card_label": "Name 3 people you would like to thank",
  "content_count": 1
}
```
**Render**: `content_title`/`content_description` + `no_of_cards` text inputs with `card_label`.

### `take-to-lunch` — 2 slides
Commit to take someone to lunch.
```json
{
  "content_title": "The Great Lunch",
  "content_description": "Don't underestimate the power of simply being together...",
  "no_of_cards": 1,
  "lhs_title": "Person I want to take to lunch this month",
  "rhs_title": "Person I want to take to lunch next month"
}
```
**Render**: `content_title`/`content_description` + two text inputs: `lhs_title` / `rhs_title`.

### `build-your-network` — 1 slide
Expandable network-building action checklist.
```json
{
  "content": "Click the word to learn more. Check the box to add it to your to-do list.",
  "content_title": "Here are ways you can increase your visibility and build your network.",
  "options": [{"card_title": "In your company", "no_of_question": "3", "question": [...], "answer": [...]}]
}
```
**Render**: Expandable accordion — `options[].card_title` as section header, nested checklist from `question[]`/`answer[]`.

### `answered-stakeholders` — 1 slide
Display previously saved stakeholder answers + bonus article.
**Keys**: `bonus_material` (with embedded HTML article), `content`, `content_title`
**Render**: Read-only display of saved stakeholder answers + downloadable bonus material if `bonus_material.is_enable`.

---

## Category G: STAKEHOLDER (4 types, 24 slides)

### `stakeholders` — 1 slide
Avatar picker grid — select up to N stakeholders.
```json
{
  "slide_title": "Besides you, who are the influencers that are key to your success? Select up to 3.",
  "select_count": "3",
  "stakeholders": [
    {"name": "Your Boss", "image": "Image/stakeholder020230912051100.png"},
    {"name": "Direct Reports", "image": "Image/stakeholder120230912051100.png"},
    {"name": "Co-Workers", "image": "Image/stakeholder220230912051100.png"},
    {"name": "Partner/Spouse", "image": "Image/stakeholder320230912051100.png"},
    {"name": "Your Family", "image": "Image/stakeholder420230912051100.png"},
    {"name": "Your Customers", "image": "Image/stakeholder520230912051100.png"},
    {"name": "Your Community", "image": "Image/stakeholder620230912051100.png"},
    {"name": "Spiritual Community", "image": "Image/stakeholder720230912051100.png"},
    {"name": "Not-For-Profit", "image": "Image/stakeholder820230912051100.png"},
    {"name": "Other Groups", "image": "Image/stakeholder920230912051100.png"},
    {"name": "User"}
  ]
}
```
**Render**: `slide_title` + avatar grid. Each `stakeholders[]` → circular image (SAS URL) + name. Select up to `select_count`.

### `stakeholders-selected` — 1 slide
Confirmation after stakeholder selection.
```json
{
  "slide_title": "There they are: four of the most important people in your support community, including you.",
  "is_headsup": 1,
  "heads_up": "Let's get intentional about what these relationships will be looking like 12 months from now."
}
```
**Render**: `slide_title` + display selected stakeholder avatars + heads-up callout.

### `stakeholder-question` — 11 slides
Stakeholder-specific reflection question (HTML content).
```json
{
  "slide_title": "Consider these questions.",
  "question": "<ul><li>What will your boss say about you, your energy, your engagement?</li>...</ul>",
  "card_title": "One Year From Now, what will YOU be saying about your life and work if we get this right?",
  "stakeholder_id": "10",
  "stakeholder_name": "User"
}
```
**Render**: Show stakeholder avatar/name context + `card_title` header + `question` as innerHTML.

### `stakeholder-question-answer` — 11 slides
Open-text answers for stakeholder context.
```json
{
  "slide_title": "Complete the following as best you can.",
  "is_headsup": 1,
  "heads_up": "We'll remind you of this along the way",
  "questions": ["Why is your boss instrumental to your success?", "What will your boss be saying about you a year from now?"],
  "placeholders": ["My pay.", "My career growth and advancement.", "You're doing a great job..."],
  "stakeholder_id": "...",
  "stakeholder_name": "..."
}
```
**Render**: Stakeholder avatar/name + `slide_title` + textarea per `questions[]` with `placeholders[]` + heads-up callout.

---

## Azure Blob Path Patterns

| Content Type | Path Pattern | Example |
|---|---|---|
| Images | `Image/{timestamp}.{ext}` | `Image/20230912060107.png` |
| Audio | `Audio/{timestamp}.{ext}` | `Audio/20250911104654.mp3` |
| Video | `Video/{id}/{slug}.mp4` | `Video/1/production-our-first--20250801065015.mp4` |
| Thumbnails | `Video/Thumbnail/Thumbnail-{id}-{ts}.jpg` | `Video/Thumbnail/Thumbnail-1-20230831013919.jpg` |
| Stakeholder images | `Image/stakeholder{n}{ts}.png` | `Image/stakeholder020230912051100.png` |
| Bonus documents | `BonusMaterial/Document/{file}` | `BonusMaterial/Document/...` |

**Container fallback**: Try `staging` first, then `production`. Both exist in Azure Storage account `productionmynextory`.

---

## Video Library Integration

118 slides have `video_library_id` → `video_libraries` table:
- **158 total records** (133 active, 25 soft-deleted)
- **ALL 118 referenced videos have blob paths and thumbnails**
- Video blob path in `video_libraries.video` column
- Thumbnail in `video_libraries.thumbnail` column
- Streaming URL in `video_libraries.url` (138 have URLs)
- Generate SAS URL from blob path, same container fallback as images
