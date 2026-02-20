"""
AI Tool Definitions for MyNextory RAG System
Defines 7 tools the AI can call during conversation via Anthropic tool_use API.

These tools let the Companion/Curator fetch live data mid-conversation:
- search_lesson_content: FAISS global search
- search_backpack: FAISS personal search
- get_slide: raw slide content by lesson_detail + index
- get_progress: learner completion % and ratings
- get_epp_trait: single EPP trait score + interpretation
- get_coaching_prompts: pre-generated conversation starters for a lesson
- get_pair_recommendations: related lessons for a given lesson
"""

from typing import Any, Dict, List


# ============================================================================
# Tool definitions in Anthropic tool_use format
# ============================================================================

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "search_lesson_content",
        "description": (
            "Search the global lesson knowledge base using semantic similarity. "
            "Returns the top matching content chunks from all indexed lessons. "
            "Use when the learner asks about a topic and you need to find "
            "relevant lesson material."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language search query. Use the learner's "
                        "question or a reformulated version for best results."
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_backpack",
        "description": (
            "Search the learner's personal backpack (saved notes, highlights, "
            "reflections) using semantic similarity. Returns matching entries "
            "from their personal FAISS index. Use when the learner references "
            "something they saved or when personalizing a response."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "integer",
                    "description": "The nx_users.id of the learner.",
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Search query to find relevant backpack entries."
                    ),
                },
            },
            "required": ["user_id", "query"],
        },
    },
    {
        "name": "get_slide",
        "description": (
            "Retrieve the raw content of a specific slide from a lesson. "
            "Use when the learner asks about a specific slide or when you "
            "need to reference exact slide content for accuracy."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lesson_detail_id": {
                    "type": "integer",
                    "description": (
                        "The nx_lesson_details.id identifying the lesson section."
                    ),
                },
                "slide_index": {
                    "type": "integer",
                    "description": (
                        "Zero-based index of the slide within the lesson detail."
                    ),
                },
            },
            "required": ["lesson_detail_id", "slide_index"],
        },
    },
    {
        "name": "get_progress",
        "description": (
            "Get the learner's progress data: overall completion percentage, "
            "lesson-level completion, ratings given, and recent activity. "
            "Use when the learner asks about their progress or when you need "
            "to contextualize a response with their learning status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "integer",
                    "description": "The nx_users.id of the learner.",
                },
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "get_epp_trait",
        "description": (
            "Retrieve a specific EPP (Employee Personality Profile) trait "
            "score and its interpretation for a learner. Returns the numeric "
            "score (1-10) and a natural-language interpretation of what it "
            "means for the learner's development. Use when discussing "
            "personality-based coaching insights."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "integer",
                    "description": "The nx_users.id of the learner.",
                },
                "trait": {
                    "type": "string",
                    "description": (
                        "EPP trait name. Personality traits: Achievement, "
                        "Motivation, Competitiveness, Managerial, Assertiveness, "
                        "Extroversion, Cooperativeness, Patience, SelfConfidence, "
                        "Conscientiousness, Openness, Stability, StressTolerance. "
                        "Job fit traits: Accounting, AdminAsst, Analyst, "
                        "BankTeller, Collections, CustomerService, FrontDesk, "
                        "Manager, MedicalAsst, Production, Programmer, Sales."
                    ),
                },
            },
            "required": ["user_id", "trait"],
        },
    },
    {
        "name": "get_coaching_prompts",
        "description": (
            "Get pre-generated coaching conversation starters for a specific "
            "lesson. These prompts help guide the learner through reflection "
            "and application of the lesson content. Use at the start of a "
            "lesson discussion or when the conversation stalls."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lesson_id": {
                    "type": "integer",
                    "description": "The nx_lessons.id of the lesson.",
                },
            },
            "required": ["lesson_id"],
        },
    },
    {
        "name": "get_pair_recommendations",
        "description": (
            "Get lessons that pair well with a given lesson based on content "
            "similarity, EPP trait alignment, and journey progression. Use "
            "when the learner finishes a lesson and wants to explore related "
            "topics, or when suggesting 'what to learn next'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lesson_id": {
                    "type": "integer",
                    "description": "The nx_lessons.id to find pairs for.",
                },
            },
            "required": ["lesson_id"],
        },
    },
]


def get_tools() -> List[Dict[str, Any]]:
    """Return the full list of tool definitions for Anthropic API."""
    return TOOLS


def get_tool_names() -> List[str]:
    """Return just the tool names."""
    return [t["name"] for t in TOOLS]


def get_tool_by_name(name: str) -> Dict[str, Any]:
    """Look up a tool definition by name. Returns empty dict if not found."""
    for tool in TOOLS:
        if tool["name"] == name:
            return tool
    return {}
