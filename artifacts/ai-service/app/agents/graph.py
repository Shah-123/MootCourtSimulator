"""The courtroom as a LangGraph StateGraph.

The nodes are the agents; the conditional edges are the supervisor. A single
student utterance enters at START and is routed through as many agents as the
moment requires:

    START
      │  (a witness is on the stand?)
      ├── yes ─▶ objection_screen ──(objection?)─▶ judge_ruling
      │              │  no                              │
      │              ▼                                  ├─ sustained ─▶ END
      │         (primary responder)                    └─ overruled ─▶ (witness answers)
      └── no ─────────┴──▶  witness_testify | counsel_argues | bench_presides ─▶ END

That routing is the whole point of #5: no single persona-swapping completion can
produce "opposing counsel objects, the judge reads the statute and rules, and
only then the witness answers" — three agents acting in sequence on one
question. Here that is just a path through the graph.

The compiled graph is built lazily and cached, because importing LangGraph is
not free; a service that never runs a turn never pays for it.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from app.agents.judge import preside, rule_on_objection
from app.agents.prosecutor import argue, screen_for_objection
from app.agents.state import (
    AgentContext,
    CourtEvent,
    CourtroomState,
    GroundedProvision,
    TurnRequest,
)
from app.agents.witness import testify
from app.grounding import list_objection_grounds
from app.memory import format_memory_for_prompt, load_session_memory
from app.rag.citations import (
    CitationAudit,
    CitationStatus,
    audit_citations,
    extract_citations,
)

logger = logging.getLogger(__name__)

# Node names, kept as constants so the routers and the graph wiring cannot drift.
OBJECTION_SCREEN = "objection_screen"
JUDGE_RULING = "judge_ruling"
WITNESS_TESTIFY = "witness_testify"
COUNSEL_ARGUES = "counsel_argues"
BENCH_PRESIDES = "bench_presides"

_PRIMARY_NODES = (WITNESS_TESTIFY, COUNSEL_ARGUES, BENCH_PRESIDES)


# ---------------------------------------------------------------------------
# Supervisor: pure routing over the shared context
# ---------------------------------------------------------------------------


def _route_primary(context: AgentContext) -> str:
    """Who answers when nothing is being objected to.

    The witness under examination answers if one is on the stand; otherwise the
    proceeding decides. That used to be a hardcoded ``cross_examination`` test,
    which was the trial's rule written as if it were the courtroom's: a writ
    has counsel answering in ``submissions`` and no cross at all. The phase→
    speaker map now lives with the proceeding, and a phase nobody claims falls
    through to the bench.
    """
    if context.active_witness is not None:
        return WITNESS_TESTIFY
    speaker = context.proceeding.primary_speaker.get(context.phase, "bench")
    return COUNSEL_ARGUES if speaker == "counsel" else BENCH_PRESIDES


def _route_entry(state: CourtroomState) -> str:
    context = state["context"]
    # Objections only make sense while a witness is being questioned. Openings
    # and closings go straight to the primary responder.
    if context.active_witness is not None:
        return OBJECTION_SCREEN
    return _route_primary(context)


def _route_after_objection(state: CourtroomState) -> str:
    if state.get("objection") is not None:
        return JUDGE_RULING
    return _route_primary(state["context"])


def _route_after_ruling(state: CourtroomState) -> str:
    from langgraph.graph import END

    ruling = state.get("ruling")
    # A sustained objection strikes the question: the witness does not answer it.
    if ruling is not None and ruling.ruling == "sustained":
        return END
    return _route_primary(state["context"])


# ---------------------------------------------------------------------------
# Nodes: each wraps one agent and returns a partial state update
# ---------------------------------------------------------------------------


async def _objection_screen_node(state: CourtroomState) -> dict:
    context = state["context"]
    objection = await screen_for_objection(context)
    if objection is None:
        return {"objection": None}
    event = CourtEvent(
        speaker="opposing_counsel",
        kind="objection",
        transcript=objection.interjection,
        ground=objection.ground_id,
        citation=objection.citation,
        grounded=[
            GroundedProvision(
                citation=objection.citation,
                heading=objection.heading,
                verified=False,
            )
        ],
    )
    return {"objection": objection, "events": [event]}


async def _judge_ruling_node(state: CourtroomState) -> dict:
    context = state["context"]
    objection = state["objection"]
    assert objection is not None  # only reached when an objection was raised
    ruling = await rule_on_objection(context, objection)
    event = CourtEvent(
        speaker="judge",
        kind="ruling",
        transcript=f"[{ruling.ruling.upper()}] {ruling.explanation} {ruling.impact}".strip(),
        ruling=ruling.ruling,
        citation=ruling.citation,
        reasoning=ruling.reasoning,
        grounded=ruling.grounded,
    )
    return {"ruling": ruling, "events": [event]}


async def _witness_testify_node(state: CourtroomState) -> dict:
    # The witness returns its grounding decision alongside the words. Carried
    # into `reasoning` so the same trace the bench gets — why this was said —
    # is available for the witness, whose failure mode (inventing a fact to fit
    # the question) is the one a student is least equipped to notice.
    transcript, reasoning = await testify(state["context"])
    if not transcript:
        return {}
    return {
        "events": [
            CourtEvent(
                speaker="witness",
                kind="testimony",
                transcript=transcript,
                reasoning=reasoning,
            )
        ]
    }


async def _counsel_argues_node(state: CourtroomState) -> dict:
    transcript = await argue(state["context"])
    if not transcript:
        return {}
    return {
        "events": [
            CourtEvent(
                speaker="opposing_counsel", kind="argument", transcript=transcript
            )
        ]
    }


async def _bench_presides_node(state: CourtroomState) -> dict:
    transcript = await preside(state["context"])
    if not transcript:
        return {}
    return {
        "events": [CourtEvent(speaker="judge", kind="bench", transcript=transcript)]
    }


# ---------------------------------------------------------------------------
# Graph assembly (compiled once, cached)
# ---------------------------------------------------------------------------

_compiled = None


def build_graph():
    """Wires and compiles the courtroom graph."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(CourtroomState)
    graph.add_node(OBJECTION_SCREEN, _objection_screen_node)
    graph.add_node(JUDGE_RULING, _judge_ruling_node)
    graph.add_node(WITNESS_TESTIFY, _witness_testify_node)
    graph.add_node(COUNSEL_ARGUES, _counsel_argues_node)
    graph.add_node(BENCH_PRESIDES, _bench_presides_node)

    entry_targets = {name: name for name in (OBJECTION_SCREEN, *_PRIMARY_NODES)}
    graph.add_conditional_edges(START, _route_entry, entry_targets)

    after_objection = {JUDGE_RULING: JUDGE_RULING, **{n: n for n in _PRIMARY_NODES}}
    graph.add_conditional_edges(OBJECTION_SCREEN, _route_after_objection, after_objection)

    after_ruling = {END: END, **{n: n for n in _PRIMARY_NODES}}
    graph.add_conditional_edges(JUDGE_RULING, _route_after_ruling, after_ruling)

    for node in _PRIMARY_NODES:
        graph.add_edge(node, END)

    return graph.compile()


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def graph_mermaid() -> str:
    """The compiled graph as a Mermaid diagram (for docs and slides)."""
    return get_graph().get_graph().draw_mermaid()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def build_context(request: TurnRequest) -> AgentContext:
    memory = await load_session_memory(request.session_id)
    # Scoped to the proceeding, so opposing counsel is never even shown a
    # ground the matter cannot engage. In a writ this is empty, and
    # screen_for_objection returns early on an empty catalogue — the objection
    # screen does not run and does not bill.
    grounds = await list_objection_grounds(request.case.proceeding_type)
    context = AgentContext(
        request=request,
        memory_prompt=format_memory_for_prompt(memory, request.phase),
        grounds=grounds,
    )
    # Read back off the context rather than off the request: a proceeding with
    # no witness box has nobody on the stand regardless of what was sent, and
    # that judgement belongs in one place.
    witness = context.active_witness
    if witness is not None:
        context.witness_memory_prompt = format_memory_for_prompt(
            memory, request.phase, as_witness=witness.name
        )
    return context


def _audit_to_dict(
    audit: CitationAudit, echoed: frozenset[str] = frozenset()
) -> dict:
    """Serialises an audit, marking citations the student had already made.

    The audit reports which provisions in a block of text are absent from the
    corpus. It cannot tell an agent *relying* on a made-up provision from one
    *naming it in order to reject it* — and the red-team eval caught it doing
    exactly that, flagging the judge for fabrication while the judge was
    correctly refusing a section the student had invented. So citations the
    student already put on the record this turn are marked, and
    ``agentFabricated`` carries only what the agent introduced by itself.

    ``hallucinated`` is left alone: it is what the batch endpoint and the
    existing logs already report, and narrowing it here would silently change a
    number other things depend on.
    """
    checks = []
    agent_fabricated: list[str] = []
    for check in audit.checks:
        payload = check.to_dict()
        key = f"{check.statute_code}:{check.section_number.upper()}"
        payload["echoedFromStudent"] = key in echoed
        if check.status is CitationStatus.NOT_FOUND and key not in echoed:
            agent_fabricated.append(check.raw)
        checks.append(payload)

    return {
        "total": audit.total,
        "verified": audit.verified,
        "hallucinated": audit.hallucinated,
        "accuracy": audit.accuracy,
        "checks": checks,
        "agentFabricated": agent_fabricated,
    }


async def run_turn_stream(request: TurnRequest) -> AsyncIterator[dict]:
    """Runs one student turn, yielding each agent event as its node completes.

    Same graph, same nodes, same order as a batch run — the only difference is
    *when* the caller learns about an event. That difference is the whole point
    for voice: returning nothing until the judge had also finished reasoning put
    ~16s of silence in front of the student, because counsel's objection cannot
    be spoken before the caller has it. Streaming lets the objection be heard
    while the bench is still reading statute.

    Ends with a single ``summary`` message carrying the objection, the primary
    speaker and the turn-level audit.
    """
    context = await build_context(request)
    state: CourtroomState = {
        "context": context,
        "events": [],
        "objection": None,
        "ruling": None,
    }

    events: list[CourtEvent] = []
    objection = None

    # Provisions the student themself put on the record this turn. An agent that
    # repeats one while rejecting it has not fabricated anything.
    echoed = frozenset(
        f"{code}:{number}"
        for _raw, code, number in extract_citations(request.utterance)
    )

    # ``updates`` yields each node's own return value as it completes; the graph
    # is strictly sequential, so this is the order the courtroom heard them in.
    async for update in get_graph().astream(state, stream_mode="updates"):
        for node_update in update.values():
            if not isinstance(node_update, dict):
                continue
            if node_update.get("objection") is not None:
                objection = node_update["objection"]

            for event in node_update.get("events") or []:
                events.append(event)
                # Audited before it is spoken rather than after the turn is
                # over: a fabricated provision should be flagged on the
                # utterance that carried it, while that utterance is still the
                # thing the student is hearing. The audit is a regex pass over
                # an in-memory index, so this costs no model call.
                yield {
                    "type": "event",
                    "event": event.model_dump(by_alias=True),
                    "objection": (
                        objection.model_dump(by_alias=True)
                        if objection is not None
                        else None
                    ),
                    "citationAudit": _audit_to_dict(
                        await audit_citations(event.transcript), echoed
                    ),
                }

    # The turn-level audit is taken over the joined transcript exactly as it
    # always was, so a provision two agents both cite is still counted once and
    # the number the batch caller sees is unchanged.
    spoken = "\n".join(event.transcript for event in events)
    yield {
        "type": "summary",
        "objection": (
            objection.model_dump(by_alias=True) if objection is not None else None
        ),
        "primarySpeaker": events[-1].speaker if events else None,
        "citationAudit": _audit_to_dict(await audit_citations(spoken), echoed),
    }


async def run_turn(request: TurnRequest) -> dict:
    """Runs one student turn and returns the whole thing at once.

    Defined in terms of :func:`run_turn_stream` rather than beside it, so the
    text turn and the voice turn cannot drift into two different courtrooms.
    Persistence and voice stay with the Node API; this only reasons.
    """
    events: list[dict] = []
    summary: dict = {}

    async for payload in run_turn_stream(request):
        if payload["type"] == "event":
            events.append(payload["event"])
        else:
            summary = payload

    return {
        "events": events,
        "objection": summary.get("objection"),
        "primarySpeaker": summary.get("primarySpeaker"),
        "citationAudit": summary.get("citationAudit"),
    }
