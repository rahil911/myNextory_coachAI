"""
routes/agents.py — Agent management endpoints.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

from models import AgentListResponse, Agent, SpawnRequest, SpawnResponse, AgentLogResponse

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _get_agent_service():
    """Get agent service from app state. Set during app startup."""
    from main import get_agent_service
    return get_agent_service()


@router.get("", response_model=AgentListResponse)
async def list_agents():
    """List all agents with status, heartbeat, bead, level."""
    svc = _get_agent_service()
    agents = svc.read_agents()
    await svc.detect_transitions(agents)
    return AgentListResponse(
        agents=agents,
        count=len(agents),
        ts=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/{name}")
async def get_agent(name: str):
    """Get detailed info for a single agent."""
    svc = _get_agent_service()
    agent = svc.get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return agent


@router.post("/{name}/kill")
async def kill_agent(name: str):
    """Kill an agent via kill-agent.sh."""
    svc = _get_agent_service()
    result = await svc.kill_agent(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@router.post("/{name}/retry")
async def retry_agent(name: str):
    """Retry a failed agent via retry-agent.sh."""
    svc = _get_agent_service()
    result = await svc.retry_agent(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@router.post("/spawn", response_model=SpawnResponse)
async def spawn_agent(req: SpawnRequest):
    """Spawn a new agent."""
    svc = _get_agent_service()
    result = await svc.spawn_agent(
        mode=req.mode, prompt=req.prompt, path=req.path,
        level=req.level, bead=req.bead,
    )
    return SpawnResponse(
        agent_name=result.get("agent_name", "unknown"),
        status="spawned" if result["success"] else "failed",
        message=result["message"],
    )


@router.get("/{name}/logs", response_model=AgentLogResponse)
async def get_agent_logs(name: str, tail: int = 100):
    """Get the last N lines of an agent's log."""
    svc = _get_agent_service()
    log_file, lines = svc.get_agent_logs(name, tail=tail)
    return AgentLogResponse(
        agent_name=name,
        log_file=log_file,
        lines=lines,
        total_lines=len(lines),
    )
