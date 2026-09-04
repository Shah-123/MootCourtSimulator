"""Shared state, request models and event types for the multi-agent courtroom.

The courtroom is modelled as a LangGraph ``StateGraph``: each agent — opposing
counsel, the judge, a witness — is a node, and the supervisor is the set of
conditional edges that route a single student utterance through however many
agents need to act on it. One spoken turn by the student can therefore produce
a *sequence* of AI responses (an objection, a ruling, then an answer), which is
what a real moot court sounds like and what a single persona-swapping
completion could never produce.

Everything that crosses the wire is camelCase to match the OpenAPI contract the
Node API and web app are generated from; internal fields stay snake_case.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

# The catalogue of objection grounds is resolved from the statute corpus in
# app.grounding; the agents reuse that type rather than defining a parallel one,
# so a ground can never be offered here that grounding would not vouch for.
from app.grounding import ObjectionGround

# ---------------------------------------------------------------------------
# Request payload (what the Node API sends for one student turn)
# ---------------------------------------------------------------------------

_CAMEL = ConfigDict(populate_by_name=True)


class WitnessBrief(BaseModel):
    model_config = _CAMEL
    name: str
    role: str
    statement: str


class BriefItem(BaseModel):
    """One numbered fact, lettered ground, or itemised prayer."""

    model_config = _CAMEL
    label: str
    text: str


class CaseParty(BaseModel):
    model_config = _CAMEL
    name: str
    role: str
    description: str = ""


class CaseBriefDetail(BaseModel):
    """The pleading behind a case: what is averred, argued, and asked for.

    Optional throughout. Cases seeded into the library, and every case generated
    before this existed, carry no brief — see ``case_context`` for why that has
    to stay indistinguishable from the old behaviour.
    """

    model_config = _CAMEL
    court: str | None = None
    case_number: str | None = Field(default=None, alias="caseNumber")
    jurisdiction_invoked: str | None = Field(default=None, alias="jurisdictionInvoked")
    petitioners: list[CaseParty] = Field(default_factory=list)
    respondents: list[CaseParty] = Field(default_factory=list)
    facts: list[BriefItem] = Field(default_factory=list)
    grounds: list[BriefItem] = Field(default_factory=list)
    prayer: list[BriefItem] = Field(default_factory=list)


class CaseBrief(BaseModel):
    model_config = _CAMEL
    title: str
    area_of_law: str = Field(alias="areaOfLaw")
    summary: str
    applicable_laws: str = Field(alias="applicableLaws")
    petitioner_name: str = Field(alias="petitionerName")
    petitioner_role: str = Field(alias="petitionerRole")
    respondent_name: str = Field(alias="respondentName")
    respondent_role: str = Field(alias="respondentRole")
    witnesses: list[WitnessBrief] = Field(default_factory=list)
    brief: CaseBriefDetail | None = None


class TurnBrief(BaseModel):
    model_config = _CAMEL
    speaker: str
    witness_name: str | None = Field(default=None, alias="witnessName")
    transcript: str


class TurnRequest(BaseModel):
    model_config = _CAMEL
    session_id: int = Field(alias="sessionId")
    phase: str
    student_side: Literal["petitioner", "respondent"] = Field(alias="studentSide")
    active_witness: str | None = Field(default=None, alias="activeWitness")
    case: CaseBrief
    utterance: str
    # Turns already spoken in the *current* phase, replayed verbatim as working
    # memory. Long-term memory of earlier phases is loaded server-side.
    working_memory: list[TurnBrief] = Field(
        default_factory=list, alias="workingMemory"
    )


class StatedObjectionRequest(TurnRequest):
    """An objection the student raised from the objection dialog.

    Unlike an interruption there is nothing to classify: counsel picked the
    ground from the corpus-backed catalogue, so ``ground_id`` is given and
    ``utterance`` is the argument offered in support of it. Everything else is
    an ordinary turn's context, because the bench rules on the same record
    however counsel got to their feet.
    """

    model_config = _CAMEL
    ground_id: str = Field(alias="groundId")


# ---------------------------------------------------------------------------
# Agent outputs
# ---------------------------------------------------------------------------

Speaker = Literal["judge", "opposing_counsel", "witness"]
EventKind = Literal["objection", "ruling", "testimony", "bench", "argument"]


class ReasoningStep(BaseModel):
    """One recorded step of an agent's reasoning before it spoke.

    Surfaced in the response so the reasoning is inspectable rather than hidden.
    The judge fills these with the Thought→Action→Observation steps of its tool
    loop — it reads statute before it rules, and the trace proves it. The
    witness fills a single step with what in its own statement let it answer, or
    why it could not, which is the same claim about a different record.
    """

    thought: str = ""
    action: str = ""
    observation: str = ""


class GroundedProvision(BaseModel):
    """A provision an agent relied on, carried for provenance in the UI."""

    citation: str
    heading: str
    verified: bool


class CourtEvent(BaseModel):
    """One AI utterance in the turn, ready for the Node API to persist and speak."""

    speaker: Speaker
    kind: EventKind
    transcript: str
    ground: str | None = None
    citation: str | None = None
    ruling: Literal["sustained", "overruled"] | None = None
    reasoning: list[ReasoningStep] = Field(default_factory=list)
    grounded: list[GroundedProvision] = Field(default_factory=list)


class Objection(BaseModel):
    """An objection opposing counsel chose to raise, bound to a real provision."""

    model_config = _CAMEL

    ground_id: str = Field(alias="groundId")
    label: str
    citation: str
    heading: str
    content: str
    interjection: str


class JudgeRuling(BaseModel):
    ruling: Literal["sustained", "overruled"]
    explanation: str
    impact: str
    citation: str | None = None
    reasoning: list[ReasoningStep] = Field(default_factory=list)
    grounded: list[GroundedProvision] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-turn context threaded through the graph (read-only)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AgentContext:
    """Everything the agents need for one turn, assembled once before the graph runs.

    Frozen for the duration of the turn: nodes read it, they never mutate it.
    Keeping case facts, memory and the ground catalogue here means each agent is
    grounded in the same shared picture of the proceedings.
    """

    request: TurnRequest
    memory_prompt: str
    grounds: list[ObjectionGround]
    # The same recollection, trimmed to what the witness on the stand is
    # entitled to. Held separately rather than swapped in per agent because the
    # bench and counsel read `memory_prompt` in the same turn and must still get
    # the whole record — only the witness was out of the room.
    witness_memory_prompt: str = ""

    @property
    def phase(self) -> str:
        return self.request.phase

    @property
    def utterance(self) -> str:
        return self.request.utterance

    @property
    def active_witness(self) -> WitnessBrief | None:
        name = self.request.active_witness
        if not name:
            return None
        for witness in self.request.case.witnesses:
            if witness.name == name:
                return witness
        # A witness on the stand who is not on the case file: fall back to a
        # bare brief so the graph still runs rather than 500s on bad state.
        return WitnessBrief(name=name, role="witness", statement="")

    def working_memory_text(self) -> str:
        rows = self.request.working_memory
        if not rows:
            return "(No exchanges yet in this phase.)"
        return "\n".join(
            f"{row.speaker}"
            f"{f' ({row.witness_name})' if row.witness_name else ''}: "
            f"{row.transcript}"
            for row in rows
        )

    def case_context(self) -> str:
        case = self.request.case
        side = self.request.student_side
        student_party = (
            case.petitioner_name if side == "petitioner" else case.respondent_name
        )
        opposing_party = (
            case.respondent_name if side == "petitioner" else case.petitioner_name
        )
        base = (
            f'Case: "{case.title}" ({case.area_of_law} matter under Pakistani law)\n'
            f"Summary: {case.summary}\n"
            f"Applicable laws: {case.applicable_laws}\n"
            f"The student represents the {side.upper()} ({student_party}); "
            f"opposing counsel represents {opposing_party}.\n"
            f"Current phase: {self.phase.replace('_', ' ')}."
        )

        # A case with no brief renders byte-identical to the version that
        # predated it. Every seeded library case is in that position, and the
        # bench must not start behaving differently for them.
        brief = case.brief
        if brief is None:
            return base

        blocks = [base]
        if brief.facts:
            blocks.append(
                "Facts as pleaded:\n"
                + "\n".join(f"  {item.label}. {item.text}" for item in brief.facts)
            )
        if brief.grounds:
            # The grounds are the argument the student has to defend, so the
            # bench and opposing counsel are told them explicitly rather than
            # having to infer them from the summary.
            blocks.append(
                "Grounds raised:\n"
                + "\n".join(f"  {item.label}. {item.text}" for item in brief.grounds)
            )
        if brief.prayer:
            blocks.append(
                "Relief sought:\n"
                + "\n".join(f"  ({item.label}) {item.text}" for item in brief.prayer)
            )
        return "\n\n".join(blocks)


class CourtroomState(TypedDict, total=False):
    """LangGraph state. ``events`` accumulates across nodes via the add reducer."""

    context: AgentContext
    events: Annotated[list[CourtEvent], operator.add]
    objection: Objection | None
    ruling: JudgeRuling | None
