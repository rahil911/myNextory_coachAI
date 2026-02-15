"""
routes/commands.py — Command palette backend.
"""

from fastapi import APIRouter, HTTPException

from models import Command, CommandExecuteRequest, CommandExecuteResponse, CommandSearchRequest

router = APIRouter(prefix="/api/commands", tags=["commands"])


def _get_command_service():
    from main import get_command_service
    return get_command_service()


def _get_agent_service():
    from main import get_agent_service
    return get_agent_service()


def _get_bead_service():
    from main import get_bead_service
    return get_bead_service()


@router.get("/available", response_model=list[Command])
async def list_commands(context: str | None = None):
    """List available commands, optionally filtered by context."""
    svc = _get_command_service()
    return svc.list_commands(context=context)


@router.post("/search", response_model=list[Command])
async def search_commands(req: CommandSearchRequest):
    """Fuzzy search commands for Cmd+K palette."""
    svc = _get_command_service()
    return svc.search(query=req.query, context=req.context, limit=req.limit)


@router.post("/execute", response_model=CommandExecuteResponse)
async def execute_command(req: CommandExecuteRequest):
    """Execute a command."""
    cmd_svc = _get_command_service()
    cmd = cmd_svc.get_command(req.command_id)
    if not cmd:
        raise HTTPException(status_code=404, detail=f"Command '{req.command_id}' not found")

    if cmd.requires_confirmation and not req.confirmed:
        return CommandExecuteResponse(
            command_id=req.command_id,
            success=False,
            message=f"Command '{cmd.name}' requires confirmation. Set confirmed=true to proceed.",
        )

    # Route to appropriate service
    try:
        result = await _dispatch_command(cmd, req.params)
        return CommandExecuteResponse(
            command_id=req.command_id,
            success=result.get("success", False),
            message=result.get("message", ""),
            output=result.get("output"),
        )
    except Exception as e:
        return CommandExecuteResponse(
            command_id=req.command_id,
            success=False,
            message=str(e),
        )


async def _dispatch_command(cmd: Command, params: dict) -> dict:
    """Route a command to the appropriate service method."""
    agent_svc = _get_agent_service()
    bead_svc = _get_bead_service()

    handlers = {
        "agent.kill": lambda: agent_svc.kill_agent(params.get("name", "")),
        "agent.retry": lambda: agent_svc.retry_agent(params.get("name", "")),
        "agent.spawn": lambda: agent_svc.spawn_agent(
            mode=params.get("mode", "worktree"),
            prompt=params.get("prompt", ""),
            path=params.get("path"),
            level=params.get("level", 2),
            bead=params.get("bead"),
        ),
        "bead.create": lambda: _sync_wrap(bead_svc.create_bead(
            title=params.get("title", "Untitled"),
            bead_type=params.get("type", "task"),
            priority=params.get("priority"),
        )),
        "bead.close": lambda: _sync_wrap(bead_svc.update_bead(params.get("id", ""), status="closed")),
        "system.health": lambda: _async_return({"success": True, "message": "API healthy"}),
    }

    handler = handlers.get(cmd.id)
    if handler:
        result = handler()
        if hasattr(result, "__await__"):
            return await result
        return result

    return {"success": False, "message": f"No handler for command '{cmd.id}'"}


def _sync_wrap(result: tuple) -> dict:
    ok, output = result
    return {"success": ok, "message": output}


async def _async_return(val: dict) -> dict:
    return val
