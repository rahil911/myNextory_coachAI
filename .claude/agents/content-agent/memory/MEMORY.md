# Content Agent Memory

## My Ownership
(Will be populated as the agent starts working)

## Key Decisions
(Will be populated as the agent makes choices)

## Schema Knowledge
Key tables in my domain:
- nx_journey_details: Top-level learning paths, hub with 10 refs
- nx_chapter_details: Mid-level units within journeys, hub with 13 refs
- nx_lessons: Atomic learning units, hub with 13 refs
- lesson_details: Detailed lesson content
- lesson_slides: Slides within lessons
- video_libraries: Video content library
- backpacks: User-collected learning materials (5833 rows)
- documents: Uploaded documents
- chatbot_documents: Knowledge base documents

Content hierarchy: Journey > Chapter > Lesson > Slide/Video

## Upstream Dependencies
- identity-agent: nx_users referenced via created_by in journey/chapter/lesson tables

## Dependents to Notify on Changes
- engagement-agent, comms-agent

## Recent Changes
(Will be populated as the agent completes tasks)
