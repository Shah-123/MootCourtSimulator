"""The student interrupts.

Everywhere else in the courtroom the student speaks and then waits. A real
advocate does not wait — they come to their feet over the answer they are
objecting to. This is the path for that: the web app stops the AI mid-sentence
the moment it hears speech, sends whatever the student said, and this decides
what it was.

Two decisions, in order:

1. **Was that an objection, and on what ground?** Constrained to the same
   catalogue opposing counsel is constrained to, so a student objection is
   citable by construction exactly as an autonomous one is. An interruption
   that is not an objection is not forced into becoming one — the honest answer
   to "counsel simply started talking" is that no objection was raised.
2. **How does the bench rule?** By the same ReAct judge that rules on the
   agents' objections. There is one judge in this courtroom, and it reads the
   statute before it rules whoever raised the point.
"""

from __future__ import annotations

import logging

from app.agents.graph import build_context
from app.agents.judge import rule_on_objection
from app.agents.llm import json_completion
from app.agents.state import CourtEvent, Objection, TurnRequest
from app.rag.citations import audit_citations

logger = logging.getLogger(__name__)

_CLASSIFY_SYSTEM = """You are the clerk of a Pakistani court. Counsel has just interrupted the proceedings. Decide what they said, in narrow terms: is this an objection, and if so on which recognised evidentiary ground?

Available grounds (you may choose only from these):
{grounds}

Rules:
- An objection is counsel asking the court to disallow a question or an answer. "Objection, My Lord", "I object", "that is hearsay", "he is leading the witness" are all objections.
- Interrupting to make a submission, ask a question, or simply continue arguing is NOT an objection. Say so rather than forcing it into a ground.
- If it is clearly an objection but no listed ground fits, return isObjection true with groundId null.

Respond with strict JSON only:
{{"isObjection": boolean, "groundId": string or null, "restated": string, "reason": string}}
- "restated" is the objection put in proper courtroom form, one sentence, beginning "Objection, My Lord" — empty string if this was not an objection.
- "reason" is a short private note (not spoken)."""


async def run_interjection(request: TurnRequest) -> dict:
    """Classifies a student interruption and, if it is an objection, rules on it.

    Returns the same event/audit shape a turn does, so the API persists and
    speaks it through exactly the same path.
    """
    context = await build_context(request)

    if not context.grounds:
        return _empty("No objection grounds are available from the corpus.")

    grounds_block = "\n".join(
        f"- {g.id}: {g.label} ({g.citation}) — {g.description}"
        for g in context.grounds
    )
    user = (
        f"{context.case_context()}\n\n"
        f"Exchange so far in this phase:\n{context.working_memory_text()}\n\n"
        f'Counsel interrupted and said:\n"{context.utterance}"\n\n'
        "Classify that interruption."
    )

    payload = await json_completion(
        _CLASSIFY_SYSTEM.format(grounds=grounds_block), user, max_tokens=400
    )

    if not payload.get("isObjection"):
        logger.info("Interruption was not an objection")
        return _empty("The interruption was not an objection.")

    ground = next(
        (g for g in context.grounds if g.id == payload.get("groundId")), None
    )
    if ground is None:
        # Counsel objected but named no ground the corpus can back. The bench is
        # not asked to rule on law we cannot cite; the student is told to name a
        # ground instead. Inventing one for them would teach the wrong lesson.
        logger.info("Objection raised without a citable ground")
        return _empty(
            "The Bench notes an objection but no recognised ground was stated. "
            "Counsel must specify the ground relied upon."
        )

    objection = Objection(
        groundId=ground.id,
        label=ground.label,
        citation=ground.citation,
        heading=ground.heading,
        content=ground.content,
        interjection=(payload.get("restated") or "").strip()
        or f"Objection, My Lord — {ground.label.lower()}.",
    )

    ruling = await rule_on_objection(context, objection)

    events = [
        CourtEvent(
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
    ]

    spoken = "\n".join(event.transcript for event in events)
    audit = await audit_citations(spoken)
    return {
        "isObjection": True,
        "objection": objection.model_dump(by_alias=True),
        "events": [event.model_dump(by_alias=True) for event in events],
        "citationAudit": {
            "total": audit.total,
            "verified": audit.verified,
            "hallucinated": audit.hallucinated,
            "accuracy": audit.accuracy,
            "checks": [check.to_dict() for check in audit.checks],
            # The student's own interruption is the source of any citation here,
            # so nothing in a ruling on it counts as the agent inventing law.
            "agentFabricated": [],
        },
        "note": None,
    }


def _empty(note: str) -> dict:
    """No objection to rule on. The note is for the record, not for the bench."""
    return {
        "isObjection": False,
        "objection": None,
        "events": [],
        "citationAudit": {
            "total": 0,
            "verified": 0,
            "hallucinated": 0,
            "accuracy": None,
            "checks": [],
            "agentFabricated": [],
        },
        "note": note,
    }
