"""Binding generated content to provisions that actually exist."""

from __future__ import annotations

from dataclasses import dataclass

from app.proceedings import TRIAL, profile_for
from app.rag.index import get_index
from app.rag.retrieval import RetrievedSection, search_statutes

# Seed queries used to pull a palette of provisions before a case exists.
#
# Case generation is a chicken-and-egg problem: we cannot retrieve law relevant
# to a case that has not been written yet. Each area maps to a broad query
# surfacing the provisions that area typically turns on, and the generator is
# then constrained to cite only from that palette.
#
# Areas with no corpus coverage deliberately have no statute filter — retrieval
# runs across everything and returns weaker matches, which the post-generation
# verification step catches.
#
# Six of these are still unreachable: `DraftableAreaOfLaw` in the OpenAPI
# contract gates generation to Criminal and Constitutional. The weak-match
# fallback below turned out not to be enough on its own — a Contract case
# answered out of s.415/s.489-F PPC still passes the citation audit, because
# the audit's ground truth is this same corpus, so nothing downstream flags it.
#
# Constitutional was in that list until the writ proceeding existed, and it was
# there for a different reason: the corpus grounded it fine, but the courtroom
# only modelled a trial with a witness box. That was a phase problem, not a
# statute problem, and the phase model fixed it.
#
# All eight are kept rather than deleted: each becomes correct again once its
# area is served, and the query is the part that takes thought.
AREA_SEED_QUERIES: dict[str, tuple[str, list[str] | None]] = {
    "Criminal": (
        "offence punishment intention culpable homicide theft cheating hurt "
        "investigation arrest bail evidence of witnesses",
        ["PPC_1860", "CRPC_1898", "QSO_1984"],
    ),
    # Narrowed to the Constitution when the area became draftable. QSO was in
    # this filter while the area was unreachable and harmless there; the moment
    # cases are actually drafted from this palette it stops being harmless,
    # because a writ is decided on the record and grounds resting on rules of
    # oral examination are grounds the proceeding cannot hear. The corpus holds
    # eight Articles — the fundamental-rights block plus Art. 199 — and a writ
    # turns on those.
    "Constitutional": (
        "fundamental rights due process equality before law writ jurisdiction "
        "of High Court liberty fair trial",
        ["CONST_1973"],
    ),
    "Civil": (
        "civil rights and obligations proof of documents burden of proof "
        "relief against public authority",
        None,
    ),
    "Family": (
        "marriage dissolution maintenance guardianship inheritance shares of "
        "heirs competence of witnesses",
        None,
    ),
    "Contract": (
        "agreement consideration breach of contract dishonestly issuing a "
        "cheque criminal breach of trust proof of documents",
        ["PPC_1860", "QSO_1984"],
    ),
    "Property": (
        "possession of property transfer title mutation dishonest "
        "misappropriation proof of title documents",
        None,
    ),
    "Corporate": (
        "company director fiduciary duty fraud cheating criminal breach of "
        "trust falsification of accounts",
        ["PPC_1860", "QSO_1984"],
    ),
    "Tort": (
        "negligence hurt caused to person compensation damages liability for "
        "act causing harm",
        None,
    ),
}


async def retrieve_area_palette(
    area_of_law: str, limit: int = 12
) -> list[RetrievedSection]:
    """Retrieves the palette of provisions a generated case may cite from."""
    query, codes = AREA_SEED_QUERIES.get(
        area_of_law, (f"{area_of_law} law dispute in Pakistan", None)
    )
    # Reranking a broad seed query wastes a call: at this stage we want recall
    # across the area, not precision on one question.
    return await search_statutes(
        query, top_k=limit, statute_codes=codes, rerank=False
    )


# ---------------------------------------------------------------------------
# Objection grounds
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GroundDefinition:
    id: str
    label: str
    statute_code: str
    section_number: str
    description: str


# Each ground is bound to a specific provision. Defining them here and
# resolving headings from the corpus means a ground can only be offered if the
# provision behind it exists — the UI cannot drift from the statute book.
#
# These were previously hardcoded in the web app, where "leading question" was
# attributed to QSO Art. 121. Leading questions are Arts. 136-138.
GROUND_DEFINITIONS: list[GroundDefinition] = [
    GroundDefinition(
        "hearsay",
        "Hearsay",
        "QSO_1984",
        "71",
        "The witness is relating what someone else said rather than what they "
        "directly perceived.",
    ),
    GroundDefinition(
        "leading_question",
        "Leading question in examination-in-chief",
        "QSO_1984",
        "137",
        "Counsel is suggesting the desired answer to their own witness.",
    ),
    GroundDefinition(
        "insulting_question",
        "Questions intended to insult or annoy",
        "QSO_1984",
        # Art. 148, not 143. The corpus originally filed this text under 143,
        # which is "Court to decide when question shall be asked"; the citation
        # audit could not catch it because the audit's ground truth *is* the
        # corpus. Confirmed against the official text with
        # `pnpm run statutes:verify qso-1984`.
        "148",
        "The question is needlessly offensive in form or designed to harass "
        "the witness.",
    ),
    GroundDefinition(
        "secondary_evidence",
        "Secondary evidence without foundation",
        "QSO_1984",
        # Art. 75 ("Proof of documents by primary evidence"), not 76. The
        # corpus had the whole documentary-evidence block shifted up by one —
        # its 75/76/77 were the official 74/75/76 — so this ground cited the
        # provision listing the *exceptions* rather than the rule requiring
        # primary evidence. Confirmed with `pnpm run statutes:verify qso-1984`.
        "75",
        "A copy is being tendered where the original is required and no "
        "exception has been established.",
    ),
    GroundDefinition(
        "irrelevant",
        "Irrelevant to the facts in issue",
        "QSO_1984",
        "133",
        "The examination has strayed beyond the relevant facts of the case.",
    ),
    GroundDefinition(
        "improper_impeachment",
        "Improper impeachment of the witness",
        "QSO_1984",
        "151",
        "Credit is being attacked otherwise than in the manner the law permits.",
    ),
    GroundDefinition(
        "police_statement",
        "Improper use of a statement made to police",
        "CRPC_1898",
        "162",
        "A section 161 statement is being used for a purpose the Code forbids.",
    ),
]


@dataclass(slots=True)
class ObjectionGround:
    id: str
    label: str
    description: str
    citation: str
    heading: str
    content: str
    verified: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "citation": self.citation,
            "heading": self.heading,
            "content": self.content,
            "verified": self.verified,
        }


async def list_objection_grounds(
    proceeding_type: str = TRIAL,
) -> list[ObjectionGround]:
    """Returns the grounds available in this proceeding, backed by the corpus.

    Two filters, and they reject for different reasons. A ground whose
    provision is missing from the corpus is one we cannot cite, so we do not
    offer it. A ground the proceeding does not engage is one that does not
    exist here at all — every ground below is an evidentiary examination
    ground, so a writ heard on the record returns an empty list. That empty
    list is the correct answer, not a degraded one.
    """
    profile = profile_for(proceeding_type)
    allowed = profile.objection_ground_ids
    index = await get_index()
    by_key = {
        f"{section.statute_code}:{section.section_number}": section
        for section in index.sections
    }

    grounds: list[ObjectionGround] = []
    for definition in GROUND_DEFINITIONS:
        if allowed is not None and definition.id not in allowed:
            continue
        section = by_key.get(f"{definition.statute_code}:{definition.section_number}")
        if section is None:
            continue
        grounds.append(
            ObjectionGround(
                id=definition.id,
                label=definition.label,
                description=definition.description,
                citation=section.citation,
                heading=section.heading,
                content=section.content,
                verified=section.verified,
            )
        )
    return grounds


async def find_objection_ground(
    ground_id: str, proceeding_type: str = TRIAL
) -> ObjectionGround | None:
    """Resolves one ground *within a proceeding*.

    Scoped rather than global so a ground the UI is not offering cannot be
    raised by posting its id directly at the manual-objection route.
    """
    for ground in await list_objection_grounds(proceeding_type):
        if ground.id == ground_id:
            return ground
    return None
