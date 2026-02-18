#!/usr/bin/env python3
"""
Phase 2b: Domain Mapper for MyNextory Coaching/Learning Platform

Maps 38 database tables to business concepts (domain entities) for the
ownership knowledge graph. Creates CONCEPT nodes that enable semantic
queries like get_blast_radius("User") or get_blast_radius("Journey").

Domain model:
  - identity:      Users, clients, coaches, employees, admin users, passwords
  - learning:      Journeys, lessons, chapters (the core learning path)
  - content:       Slides, questions, elements, backpacks, documents, video
  - engagement:    Meetings, tasks, ratings, journals
  - communication: SMS, notifications, mail, chatbot, activity log
  - platform:      Migrations, failed_jobs, mappings, departments

Output: .claude/kg/seeds/concepts.csv
"""

import json
import csv
from pathlib import Path
from collections import defaultdict


BASE = Path(__file__).resolve().parent.parent.parent  # ~/Projects/baap
DISCOVERY = BASE / ".claude" / "discovery"
SEEDS = BASE / ".claude" / "kg" / "seeds"


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def build_row_count_map(profile: dict) -> dict[str, int]:
    """Table name -> row count."""
    return {t["name"]: t.get("row_count", 0) for t in profile["tables"]}


def build_relationship_graph(relationships: dict) -> dict[str, set[str]]:
    """Table -> set of tables it connects to (bidirectional)."""
    graph = defaultdict(set)
    for rel in relationships.get("relationships", []):
        ft = rel["from_table"]
        tt = rel["to_table"]
        graph[ft].add(tt)
        graph[tt].add(ft)
    return graph


def build_hub_table_map(relationships: dict) -> dict[str, int]:
    """Table -> total reference count for hub tables."""
    return {
        h["table"]: h["total_references"]
        for h in relationships.get("hub_tables", [])
    }


# ---------------------------------------------------------------------------
# Hand-crafted concept definitions for MyNextory
# ---------------------------------------------------------------------------
# Each concept is a semantic grouping of tables with domain knowledge applied.
# The key insight: this is a COACHING PLATFORM, not e-commerce.
#
# Table assignment is EXPLICIT (not algorithmic prefix-matching) because:
#   1. Tables have inconsistent prefixes (nx_ vs bare vs mixed)
#   2. Some tables belong to multiple semantic areas but need one primary owner
#   3. Domain knowledge (coaching platform) matters more than naming patterns
# ---------------------------------------------------------------------------

CONCEPT_DEFINITIONS = [
    {
        "id": "User",
        "domain": "identity",
        "description": "Core user entity - employees/learners who take journeys and complete lessons. Hub table with 20 references. Links to clients, coaches, onboarding, ratings, and all learning activity.",
        "tables": ["nx_users", "nx_user_onboardings"],
        "related_concepts": ["Client", "Coach", "Employee", "Journey", "Rating", "ActivityLog"],
    },
    {
        "id": "Client",
        "domain": "identity",
        "description": "Client organization (employer/company) that purchases coaching programs. Clients own users, map to coaches, and manage departments. Hub with 5 incoming references.",
        "tables": ["clients", "client_password_resets"],
        "related_concepts": ["User", "Coach", "Employee", "Department", "ClientCoachMapping"],
    },
    {
        "id": "Coach",
        "domain": "identity",
        "description": "Coach entity with profile and availability. Coaches are mapped to clients and attend meetings. Hub with 4 incoming references.",
        "tables": ["coaches", "coach_profiles", "coach_availabilities", "coach_password_resets"],
        "related_concepts": ["Client", "Meeting", "ClientCoachMapping", "User"],
    },
    {
        "id": "Employee",
        "domain": "identity",
        "description": "Employee within a client organization. Linked to nx_users and departments. Represents the learner role within a company.",
        "tables": ["employees"],
        "related_concepts": ["User", "Client", "Department"],
    },
    {
        "id": "AdminUser",
        "domain": "identity",
        "description": "Platform administrator with elevated privileges for managing the coaching platform.",
        "tables": ["nx_admin_users"],
        "related_concepts": ["User", "Client"],
    },
    {
        "id": "PasswordReset",
        "domain": "identity",
        "description": "Password reset tokens for platform users. Separate tables for different user types (general, client, coach).",
        "tables": ["nx_password_resets"],
        "related_concepts": ["User", "Client", "Coach", "AdminUser"],
    },
    {
        "id": "Journey",
        "domain": "learning",
        "description": "Learning journey - the top-level learning path. nx_journey_details is a hub table (10 refs) linking to chapters, lessons, ratings, backpacks, tasks, and journals. Core of the learning hierarchy: Journey > Chapter > Lesson.",
        "tables": ["nx_journey_details"],
        "related_concepts": ["Chapter", "Lesson", "User", "Rating", "Task", "Backpack", "Journal"],
    },
    {
        "id": "Chapter",
        "domain": "learning",
        "description": "Chapter within a journey - mid-level learning unit. nx_chapter_details is a hub table (13 refs) connecting journeys to lessons, ratings, sms, and tasks. Learning hierarchy: Journey > Chapter > Lesson.",
        "tables": ["nx_chapter_details"],
        "related_concepts": ["Journey", "Lesson", "Rating", "Task", "SMS", "Backpack"],
    },
    {
        "id": "Lesson",
        "domain": "learning",
        "description": "Lesson - the atomic learning unit. nx_lessons is a hub (13 refs). Contains lesson details and slides. Links to journeys, chapters, ratings, tasks, backpacks, and SMS. Learning hierarchy: Journey > Chapter > Lesson.",
        "tables": ["nx_lessons", "lesson_details", "lesson_slides"],
        "related_concepts": ["Journey", "Chapter", "Rating", "Task", "Backpack", "VideoLibrary"],
    },
    {
        "id": "Backpack",
        "domain": "content",
        "description": "Content backpack - saved/collected learning materials tied to journeys, chapters, and lessons. 5833 rows - indicates active use. References journey_details, chapter_details, lessons, and slides.",
        "tables": ["backpacks"],
        "related_concepts": ["Journey", "Chapter", "Lesson", "User"],
    },
    {
        "id": "Document",
        "domain": "content",
        "description": "Uploaded documents and chatbot knowledge base documents for the learning platform.",
        "tables": ["documents", "chatbot_documents"],
        "related_concepts": ["Chatbot", "User"],
    },
    {
        "id": "VideoLibrary",
        "domain": "content",
        "description": "Video content library linked to journeys, chapters, and lessons. Referenced by lesson_slides for video-based learning content.",
        "tables": ["video_libraries"],
        "related_concepts": ["Journey", "Chapter", "Lesson"],
    },
    {
        "id": "Rating",
        "domain": "engagement",
        "description": "User ratings for learning content at every level (journey, chapter, lesson, slide). nx_user_ratings has 6 references spanning the full learning hierarchy. old_ratings preserves historical rating data. 3657 total rows.",
        "tables": ["nx_user_ratings", "old_ratings"],
        "related_concepts": ["User", "Journey", "Chapter", "Lesson"],
    },
    {
        "id": "Task",
        "domain": "engagement",
        "description": "Tasks assigned within learning journeys. 2829 rows. Links to journey_details, chapter_details, lessons, and slides. Created by users.",
        "tables": ["tasks"],
        "related_concepts": ["User", "Journey", "Chapter", "Lesson"],
    },
    {
        "id": "Meeting",
        "domain": "engagement",
        "description": "Coaching meetings/sessions between coaches and learners. Includes attendee tracking with participant roles.",
        "tables": ["meetings", "meeting_attendees"],
        "related_concepts": ["Coach", "User"],
    },
    {
        "id": "Journal",
        "domain": "engagement",
        "description": "User journal entries tied to learning progress. Links to users, journey details, chapter details, and lessons. Reflective learning tool.",
        "tables": ["nx_journal_details"],
        "related_concepts": ["User", "Journey", "Chapter", "Lesson"],
    },
    {
        "id": "SMS",
        "domain": "communication",
        "description": "SMS communication system for learning nudges and reminders. Includes scheduling and dynamic content tied to chapters and lessons. 1323 detail rows.",
        "tables": ["sms_details", "sms_schedules", "dynamic_sms_details"],
        "related_concepts": ["User", "Chapter", "Lesson"],
    },
    {
        "id": "Notification",
        "domain": "communication",
        "description": "Notification history tracking for users, coaches, and clients. Multi-stakeholder notification delivery.",
        "tables": ["notification_histories"],
        "related_concepts": ["User", "Coach", "Client"],
    },
    {
        "id": "Mail",
        "domain": "communication",
        "description": "Email communication system with transfer tracking. mail_communication_details is a hub with self-referencing for threaded conversations.",
        "tables": ["mail_communication_details", "mail_transfers"],
        "related_concepts": ["User", "Notification"],
    },
    {
        "id": "Chatbot",
        "domain": "communication",
        "description": "AI chatbot for learning support. Tracks sessions and conversation history with question/answer pairs and timing.",
        "tables": ["chatbot_histories", "chatbot_sessions"],
        "related_concepts": ["User", "Document"],
    },
    {
        "id": "ActivityLog",
        "domain": "communication",
        "description": "Polymorphic activity log (Laravel Spatie). 57210 rows (77% of all data). Tracks all user actions with subject/causer polymorphism. 30 distinct log types.",
        "tables": ["activity_log"],
        "related_concepts": ["User", "AdminUser", "Coach"],
    },
    {
        "id": "ClientCoachMapping",
        "domain": "platform",
        "description": "Many-to-many mapping between clients and coaches. Core relationship table for the coaching business model.",
        "tables": ["client_coach_mappings"],
        "related_concepts": ["Client", "Coach"],
    },
    {
        "id": "Department",
        "domain": "platform",
        "description": "Organizational departments within client companies. Employees belong to departments, departments belong to clients.",
        "tables": ["departments"],
        "related_concepts": ["Client", "Employee"],
    },
    {
        "id": "BackgroundJob",
        "domain": "platform",
        "description": "Laravel queue/job infrastructure for async processing (email sending, SMS dispatch, etc.).",
        "tables": ["jobs"],
        "related_concepts": ["SMS", "Mail", "Notification"],
    },
    # --- Tory: Personalized Learning Path Engine ---
    {
        "id": "ToryContentTag",
        "domain": "learning",
        "description": "Claude Opus-generated personality trait tags per lesson. Multi-pass confidence-gated tagging with coach review. Foundation for similarity scoring and roadmap matching.",
        "tables": ["tory_content_tags"],
        "related_concepts": ["Lesson", "ToryRoadmapItem", "ToryLearnerProfile"],
    },
    {
        "id": "ToryLearnerProfile",
        "domain": "identity",
        "description": "Claude-interpreted personality profile from EPP (29 dimensions) + onboarding Q&A. Includes trait vector, motivation cluster, strengths, gaps, and user-facing narrative.",
        "tables": ["tory_learner_profiles"],
        "related_concepts": ["User", "ToryRoadmap", "ToryReassessment", "ToryContentTag"],
    },
    {
        "id": "ToryRoadmap",
        "domain": "learning",
        "description": "Personalized adaptive learning path per learner. Versioned, with pedagogy mode snapshot. Tracks completion and generation rationale.",
        "tables": ["tory_roadmaps"],
        "related_concepts": ["ToryLearnerProfile", "ToryRoadmapItem", "ToryCoachOverride", "ToryProgressSnapshot"],
    },
    {
        "id": "ToryRoadmapItem",
        "domain": "learning",
        "description": "Individual lesson assignment within a roadmap. Includes match score, rationale, critical flag (guardrail), and discovery phase marker.",
        "tables": ["tory_roadmap_items"],
        "related_concepts": ["ToryRoadmap", "ToryContentTag", "Lesson", "ToryCoachOverride"],
    },
    {
        "id": "ToryReassessment",
        "domain": "engagement",
        "description": "Periodic re-evaluation records (mini every 4-6 weeks, full EPP quarterly). Tracks profile drift and triggers path adaptation.",
        "tables": ["tory_reassessments"],
        "related_concepts": ["ToryLearnerProfile", "ToryRoadmap", "User"],
    },
    {
        "id": "ToryCoachOverride",
        "domain": "engagement",
        "description": "Coach curation actions on roadmaps (reorder/swap/lock/unlock). Guardrails prevent removal of critical lessons. Tracks divergence.",
        "tables": ["tory_coach_overrides"],
        "related_concepts": ["ToryRoadmap", "ToryRoadmapItem", "Coach"],
    },
    {
        "id": "ToryProgressSnapshot",
        "domain": "platform",
        "description": "Aggregated HR dashboard data per user per snapshot date. Includes completion, engagement, coach effectiveness, Tory accuracy, and team aggregate support.",
        "tables": ["tory_progress_snapshots"],
        "related_concepts": ["ToryRoadmap", "User", "Client", "Department"],
    },
    {
        "id": "ToryPedagogyConfig",
        "domain": "identity",
        "description": "Client-company pedagogy preference: gap-fill (A), strength-lead (B), or configurable blend (C) with ratio. Set at company onboarding.",
        "tables": ["tory_pedagogy_config"],
        "related_concepts": ["Client", "ToryRoadmap"],
    },
]


def determine_agents(domain: str, concept_id: str) -> list[str]:
    """Determine which agents are involved based on domain and concept importance."""
    # Every concept involves db-agent
    agents = ["db-agent"]

    # Domain-specific agent assignments
    domain_agents = {
        "identity": ["api-agent", "auth-agent"],
        "learning": ["api-agent", "learning-agent", "ui-agent"],
        "content": ["api-agent", "content-agent", "ui-agent"],
        "engagement": ["api-agent", "engagement-agent", "ui-agent"],
        "communication": ["api-agent", "comm-agent"],
        "platform": ["api-agent"],
    }

    agents.extend(domain_agents.get(domain, ["api-agent"]))

    # Hub concepts get extra attention
    hub_concepts = {"User", "Journey", "Chapter", "Lesson", "Rating"}
    if concept_id in hub_concepts:
        if "ui-agent" not in agents:
            agents.append("ui-agent")

    # Tory concepts always involve tory-agent
    tory_concepts = {
        "ToryContentTag", "ToryLearnerProfile", "ToryRoadmap",
        "ToryRoadmapItem", "ToryReassessment", "ToryCoachOverride",
        "ToryProgressSnapshot", "ToryPedagogyConfig",
    }
    if concept_id in tory_concepts:
        agents.append("tory-agent")

    return sorted(set(agents))


def validate_concepts(concepts: list[dict], all_tables: set[str]) -> None:
    """Validate the concept mappings meet quality criteria."""
    errors = []
    warnings = []

    # 1. At least 10 concepts
    if len(concepts) < 10:
        errors.append(f"Only {len(concepts)} concepts (need >= 10)")

    # 2. Each concept has at least 1 table
    for c in concepts:
        tables = [t.strip() for t in c["tables"].split(",") if t.strip()]
        if len(tables) == 0:
            errors.append(f"Concept {c['id']} has no tables")

    # 3. Not all domains are "general"
    domains = set(c["domain"] for c in concepts)
    if domains == {"general"}:
        errors.append("All concepts have domain 'general'")
    if len(domains) < 3:
        warnings.append(f"Only {len(domains)} distinct domains: {domains}")

    # 4. All tables are assigned to at least one concept
    assigned_tables = set()
    for c in concepts:
        for t in c["tables"].split(","):
            t = t.strip()
            if t:
                assigned_tables.add(t)

    orphans = all_tables - assigned_tables
    if orphans:
        warnings.append(f"Unassigned tables: {orphans}")

    double_assigned = []
    table_concept_map = defaultdict(list)
    for c in concepts:
        for t in c["tables"].split(","):
            t = t.strip()
            if t:
                table_concept_map[t].append(c["id"])
    for t, cs in table_concept_map.items():
        if len(cs) > 1:
            double_assigned.append(f"{t} -> {cs}")

    if double_assigned:
        warnings.append(f"Tables in multiple concepts: {double_assigned}")

    # 5. Related concepts cross-reference each other
    concept_ids = set(c["id"] for c in concepts)
    for c in concepts:
        related = [r.strip() for r in c["related_concepts"].split(",") if r.strip()]
        for r in related:
            if r not in concept_ids:
                warnings.append(f"Concept {c['id']} references unknown concept {r}")

    # 6. Hub tables are covered
    hub_tables = ["nx_users", "nx_chapter_details", "nx_lessons", "nx_journey_details", "lesson_details"]
    for ht in hub_tables:
        if ht not in assigned_tables:
            errors.append(f"Hub table {ht} not assigned to any concept")

    # Report
    if errors:
        print("\n=== VALIDATION ERRORS ===")
        for e in errors:
            print(f"  ERROR: {e}")

    if warnings:
        print("\n=== VALIDATION WARNINGS ===")
        for w in warnings:
            print(f"  WARN: {w}")

    if not errors and not warnings:
        print("\n=== VALIDATION: ALL CHECKS PASSED ===")
    elif not errors:
        print("\n=== VALIDATION: PASSED (with warnings) ===")
    else:
        print("\n=== VALIDATION: FAILED ===")
        raise SystemExit(1)


def main():
    # Load discovery data
    schema = load_json(DISCOVERY / "schema.json")
    relationships = load_json(DISCOVERY / "relationships.json")
    profile = load_json(DISCOVERY / "profile.json")

    all_tables = set(t["name"] for t in schema["tables"])
    row_counts = build_row_count_map(profile)
    rel_graph = build_relationship_graph(relationships)
    hub_map = build_hub_table_map(relationships)

    print(f"Loaded: {len(all_tables)} tables, {len(relationships['relationships'])} relationships")
    print(f"Hub tables: {list(hub_map.keys())}")
    print()

    # Build concepts from definitions
    concepts = []
    for defn in CONCEPT_DEFINITIONS:
        concept_id = defn["id"]
        domain = defn["domain"]
        tables = defn["tables"]
        related = defn["related_concepts"]

        # Compute stats for description enrichment
        total_rows = sum(row_counts.get(t, 0) for t in tables)
        hub_refs = sum(hub_map.get(t, 0) for t in tables)

        # Determine agents
        agents = determine_agents(domain, concept_id)

        concept = {
            "id": concept_id,
            "type": "concept",
            "description": defn["description"],
            "tables": ",".join(sorted(tables)),
            "domain": domain,
            "related_concepts": ",".join(sorted(related)),
            "agents_involved": ",".join(agents),
        }
        concepts.append(concept)

    # Write CSV
    SEEDS.mkdir(parents=True, exist_ok=True)
    output_path = SEEDS / "concepts.csv"

    fieldnames = [
        "id", "type", "description", "tables", "domain",
        "related_concepts", "agents_involved"
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(concepts)

    # Summary statistics
    print("=" * 60)
    print(f"CONCEPTS CREATED: {len(concepts)}")
    print("=" * 60)

    domain_counts = defaultdict(int)
    domain_tables = defaultdict(int)
    for c in concepts:
        domain_counts[c["domain"]] += 1
        domain_tables[c["domain"]] += len(c["tables"].split(","))

    print(f"\n{'Domain':<20} {'Concepts':>10} {'Tables':>10}")
    print("-" * 42)
    for domain in sorted(domain_counts.keys()):
        print(f"{domain:<20} {domain_counts[domain]:>10} {domain_tables[domain]:>10}")
    print("-" * 42)
    print(f"{'TOTAL':<20} {sum(domain_counts.values()):>10} {sum(domain_tables.values()):>10}")

    # List all concepts
    print(f"\n{'ID':<25} {'Domain':<15} {'Tables':>7} {'Related':>8}")
    print("-" * 58)
    for c in concepts:
        n_tables = len(c["tables"].split(","))
        n_related = len([r for r in c["related_concepts"].split(",") if r.strip()])
        print(f"{c['id']:<25} {c['domain']:<15} {n_tables:>7} {n_related:>8}")

    # Table coverage check
    assigned = set()
    for c in concepts:
        for t in c["tables"].split(","):
            t = t.strip()
            if t:
                assigned.add(t)

    unassigned = all_tables - assigned
    print(f"\nTable coverage: {len(assigned)}/{len(all_tables)} tables assigned")
    if unassigned:
        print(f"Unassigned tables: {sorted(unassigned)}")

    print(f"\nOutput written to: {output_path}")

    # Validate
    validate_concepts(concepts, all_tables)


if __name__ == "__main__":
    main()
