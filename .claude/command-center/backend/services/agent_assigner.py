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

    def score_agent_for_task(self, agent_id: str, task) -> tuple[float, dict]:
        """Score how well an agent matches a task.

        Returns (score, breakdown) where breakdown explains the scoring.
        """
        score = 0.0
        breakdown = {
            "keyword_matches": 0,
            "capability_matches": 0,
            "suggested_bonus": False,
            "file_ownership": 0,
        }
        text = f"{task.title} {task.description} {' '.join(task.requirements)}".lower()

        # Check domain keywords
        for kw_agent, keywords in DOMAIN_KEYWORDS.items():
            if agent_id == kw_agent:
                matches = sum(1 for kw in keywords if kw in text)
                if matches > 0:
                    breakdown["keyword_matches"] = matches
                    score += min(matches * 0.15, 0.6)

        # Check capabilities overlap
        caps = self.get_agent_capabilities(agent_id)
        cap_matches = sum(1 for cap in caps if cap.lower() in text)
        breakdown["capability_matches"] = cap_matches
        score += cap_matches * 0.1

        # Bonus if this was the suggested agent
        if hasattr(task, "suggested_agent") and task.suggested_agent == agent_id:
            breakdown["suggested_bonus"] = True
            score += 0.2

        # Check affected files against KG file ownership
        if hasattr(task, "affected_files") and task.affected_files:
            owned_files = self._get_agent_files(agent_id)
            file_matches = sum(1 for f in task.affected_files if any(f in owned for owned in owned_files))
            breakdown["file_ownership"] = file_matches
            score += file_matches * 0.15

        return (min(score, 1.0), breakdown)

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

    def find_best_agent(self, task) -> tuple[str, dict]:
        """Find the best agent for a given task.

        Returns (agent_id, all_scores) where all_scores maps each candidate
        agent to {score, ...breakdown} for transparency.
        """
        agents = self.get_available_agents()
        if not agents:
            fallback = getattr(task, "suggested_agent", None) or "platform-agent"
            return (fallback, {fallback: {"score": 0, "reason": "no agents available"}})

        all_scores = {}
        for agent_id in agents:
            # Skip orchestrator and review-agent for implementation tasks
            if agent_id in ("orchestrator", "review-agent"):
                continue
            score, breakdown = self.score_agent_for_task(agent_id, task)
            all_scores[agent_id] = {"score": round(score, 3), **breakdown}

        if not all_scores:
            fallback = getattr(task, "suggested_agent", None) or "platform-agent"
            return (fallback, {fallback: {"score": 0, "reason": "no candidate agents"}})

        best = max(all_scores, key=lambda k: all_scores[k]["score"])
        best_score = all_scores[best]["score"]

        # If best score is too low, fall back to platform-agent
        if best_score < 0.1:
            logger.info(f"Task '{task.title}' -> platform-agent (all scores < 0.1)")
            return ("platform-agent", all_scores)

        logger.info(f"Task '{task.title}' -> {best} (score: {best_score:.3f})")
        return (best, all_scores)

    async def assign_beads(self, plan) -> None:
        """Assign all beads in a plan to agents.

        Updates task.suggested_agent, calls bd update --assignee, and stores
        assignment reasoning on the plan for Control Tower visibility.
        """
        if not hasattr(plan, "assignment_reasoning"):
            plan.assignment_reasoning = {}

        for task in plan.tasks:
            agent, scores = self.find_best_agent(task)
            task.suggested_agent = agent
            plan.agent_hints[task.id] = agent

            # Store reasoning for UI transparency
            plan.assignment_reasoning[task.id] = {
                "chosen": agent,
                "scores": scores,
            }

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
