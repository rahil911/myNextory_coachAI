# Enhanced RAG System — Access Guide

## Repository
- **URL**: `https://github.com/rahil911/enhanced-rag-system`
- **Branch**: `main`
- **Root path**: `enhanced_rag/`
- **Status**: Private repo, battle-tested production code

## Authentication
The GitHub token is available as `$GITHUB_TOKEN` environment variable (auto-loaded from `.env` by spawn.sh).

## How to Download Files

### Single file (raw content):
```bash
curl -sH "Authorization: token $GITHUB_TOKEN" \
  "https://raw.githubusercontent.com/rahil911/enhanced-rag-system/main/enhanced_rag/FILENAME" \
  -o /home/rahil/Projects/baap/.claude/rag/FILENAME
```

### List directory contents:
```bash
curl -sH "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/rahil911/enhanced-rag-system/contents/enhanced_rag" | python3 -m json.tool
```

### All 8 core files at once:
```bash
mkdir -p /home/rahil/Projects/baap/.claude/rag
for f in shared_vector_manager.py incremental_ingestion.py hybrid_query_engine.py \
         chat_manager.py user_backpack_ingestion.py user_manager_optimized.py \
         avatar_manager.py config.py; do
  curl -sH "Authorization: token $GITHUB_TOKEN" \
    "https://raw.githubusercontent.com/rahil911/enhanced-rag-system/main/enhanced_rag/$f" \
    -o "/home/rahil/Projects/baap/.claude/rag/$f"
  echo "Downloaded: $f"
done
```

## Core Files and What They Do

| File | Purpose | Adapt For |
|------|---------|-----------|
| `shared_vector_manager.py` | Singleton FAISS index, thread-safe, 15-min cache TTL | Global lesson content store, fed by Content Processor |
| `incremental_ingestion.py` | Azure ETag change detection, token-based chunking, bloom filter dedup | Content Processor pipeline — lesson_slides instead of PDFs |
| `hybrid_query_engine.py` | Parallel global + personal FAISS search, 1.5x personal boost, smart merge | Core engine for BOTH Curator and Companion AI |
| `chat_manager.py` | Session history, context-aware prompt reformulation | Conversation history for both AI roles |
| `user_backpack_ingestion.py` | Per-user document processing, 800 token chunks | Per-learner overlay from backpack + EPP + path data |
| `user_manager_optimized.py` | Lightweight per-user overlays (2KB), MD5 hash dirs, LRU cache | Per-learner FAISS overlay management |
| `avatar_manager.py` | HeyGen API WebRTC integration | Future: Companion AI avatar (Phase D) |
| `config.py` | Centralized config (models, embedding dims, costs) | Adapted for MyNextory models and settings |

## Key Architecture Decisions in the RAG Repo

1. **Shared FAISS store** (singleton) — one global index for all content, thread-safe reads
2. **Per-user overlays** — lightweight 2KB FAISS indexes per user (backpack, personal data)
3. **Hybrid search** — parallel query against global + personal, personal results get 1.5x score boost
4. **Cost optimization** — 99.4% reduction at scale via embeddings cache, incremental updates, bloom filter dedup
5. **Embedding model**: OpenAI `text-embedding-3-small` ($0.02/1M tokens)
6. **Chat model**: `gpt-4o-mini` (their default — we replace with Claude Sonnet/Opus)
7. **Chunk strategy**: 1000 tokens with 200 overlap (mechanical) — we improve with semantic chunking from Content Processor

## Adaptation Strategy

**Use as-is**: FAISS store architecture, user overlay pattern, hybrid query engine, chat manager session handling
**Replace**: OpenAI embeddings → keep or switch (decision pending), GPT-4o-mini → Claude Sonnet/Opus
**Enhance**: Mechanical chunking → semantic chunking (LLM understands slide boundaries), add EPP-aware personal overlays
**Skip for now**: avatar_manager.py (Phase D)

## MyNextory-Specific Data Sources (not in RAG repo)

| Data Source | Table | Rows | Use In |
|-------------|-------|------|--------|
| Lesson slides | `lesson_slides` | 620 (86 lessons) | Global FAISS index (via Content Processor) |
| Raw EPP scores | `nx_user_onboardings.assesment_result` | 488 users | Source of truth for EPP (JSON from Criteria Corp API, scores prefixed `EPP*`) |
| Parsed EPP profiles | `tory_learner_profiles.epp_summary` | 8 processed | Pre-loaded static context (parsed from raw) |
| Onboarding Q&A | `nx_user_onboardings` | 571 | Learner profile context (why_did_you_come, best_boss, success_look_like, own_reason, etc.) |
| Backpack reflections | `backpacks` | 11,679 from 327 learners | Per-learner personal FAISS overlay. `data` is JSON array of answers. Linked to lesson_slide_id. |
| Activity log | `activity_log` | 58K | Progress tracking, engagement signals |
| Path/recommendations | `tory_recommendations` | varies | Current learning path context |
| Learner profiles | `tory_learner_profiles` | 8 | Pre-loaded static context (profile_narrative, trait_vector, etc.) |

### CRITICAL TABLE NAME NOTES
- Backpack table is `backpacks` (plural), NOT `backpack`
- Onboarding table is `nx_user_onboardings`, NOT `onboarding_question_answers`
- No standalone `epp_scores` table — EPP lives inside `nx_user_onboardings.assesment_result` as raw JSON
- `backpacks.created_by` maps to the learner (nx_users.id), `backpacks.user_type` = 'User'
- `backpacks.data` is a JSON array of answers, `backpacks.form_type` indicates the slide type responded to
