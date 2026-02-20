# MSSQL-to-MariaDB Migration Audit

**Audited**: 2026-02-20
**Source**: `app-mynextory-backup-utf8.sql` (MSSQL backup, dated 2026-02-09)
**Target**: MariaDB database `baap` (loaded via `bootstrap.sh` from `baap.sql.gz`)

---

## Executive Summary

The migration from MSSQL to MariaDB lost **13,266 rows (14.9%)** across **29 of 38 tables**. The losses fall into three categories:

1. **Content hierarchy completely replaced with dummy data** — journeys, chapters, lessons were seed-generated on 2026-02-19, not migrated
2. **Admin/organizational tables zeroed out** — clients, coaches, departments, admin users all empty
3. **Earliest ~99 user records and their associated data dropped** — IDs 1-173 in nx_users missing

**Root cause**: Naive regex in Python conversion scripts (`mssql_to_mariadb.py`, `load_mssql_dump.py`) breaks on backticks/quotes in string values, causing truncated INSERT statements. The current `bootstrap.sh` bypasses these scripts by loading a pre-dumped mysqldump, but that dump was taken from an already-corrupted state.

---

## Full Comparison Table

### Section A: Total Data Loss (12 tables, 462 rows)

| Table | MSSQL Rows | MariaDB Rows | Business Impact |
|-------|-----------|-------------|-----------------|
| departments | 97 | 0 | Organizational hierarchy broken |
| notification_histories | 94 | 0 | Historical notification delivery records |
| lesson_details | 86 | 0 | **CRITICAL** — bridge table for lesson_slides, tasks |
| dynamic_sms_details | 53 | 0 | Template-based SMS messages |
| mail_communication_details | 45 | 0 | Support tickets and internal comms |
| clients | 37 | 0 | **CRITICAL** — all 37 client companies gone |
| nx_password_resets | 19 | 0 | Transient (low impact) |
| sms_schedules | 12 | 0 | Scheduled SMS templates |
| coach_availabilities | 9 | 0 | Coach scheduling data |
| coaches | 5 | 0 | **CRITICAL** — all 5 coaches gone |
| coach_profiles | 4 | 0 | Coach expertise/bio data |
| nx_admin_users | 1 | 0 | The single admin user (support@mynextory.com) |

### Section B: Partial Data Loss (17 tables, 12,804 rows lost)

| Table | MSSQL | MariaDB | Lost | Loss % | Notes |
|-------|-------|---------|------|--------|-------|
| backpacks | 11,951 | 5,562 | 6,389 | 53.5% | Core learning interaction data |
| sms_details | 5,744 | 1,209 | 4,535 | 79.0% | Historical comm logs |
| nx_user_onboardings | 571 | 196 | 375 | 65.7% | **CRITICAL** — EPP assessment results |
| chatbot_histories | 291 | 27 | 264 | 90.7% | Chatbot conversations |
| tasks | 2,928 | 2,751 | 177 | 6.0% | Lesson tasks |
| video_libraries | 158 | 3 | 155 | 98.1% | Azure video metadata |
| documents | 144 | 40 | 104 | 72.2% | Uploaded documents |
| nx_users | 1,563 | 1,463 | 100 | 6.4% | Earliest 99 users (IDs 1-173) |
| chatbot_documents | 106 | 7 | 99 | 93.4% | Chatbot knowledge base |
| employees | 1,566 | 1,467 | 99 | 6.3% | Mirrors nx_users loss |
| nx_journal_details | 112 | 13 | 99 | 88.4% | User journal entries |
| nx_user_ratings | 3,356 | 3,257 | 99 | 2.9% | Lesson ratings |
| old_ratings | 499 | 400 | 99 | 19.8% | Historical ratings |
| lesson_slides | 620 | 521 | 99 | 15.3% | Slide content |
| nx_lessons | 90 | 25 | 65 | 72.2% | **Replaced** with dummy data |
| nx_chapter_details | 46 | 8 | 38 | 82.6% | **Replaced** with dummy data |
| nx_journey_details | 16 | 4 | 12 | 75.0% | **Replaced** with dummy data |

### Section C: Preserved / Grew

| Table | MSSQL | MariaDB | Notes |
|-------|-------|---------|-------|
| activity_log | 58,504 | 67,972 | +9,468 post-migration entries |
| client_coach_mappings | 17 | 17 | Exact match (but references missing clients) |

### Section D: Both Empty (7 tables)

chatbot_sessions, client_password_resets, coach_password_resets, jobs, mail_transfers, meeting_attendees, meetings

---

## Content Hierarchy: Dummy Data vs Real Data

The content tables contain **completely fabricated data**, not migrated data:

### Journeys (nx_journey_details)

| MSSQL (real) | MariaDB (dummy) |
|-------------|-----------------|
| ID 2: "Win at Work" (2023-07-25, Admin) | ID 1: "Leadership & Management" (2026-02-19) |
| ID 13: "Lessons" (2023-11-13, Coach 6) | ID 2: "Communication & Teamwork" (2026-02-19) |
| ID 18: "Superskill: AI" | ID 3: "Resilience & Wellbeing" (2026-02-19) |
| ID 19: "Motivation Minute" | ID 4: "Career Growth & Sales" (2026-02-19) |
| + 12 deleted test journeys | |

**4 active MSSQL journeys, 12 deleted. 4 dummy MariaDB journeys. Zero overlap.**

### Chapters (nx_chapter_details)

MSSQL had 33 active chapters (IDs 2, 23-30, 40-73) with real names: "Foundations", "The Amazing You", "Super Skill: EQ", "Imposter Syndrome", "Reading the Room", "AI at Work", etc.

MariaDB has 8 dummy chapters (IDs 1-8): "Foundations of Leadership", "Strategic Management", "Active Listening", etc.

### Lessons (nx_lessons)

MSSQL had 44 active lessons (IDs 5-119) with real names: "Introduction", "One Word", "Principles", "The Introvert's Style", "Working With Introverts", "Imposter Syndrome", "Networking", "Reading the Room", "AI at Work", etc.

MariaDB has 25 dummy lessons (IDs 1-25): "Setting Team Goals", "Delegation Skills", "Decision Making Under Pressure", etc.

### lesson_details — THE CRITICAL MISSING TABLE

| Metric | MSSQL | MariaDB |
|--------|-------|---------|
| Total rows | 86 | **0** |
| Active (non-deleted) | 71 | 0 |
| Published status | 65 | 0 |

This table is the **bridge between nx_lessons and lesson_slides**. With 0 rows:
- ALL 521 lesson_slides have broken `lesson_detail_id` FK references
- 2,787 of 2,829 tasks have broken `lesson_detail_id` FK references
- The entire content hierarchy chain is severed

---

## Critical Business Data Lost

### Clients (37 companies — ALL GONE)

Amazon, BCS, Barracuda, Bill Filip and Co, Carmichael Lynch, Centinel Spine, Conner Strong, Copado, Eagleville Hospital, Hajoca, Highmark DBG, Highmark Inc, Independence Blue Cross, Jefferson Healthcare, Kachava, Omlie, One Digital, Placers, Shadow Her, Subaru, The Chamber of Commerce for Greater Philadelphia, Thrive Wealth, TopStack Group, United Concordia Dental, myNextory, and others.

Each record has: employer_id, company_logo, company_name, addresses, contacts, emails, passwords, status.

### Coaches (5 coaches — ALL GONE)

- Sabine Gillert (sabine@mynextory.com) — General Coaching, Customer Service/Success
- Dee Raviv (dee@mynextory.com) — Executive Coaching, Women, Transitional Coaching
- coach@nx.com, Scotty (scotty@mynextory.com), mynextory@gmail.com

### EPP Assessment Results (375 onboardings — 65.7% LOST)

Each lost `nx_user_onboardings` record contains irreplaceable Criteria Corp EPP psychometric scores: EPPAchievement, EPPMotivation, EPPCompetitiveness, EPPManagerial, EPPAssertiveness, EPPExtroversion, EPPCooperativeness, EPPPatience, EPPSelfConfidence, EPPConscientiousness, EPPOpenness, EPPStability, EPPStressTolerance. These cost money per test and cannot be regenerated without re-testing.

### Founding Users (99 earliest users — IDs 1-173)

Original Thrive Wealth users from 2023-02-08 (platform launch day): jack@thrivewealth.com, ian@thrivewealth.com, matt@thrivewealth.com, mstanton@thrivewealth.com, etc.

---

## Referential Integrity Damage

| Table | Total Rows | Orphaned | Orphan % | Broken FK Target |
|-------|-----------|----------|----------|-----------------|
| lesson_slides | 521 | **521** | **100%** | lesson_detail_id → empty lesson_details |
| lesson_slides | 521 | **109** | 21% | video_library_id → missing video_libraries |
| tasks | 2,829 | **2,787** | **98.5%** | lesson_detail_id → empty lesson_details |
| backpacks | 5,833 | **1,021** | 17.5% | nx_journey_detail_id → missing journeys |
| backpacks | 5,833 | **1,724** | 29.6% | nx_lesson_id → missing lessons |
| sms_details | 1,323 | **207** | 15.6% | nx_lesson_id → missing lessons |
| client_coach_mappings | 17 | **17** | 100% | client_id → empty clients |

---

## Root Cause: Conversion Script Flaws

### The Scripts

| Script | Lines | Purpose | Status |
|--------|-------|---------|--------|
| `mssql_to_mariadb.py` | 354 | Full dump conversion | **BROKEN** — naive regex |
| `load_mssql_dump.py` | 299 | Table-by-table loading | **BROKEN** — same flaws |
| `bootstrap.sh` | 33 | Load pre-dumped .sql.gz | **ACTIVE** — bypasses scripts |

### Core Bug: String Handling

Both Python scripts use identical naive regex for string conversion:

```python
# Removes N-prefix but doesn't adjust escaping
val_part = re.sub(r"N'", "'", val_part)

# Too simplistic — doesn't handle nested quotes/backticks
val_part = re.sub(r"CAST\('([^']*)'\s+AS\s+\w+(?:\([^)]*\))?\)", r"'\1'", val_part)
```

When SQL Server data contains backticks, apostrophes, or Unicode in string values, the regex produces malformed SQL that MariaDB truncates or rejects.

### Evidence

Commit 31c889d (2026-02-18): *"Original dump had truncated INSERT statements in activity_log (Error rows with unescaped backticks/quotes). Re-dumped with --hex-blob and proper escaping."*

The fix replaced the converted dump with a clean `mysqldump` from the already-loaded (but corrupted) database — preserving whatever survived initial loading but not recovering what was already lost.

### Other Flaws

- `errors='replace'` in file reading silently drops problematic characters
- No hex-encoding for binary data
- No error counting or failed-row logging
- `mssql_to_mariadb.py` only adds AUTO_INCREMENT if PRIMARY KEY explicitly defined
- No validation of row counts before/after

---

## Video Libraries: 155 of 158 Lost

Only 3 survived in MariaDB:
- ID 110: "tet" (soft-deleted test)
- ID 152: "videotest" (soft-deleted test)
- ID 163: "Reading the Room Video 2" (active — the ONE working video)

The 155 missing records contain Azure Media Services streaming metadata (video blob paths, thumbnail paths, transcripts, streaming locator URLs). The actual .mp4 files still exist in Azure Blob Storage — only the DB metadata to locate them is lost.

See also: `.claude/knowledge/video-data-model.md` for the dynamic blob inventory fallback that resolves videos without DB records.

---

## Restoration Contract

### Records to Restore (order matters for FK integrity)

| Step | Table | Records | Action | Priority |
|------|-------|---------|--------|----------|
| 1 | nx_journey_details | 16 | DELETE 4 dummy + INSERT 16 real | CRITICAL |
| 2 | nx_chapter_details | 46 | DELETE 8 dummy + INSERT 46 real | CRITICAL |
| 3 | nx_lessons | 91 | DELETE 25 dummy + INSERT 91 real | CRITICAL |
| 4 | lesson_details | 86 | INSERT 86 (table empty) | CRITICAL |
| 5 | clients | 37 | INSERT 37 | CRITICAL |
| 6 | coaches | 5 | INSERT 5 | CRITICAL |
| 7 | coach_profiles | 4 | INSERT 4 | CRITICAL |
| 8 | video_libraries | 155 | INSERT 155 (keep 3 survivors) | HIGH |
| 9 | lesson_slides | 99 | INSERT 99 missing | HIGH |
| 10 | nx_users | ~483 | INSERT missing early users | HIGH |
| 11 | nx_user_onboardings | ~351 | INSERT missing (EPP scores) | HIGH |
| 12 | departments | 97 | INSERT 97 | MEDIUM |
| 13 | coach_availabilities | 9 | INSERT 9 | MEDIUM |
| 14 | backpacks | ~6,389 | INSERT missing | MEDIUM |
| 15 | employees | ~99 | INSERT missing | MEDIUM |
| 16 | nx_journal_details | ~99 | INSERT missing | MEDIUM |
| 17 | documents | ~104 | INSERT missing | MEDIUM |
| 18 | chatbot_documents | ~99 | INSERT missing | LOW |
| 19 | chatbot_histories | ~264 | INSERT missing | LOW |
| 20 | sms_details | ~4,535 | INSERT missing | LOW |
| 21 | notification_histories | 94 | INSERT 94 | LOW |
| 22 | dynamic_sms_details | 53 | INSERT 53 | LOW |
| 23 | mail_communication_details | 45 | INSERT 45 | LOW |
| 24 | nx_user_ratings | ~99 | INSERT missing | LOW |
| 25 | old_ratings | ~99 | INSERT missing | LOW |
| 26 | tasks | ~177 | INSERT missing | LOW |
| 27 | nx_password_resets | 19 | INSERT 19 | LOW |
| 28 | sms_schedules | 12 | INSERT 12 | LOW |
| 29 | nx_admin_users | 1 | INSERT 1 | LOW |

**Total: ~13,266 records across 29 tables**

### Pre-Restoration Cleanup

Before restoring real data:
1. DELETE dummy `nx_lessons` (IDs 1-25)
2. DELETE dummy `nx_chapter_details` (IDs 1-8)
3. DELETE dummy `nx_journey_details` (IDs 1-4)
4. DELETE `tory_content_tags` referencing dummy lesson_detail_ids (if any)
5. SET `SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO'` to preserve original IDs

### Approach: Smart MSSQL Converter

The existing Python scripts are too broken to reuse. A new conversion approach should:
1. Parse MSSQL INSERT per table, not generic regex
2. Use parameterized inserts or proper SQL escaping library
3. Hex-encode binary/problematic string data
4. Validate row counts table-by-table after each import
5. Log and report any failed rows (don't silently drop)

### Post-Restoration

After restoring:
1. Re-run `tory_content_tags` pipeline on real lesson_detail_ids
2. Re-verify video_library_id references in lesson_slides
3. Update `tory_learner_profiles` and `tory_recommendations` if they reference dummy content
4. Re-dump `baap.sql.gz` from the restored database for future `bootstrap.sh` use
