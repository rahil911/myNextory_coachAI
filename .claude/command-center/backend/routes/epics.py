"""
routes/epics.py — Epic progress and dependency graphs.
"""

from fastapi import APIRouter, HTTPException

from models import EpicListResponse, Epic, EpicGraphResponse, EpicGraphNode

router = APIRouter(prefix="/api/epics", tags=["epics"])


def _get_bead_service():
    from main import get_bead_service
    return get_bead_service()


@router.get("", response_model=EpicListResponse)
async def list_epics():
    """All epics with progress percentages."""
    svc = _get_bead_service()
    epics_data = svc.build_epics()
    epics = [Epic(**e) for e in epics_data]
    return EpicListResponse(epics=epics, count=len(epics))


@router.get("/{epic_id}")
async def get_epic(epic_id: str):
    """Epic detail with bead breakdown."""
    svc = _get_bead_service()
    epics_data = svc.build_epics()
    for e in epics_data:
        if e["epic"] == epic_id:
            beads = svc.list_beads(epic=epic_id)
            return {**e, "bead_details": beads}
    raise HTTPException(status_code=404, detail=f"Epic '{epic_id}' not found")


@router.get("/{epic_id}/graph", response_model=EpicGraphResponse)
async def get_epic_graph(epic_id: str):
    """Dependency DAG for an epic."""
    svc = _get_bead_service()
    beads = svc.list_beads(epic=epic_id)
    if not beads:
        raise HTTPException(status_code=404, detail=f"No beads found for epic '{epic_id}'")

    nodes = [EpicGraphNode(id=b.id, title=b.title, status=b.status, deps=b.deps) for b in beads]
    edges = []
    for b in beads:
        for dep in b.deps:
            edges.append({"from": dep, "to": b.id})

    return EpicGraphResponse(epic=epic_id, nodes=nodes, edges=edges)
