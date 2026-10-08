from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.agents import (
    TurnRequest,
    graph_mermaid,
    run_interjection,
    run_turn,
    run_turn_stream,
)
from app.grounding import (
    find_objection_ground,
    list_objection_grounds,
    retrieve_area_palette,
)
from app.memory import (
    format_memory_for_prompt,
    load_session_memory,
    refresh_session_memory,
)
from app.objections import rule_on_raised_objection
from app.proceedings import TRIAL
from app.rag.retrieval import format_sections_for_prompt

router = APIRouter(tags=["courtroom"])

logger = logging.getLogger(__name__)


class PaletteRequest(BaseModel):
    area_of_law: str
    limit: int = Field(default=12, ge=1, le=30)


@router.post("/grounding/area-palette")
async def area_palette(request: PaletteRequest) -> dict:
    sections = await retrieve_area_palette(request.area_of_law, request.limit)
    return {
        "sections": [item.to_dict() for item in sections],
        "promptBlock": format_sections_for_prompt(sections),
        "allowedCitations": [item.section.citation for item in sections],
    }


@router.post("/courtroom/turn")
async def courtroom_turn(request: TurnRequest) -> dict:
    """Runs one student utterance through the multi-agent courtroom graph.

    Returns the ordered sequence of agent events (an objection, a ruling, a
    witness answer — however many the moment required) with a citation audit
    over everything the AI said. The Node API owns persisting these as turns and
    speaking them; this endpoint only reasons.
    """
    return await run_turn(request)


@router.post("/courtroom/interject")
async def courtroom_interject(request: TurnRequest) -> dict:
    """Handles a student interrupting the court mid-answer.

    The web app cuts playback the moment it hears speech and posts whatever was
    said. This decides whether it was an objection, on which corpus-backed
    ground, and how the same ReAct judge rules on it. An interruption that was
    not an objection returns no events rather than being forced into one.
    """
    return await run_interjection(request)


@router.post("/courtroom/turn/stream")
async def courtroom_turn_stream(request: TurnRequest) -> StreamingResponse:
    """The same turn as ``/courtroom/turn``, one agent event at a time (NDJSON).

    The voice path speaks each event as it arrives, so opposing counsel's
    objection reaches the student while the judge is still reading statute
    instead of after. Each event carries its own citation audit, so a fabricated
    provision is flagged on the utterance that carried it rather than at the end
    of the turn.
    """

    async def lines() -> AsyncIterator[str]:
        try:
            async for payload in run_turn_stream(request):
                yield json.dumps(payload) + "\n"
        except Exception as err:
            # The 200 status line is already on the wire by the time a node can
            # fail, so the failure has to travel in-band as a final message.
            logger.exception("Courtroom turn stream failed")
            yield json.dumps({"type": "error", "message": str(err)}) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@router.get("/courtroom/graph", response_class=Response)
async def courtroom_graph() -> Response:
    """The compiled agent graph as a Mermaid diagram (documentation aid)."""
    return Response(content=graph_mermaid(), media_type="text/plain")


@router.get("/objection-grounds")
async def objection_grounds(
    proceeding_type: str = Query(TRIAL, alias="proceedingType"),
) -> list[dict]:
    # An empty list is a correct answer, not a failure: every ground is an
    # evidentiary examination ground, and a writ has no witness box.
    return [
        ground.to_dict() for ground in await list_objection_grounds(proceeding_type)
    ]


@router.get("/objection-grounds/{ground_id}")
async def objection_ground(
    ground_id: str,
    proceeding_type: str = Query(TRIAL, alias="proceedingType"),
) -> dict:
    ground = await find_objection_ground(ground_id, proceeding_type)
    if ground is None:
        raise HTTPException(status_code=404, detail="Unknown objection ground")
    return ground.to_dict()


class RaisedObjectionRequest(BaseModel):
    """A student's own objection, plus the turn context the bench needs."""

    model_config = ConfigDict(populate_by_name=True)
    ground_id: str = Field(alias="groundId")
    statement: str = ""
    turn: TurnRequest


@router.post("/objections/rule")
async def objections_rule(request: RaisedObjectionRequest) -> dict:
    """Rules on an objection the student raised.

    The same bench that rules on the objections opposing counsel raises inside
    the graph — see `app/objections.py` for why this routes there rather than
    porting the prompt Express used to hold.
    """
    try:
        return await rule_on_raised_objection(
            request.turn, request.ground_id, request.statement
        )
    except ValueError as err:
        # The ground does not exist in this proceeding. A client error, not a
        # failed ruling.
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.post("/sessions/{session_id}/memory/refresh")
async def refresh_memory(session_id: int) -> dict:
    try:
        memory = await refresh_session_memory(session_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return memory.model_dump(by_alias=True)


@router.get("/sessions/{session_id}/memory")
async def get_memory(session_id: int, phase: str = "opening") -> dict:
    memory = await load_session_memory(session_id)
    return {
        **memory.model_dump(by_alias=True),
        "promptBlock": format_memory_for_prompt(memory, phase),
    }
