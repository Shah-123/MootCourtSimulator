"""Ruling on an objection the student raised by hand.

The last piece of reasoning that lived in Express. `routes/sessions.ts` built
its own ruling prompt and called the model directly, which broke the §1
boundary — but the worse problem was that it made a *second bench*. That one
was handed a block of retrieved provisions and answered in one shot; the bench
in `agents/judge.py` reads the corpus itself with `search_statute` in a bounded
ReAct loop and returns the trace. Two judges ruling on the same kind of
objection, by different methods, with nothing forcing them to agree.

So this does not port the old prompt across the boundary. It routes the
hand-raised objection into the same `rule_on_objection` the graph uses, telling
it that the student objected rather than opposing counsel — see `ObjectorVoice`
for why that distinction is load-bearing rather than cosmetic. The student's
objection now gets what the autonomous one always had: statute read before the
ruling, and a recorded trace showing it.

Only the ruling comes back. The student's own words are not an agent event and
must not be recorded as one — `CourtEvent.speaker` cannot even express
"student" — so Express writes that turn itself, exactly as it already does for
the utterance in `POST /sessions/:id/turn`.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.graph import audit_to_dict, build_context
from app.agents.judge import STUDENT, rule_on_objection
from app.agents.state import CourtEvent, Objection, TurnRequest
from app.grounding import find_objection_ground
from app.proceedings import TRIAL
from app.rag.citations import audit_citations, extract_citations

logger = logging.getLogger(__name__)

# Fallback when the student objects without saying why. The bench still has the
# ground and the provision behind it, which is enough to rule on.
DEFAULT_STATEMENT = "Objection, My Lord!"


async def rule_on_raised_objection(
    request: TurnRequest,
    ground_id: str,
    statement: str,
) -> dict[str, Any]:
    """Rules on an objection raised by the student.

    Raises ValueError when the ground does not exist in this proceeding. That
    is the same answer the catalogue gives, so a ground id posted directly
    cannot get past a filter the UI is already applying.
    """
    proceeding_type = request.case.proceeding_type or TRIAL
    ground = await find_objection_ground(ground_id, proceeding_type)
    if ground is None:
        raise ValueError(
            f"Objection ground {ground_id!r} is not available in a "
            f"{proceeding_type} proceeding"
        )

    spoken = statement.strip() or DEFAULT_STATEMENT

    objection = Objection(
        groundId=ground.id,
        label=ground.label,
        citation=ground.citation,
        heading=ground.heading,
        content=ground.content,
        # The student's own words are the interjection here. The graph's
        # opposing counsel writes its own; a student has already written theirs.
        interjection=spoken,
    )

    # The same context the graph builds: memory, the ground catalogue scoped to
    # the proceeding, and the case. This imports no LangGraph — the compiled
    # graph is built lazily inside `get_graph`, so ruling on a hand-raised
    # objection never pays the ~49s import.
    context = await build_context(request)
    ruling = await rule_on_objection(context, objection, objector=STUDENT)

    event = CourtEvent(
        speaker="judge",
        kind="ruling",
        transcript=(
            f"[{ruling.ruling.upper()}] {ruling.explanation} {ruling.impact}"
        ).strip(),
        ruling=ruling.ruling,
        citation=ruling.citation,
        reasoning=ruling.reasoning,
        grounded=ruling.grounded,
    )

    # Audited over what the bench said. Provisions the student put on the record
    # in their own objection are marked as echoed, so a bench that names one in
    # order to reject it is not recorded as having fabricated it — the same
    # correction `agentFabricated` exists to make on the graph path.
    echoed = frozenset(
        f"{code}:{number}" for _raw, code, number in extract_citations(spoken)
    )
    audit = audit_to_dict(await audit_citations(event.transcript), echoed)

    if audit["agentFabricated"]:
        logger.warning(
            "Bench cited provisions absent from the corpus while ruling on a "
            "hand-raised objection: %s",
            audit["agentFabricated"],
        )

    return {
        "events": [event.model_dump(by_alias=True)],
        "objection": objection.model_dump(by_alias=True),
        "primarySpeaker": "judge",
        "citationAudit": audit,
    }
