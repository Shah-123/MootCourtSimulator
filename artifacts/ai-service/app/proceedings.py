"""How a matter is heard, and what that implies for the agents.

A proceeding decides two things this service cares about: who answers the
student inside a given phase, and which objection grounds opposing counsel may
raise at all. It deliberately does *not* hold a phase order — advancing a
session is bookkeeping rather than reasoning, so Express owns that half
(``lib/courtroom.ts``). The two halves name the same phases and answer
different questions about them, so there is nothing here for the other side to
contradict.

The distinction this exists to enforce is not cosmetic. Every one of the seven
grounds in ``app.grounding`` is an evidentiary examination ground, drawn from
the Qanun-e-Shahadat and s.162 CrPC. An Article 199 writ is heard on
affidavits and argument, with no witness box, so none of them can arise in one.
Offering them anyway would have the simulator teach a student a rule of
procedure that does not exist in the proceeding they are standing in — the
same class of error as citing a section the corpus cannot confirm, and it
deserves the same treatment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TRIAL = "trial"
WRIT = "writ"

# Who answers when nobody is on the stand. Kept as neutral tokens rather than
# graph node names so this module stays importable from anywhere in the service
# — ``app.grounding`` reads it, and the graph imports grounding.
PrimarySpeaker = Literal["bench", "counsel"]


@dataclass(frozen=True, slots=True)
class ProceedingProfile:
    id: str
    label: str

    #: Rendered into every agent prompt via ``AgentContext.case_context``. The
    #: bench and opposing counsel behave differently in a writ than in a trial,
    #: and telling them which one they are in is cheaper and more reliable than
    #: hoping they infer it from the pleading.
    context_line: str

    #: Phase -> who answers when no witness is on the stand. A phase missing
    #: from this map falls through to the bench, which is the safe default: the
    #: judge is the one participant present at every stage of every proceeding.
    primary_speaker: dict[str, PrimarySpeaker]

    #: Ground ids from ``app.grounding.GROUND_DEFINITIONS`` this proceeding
    #: permits. ``None`` means every ground the corpus can back — so a ground
    #: added later is live in a trial without an edit here, and still excluded
    #: from a writ, which is the direction the failure should point.
    objection_ground_ids: frozenset[str] | None

    @property
    def has_witness_box(self) -> bool:
        """Whether anyone can be examined in this proceeding.

        Derived from the phases that name a speaker rather than declared, for
        the same reason Express derives it: two hand-maintained statements of
        the same fact eventually disagree.
        """
        return "witness_examination" in self.primary_speaker or (
            "cross_examination" in self.primary_speaker
        )


PROFILES: dict[str, ProceedingProfile] = {
    TRIAL: ProceedingProfile(
        id=TRIAL,
        label="trial",
        context_line=(
            "This is a trial. Evidence is led orally through witnesses, and "
            "the ordinary rules of examination apply."
        ),
        # `witness_examination` is listed even though the witness on the stand
        # takes precedence, because it is what makes has_witness_box true and
        # because it is the honest statement of the phase: when no witness is
        # up, chief is conducted before the bench.
        primary_speaker={
            "witness_examination": "bench",
            "cross_examination": "counsel",
        },
        objection_ground_ids=None,
    ),
    WRIT: ProceedingProfile(
        id=WRIT,
        label="constitutional writ petition",
        context_line=(
            "This is a constitutional petition under Article 199 of the "
            "Constitution of Pakistan, heard on the record. There is no "
            "witness box and no oral evidence: the matter is argued on "
            "affidavits, the annexures and the law. Do not invite testimony, "
            "and do not raise or entertain evidentiary objections — none of "
            "the rules of examination are engaged in this proceeding."
        ),
        primary_speaker={"submissions": "counsel"},
        # Empty rather than None: not "we have not decided yet", but "none of
        # them apply here". screen_for_objection returns early on an empty
        # catalogue, so the objection screen never runs and never bills.
        objection_ground_ids=frozenset(),
    ),
}


def profile_for(proceeding_type: str | None) -> ProceedingProfile:
    """Resolves a stored proceeding type, falling back to a trial.

    The column is defaulted and not nullable, so this only fires on a value
    written by something outside this codebase, or on a payload from a caller
    that predates proceeding types — the eval harnesses and the simulate
    scripts among them. Treating those as trials is what keeps this change
    invisible to everything that was already working.
    """
    return PROFILES.get(proceeding_type or TRIAL, PROFILES[TRIAL])
