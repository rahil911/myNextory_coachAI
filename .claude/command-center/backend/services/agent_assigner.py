"""
agent_assigner.py — KG-based agent assignment for beads.

Queries the Ownership Knowledge Graph to find the best agent for each task
based on file ownership, capabilities, and domain expertise.
"""

import asyncio
import json
import logging
from pathlib import Path

from config import PROJECT_ROOT, KG_CACHE

logger = logging.getLogger(__name__)

# Known agent capabilities (fallback if KG query fails)
AGENT_CAPABILITIES = {
    "platform-agent": ["fastapi", "architecture", "database", "api", "deployment"],
    "identity-agent": ["auth", "users", "sessions", "jwt", "oauth", "permissions"],
    "comms-agent": ["notifications", "email", "sms", "push", "messaging"],
    "content-agent": ["cms", "media", "documents", "search", "templates"],
    "engagement-agent": ["analytics", "tracking", "events", "campaigns", "ab-testing"],
    "meetings-agent": ["calendar", "scheduling", "video", "rooms", "availability"],
    "kg-agent": ["knowledge-graph", "ontology", "relationships", "metadata"],
    "review-agent": ["code-review", "testing", "quality", "security"],
}

# Domain keywords -> agent mapping
DOMAIN_KEYWORDS = {
    "identity-agent": [
        "user", "auth", "login", "signup", "password", "session",
        "permission", "role", "jwt", "oauth", "profile", "account",
    ],
    "comms-agent": [
        "notification", "email", "sms", "push", "alert", "message",
        "template", "send", "telegram", "whatsapp",
    ],
    "content-agent": [
        "content", "document", "media", "upload", "image", "file",
        "search", "cms", "lesson", "journey", "chapter", "slide",
    ],
    "engagement-agent": [
        "analytics", "tracking", "event", "campaign", "metric",
        "dashboard", "report", "activity", "engagement",
    ],
    "meetings-agent": [
        "meeting", "calendar", "schedule", "booking", "appointment",
        "room", "availability", "coaching", "session",
    ],
    "kg-agent": [
        "knowledge", "graph", "ontology", "relationship", "entity",
        "concept", "metadata", "schema",
    ],
}


class AgentAssigner:
    """Assigns beads to agents using KG context."""

    def __init__(self):
        self._baap_root = PROJECT_ROOT
        self._kg_cache = None
        self._agents: dict[str, dict] = {}

    def _load_kg(self) -> None:
        """Load agent knowledge graph from cache."""
        if self._kg_cache is not None:
            return

        cache_path = KG_CACHE
        try:
            self._kg_cache = json.loads(cache_path.read_text())
            # Index agents by ID for fast lookup
            nodes = self._kg_cache.get("nodes", [])
            if isinstance(nodes, list):
                for node in nodes:
                    if node.get("type") == "agent":
                        self._agents[node["id"]] = node
            elif isinstance(nodes, dict):
                for node_id, node in nodes.items():
                    if node.get("type") == "agent":
                        self._agents[node_id] = node
            logger.info(f"KG loaded: {len(self._agents)} agents")
        except Exception as e:
            logger.warning(f"Failed to load KG cache: {e}. Using fallback capabilities.")
            self._kg_cache = {}

    def get_agent_capabilities(self, agent_id: str) -> list[str]:
        """Get agent capabilities from KG or fallback."""
        self._load_kg()
        agent = self._agents.get(agent_id, {})
        caps = agent.get("capabilities", [])
        if caps:
            return caps
        return AGENT_CAPABILITIES.get(agent_id, [])

    def get_available_agents(self) -> list[str]:
        """Get list of all available agent IDs."""
        self._load_kg()
        if self._agents:
            return list(self._agents.keys())
        return list(AGENT_CAPABILITIES.keys())

    def score_agent_for_task(self, agent_id: str, task) -> float:
        """Score how well an agent matches a task (0.0 - 1.0)."""
        score = 0.0
        text = f"{task.title} {task.description} {' '.join(task.requirements)}".lower()

        # Check domain keywords
        for kw_agent, keywords in DOMAIN_KEYWORDS.items():
            if agent_id == kw_agent:
                matches = sum(1 for kw in keywords if kw in text)
                if matches > 0:
                    score += min(matches * 0.15, 0.6)

        # Check capabilities overlap
        caps = self.get_agent_capabilities(agent_id)
        for cap in caps:
            if cap.lower() in text:
                score += 0.1

        # Bonus if this was the suggested agent
        if hasattr(task, "suggested_agent") and task.suggested_agent == agent_id:
            score += 0.2

        # Check affected files against KG file ownership
        if hasattr(task, "affected_files") and task.affected_files:
            owned_files = self._get_agent_files(agent_id)
            for f in task.affected_files:
                if any(f in owned for owned in owned_files):
                    score += 0.15

        return min(score, 1.0)

    def _get_agent_files(self, agent_id: str) -> list[str]:
        """Get files owned by this agent from KG."""
        self._load_kg()
        edges = self._kg_cache.get("edges", [])
        files = []
        if isinstance(edges, list):
            for edge in edges:
                src = edge.get("from") or edge.get("source", "")
                if src == agent_id and edge.get("type") in ("OWNS", "owns"):
                    files.append(edge.get("to", edge.get("target", "")))
        return files

    def find_best_agent(self, task) -> str:
        """Find the best agent for a given task."""
        agents = self.get_available_agents()
        if not agents:
            return getattr(task, "suggested_agent", None) or "platform-agent"

        scores = {}
        for agent_id in agents:
            # Skip orchestrator and review-agent for implementation tasks
            if agent_id in ("orchestrator", "review-agent"):
                continue
            scores[agent_id] = self.score_agent_for_task(agent_id, task)

        if not scores:
            return getattr(task, "suggested_agent", None) or "platform-agent"

        best = max(scores, key=scores.get)
        best_score = scores[best]

        # If best score is too low, fall back to platform-agent
        if best_score < 0.1:
            return "platform-agent"

        logger.info(f"Task '{task.title}' -> {best} (score: {best_score:.2f})")
        return best

    async def assign_beads(self, plan) -> None:
        """Assign all beads in a plan to agents.

        Updates task.suggested_agent and calls bd update --assignee.
        """
        for task in plan.tasks:
            agent = self.find_best_agent(task)
            task.suggested_agent = agent
            plan.agent_hints[task.id] = agent

            # Update bead assignment via CLI
            if task.id:
                await self._assign_bead(task.id, agent)

            logger.info(f"Assigned bead {task.id} '{task.title}' -> {agent}")

    async def _assign_bead(self, bead_id: str, agent_name: str) -> None:
        """Assign a bead to an agent via bd CLI."""
        proc = await asyncio.create_subprocess_exec(
            "bd", "update", bead_id, f"--assignee={agent_name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._baap_root),
        )
        await proc.communicate()
