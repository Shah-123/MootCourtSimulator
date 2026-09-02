"""Grounded generation of moot-court practice cases.

Reasoning lives in this service, so case generation lives here rather than in the
Express route it was moved out of. Express keeps validation and persistence and
calls across for the model work — the same split verdict scoring already uses.

A generated case now carries a structured brief (facts, grounds, prayer) rather
than a single summary paragraph, because grounds are what a student actually
argues and prayer is what they ask the bench for. That brief is also read by the
courtroom agents, which is why every list here is capped: the brief is rendered
into `AgentContext.case_context()` and therefore rides in every agent prompt.

Grounds are prose that *contains citations*, so they are audited the same way
`applicableLaws` always has been. Constraining the prompt to a retrieved palette
reduces fabrication; it does not eliminate it, and a student must never be shown
a section number the corpus could not confirm.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings
from app.grounding import retrieve_area_palette
from app.proceedings import TRIAL, WRIT, profile_for
from app.rag.citations import CitationStatus, audit_citations
from app.rag.embeddings import get_client
from app.rag.retrieval import format_sections_for_prompt

logger = logging.getLogger(__name__)

# Caps on the brief. These are not cosmetic: the brief is rendered into every
# agent prompt via case_context(), so an unbounded facts list would multiply the
# per-turn cost across the objection screen, the ruling, the testimony and the
# bench. Trimming happens here, server-side, rather than being trusted from the
# model.
MAX_FACTS = 8
MAX_GROUNDS = 6
MAX_PRAYER = 5
MAX_PARTIES = 6
MAX_WITNESSES = 3
CAP_ITEM = 400

# A brief that survives the citation audit with fewer than two grounds is not a
# pleading worth arguing against, so it is rejected rather than persisted thin.
MIN_GROUNDS = 2

# Which proceeding an area is drafted as.
#
# Not a free choice on the request: a criminal prosecution is tried and an
# Article 199 petition is not, and letting a student pick would produce a
# criminal trial with no witness box or a writ with a cross-examination. The
# OpenAPI contract gates the areas (DraftableAreaOfLaw); this decides how each
# one is heard. An area absent here is drafted as a trial, which is what every
# case that predates proceeding types already is.
AREA_PROCEEDING: dict[str, str] = {
    "Criminal": TRIAL,
    "Constitutional": WRIT,
}

# Server-assigned so labels stay contiguous after a ground is dropped by the
# audit: a brief that jumps from "A." to "C." tells the student a ground was
# removed without telling them why.
_GROUND_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PRAYER_LABELS = "abcdefghijklmnopqrstuvwxyz"

CASE_SYSTEM_PROMPT = (
    "You are an expert Pakistani law professor designing moot-court practice "
    "problems. You draft them in the shape of a real filing before a Pakistani "
    "court: numbered facts, lettered grounds, and an itemised prayer."
)


def _clean(value: object, cap: int = CAP_ITEM) -> str:
    return str(value or "").strip()[:cap]


def _text_items(raw: object, limit: int) -> list[str]:
    """Pulls a capped list of non-empty strings out of untyped model output."""
    if not isinstance(raw, list):
        return []
    items = [_clean(entry) for entry in raw if isinstance(entry, (str, int, float))]
    return [item for item in items if item][:limit]


def _parties(raw: object, limit: int = MAX_PARTIES) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    parties = []
    for entry in raw[:limit]:
        if not isinstance(entry, dict):
            continue
        name = _clean(entry.get("name"), 120)
        if not name:
            continue
        parties.append(
            {
                "name": name,
                "role": _clean(entry.get("role"), 80) or "Party",
                "description": _clean(entry.get("description"), 200),
            }
        )
    return parties


def _witnesses(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    witnesses = []
    for entry in raw[:MAX_WITNESSES]:
        if not isinstance(entry, dict):
            continue
        name = _clean(entry.get("name"), 120)
        statement = _clean(entry.get("statement"), CAP_ITEM)
        # An empty statement makes witness_examination unplayable: witness.py
        # puts it verbatim into the system prompt.
        if not name or not statement:
            continue
        witnesses.append(
            {
                "name": name,
                "role": _clean(entry.get("role"), 80) or "Witness",
                "statement": statement,
            }
        )
    return witnesses


# What the drafter is told about the proceeding, and whether a witness list is
# asked for at all.
#
# A writ drafted with three eyewitnesses is not a slightly imperfect writ — it
# is a trial wearing the wrong name, and the student would open a case whose
# witnesses can never be called. The instruction and the JSON shape therefore
# move together.
_POSTURE = {
    TRIAL: (
        "This matter is tried. Evidence is led orally through witnesses, so "
        "build in contested facts that testimony can decide."
    ),
    WRIT: (
        "This matter is a constitutional petition under Article 199 of the "
        "Constitution of Pakistan, heard on the record. There is no witness "
        "box: the facts come from affidavits and annexures, and the matter is "
        "argued on the law. Draft no witnesses and do not build the dispute "
        "around a contested eyewitness account. It must turn on the legality "
        "of the impugned action and the rights invoked."
    ),
}

_WITNESS_SHAPE = (
    '  "witnesses": array of 2-{max_witnesses} objects '
    '{{ "name": string, "role": string (relation to case, e.g. "Eyewitness"), '
    '"statement": string (2-3 sentences of their testimony) }}'
)


def _build_prompt(
    area_of_law: str,
    difficulty: str,
    proceeding_type: str,
    palette_block: str,
    allowed: list[str],
) -> str:
    profile = profile_for(proceeding_type)
    posture = _POSTURE.get(proceeding_type, _POSTURE[TRIAL])
    # The prayer trails the JSON body for a writ, so the comma that used to
    # separate it from "witnesses" has to go with it.
    prayer_line = f'  "prayer": array of 2-{MAX_PRAYER} strings'
    if profile.has_witness_box:
        prayer_line += ",\n" + _WITNESS_SHAPE.format(
            max_witnesses=MAX_WITNESSES
        )

    return f"""Generate a realistic, original moot-court practice case under Pakistani law for a final-year law student. Area of law: {area_of_law}. Difficulty: {difficulty}.

{posture}

You have been given the full text of the provisions available to you below. Build the dispute so that it genuinely turns on some of them.

AVAILABLE PROVISIONS:
{palette_block}

Rules for citations, in "applicableLaws" and inside every ground:
- Cite ONLY from this exact list: {"; ".join(allowed)}
- Reproduce each citation string exactly as written above.
- Cite 2-4 provisions that the dispute actually turns on. Do not pad the list.
- Never invent a section or article number that does not appear above.

Draft the case as a filing would be drafted:
- "facts" are the numbered factual averments, in chronological order, each one sentence or two. They tell the story; they do not argue it.
- "grounds" are the legal propositions the case stands on. Each ground must state a proposition of law and name the provision it rests on, drawn only from the list above. This is the argument the student will have to defend.
- "prayer" is the specific relief sought from the court, itemised. Each item is something a court could actually order.

Respond with strict JSON only, matching this shape:
{{
  "title": string (short, formal case title, e.g. "State v. Ahmed Khan"),
  "summary": string (3-5 sentences describing the dispute and procedural posture),
  "court": string (the court seised of the matter, e.g. "Lahore High Court"),
  "caseNumber": string (a plausible cause number, e.g. "Crl. Misc. No. 412 of 2026"),
  "jurisdictionInvoked": string (the provision conferring jurisdiction, or "" if not applicable),
  "applicableLaws": string (comma-separated citations drawn only from the list above),
  "petitioners": array of 1-3 objects {{ "name": string, "role": string (e.g. "Petitioner", "Appellant", "Complainant"), "description": string (one clause on who they are) }},
  "respondents": array of 1-3 objects {{ "name": string, "role": string (e.g. "Respondent", "Accused", "The State"), "description": string }},
  "facts": array of 4-{MAX_FACTS} strings,
  "grounds": array of {MIN_GROUNDS}-{MAX_GROUNDS} strings,
{prayer_line}
}}"""


async def _surviving_grounds(grounds: list[str]) -> tuple[list[str], list[dict]]:
    """Drops any ground citing a provision that does not exist.

    The audit is a local index lookup, not a model call, so checking each ground
    individually costs nothing and tells us exactly which citation was invented.
    An `uncovered` instrument is logged but kept: that means real law we do not
    hold, which is a coverage gap, not a fabrication.
    """
    kept: list[str] = []
    dropped: list[dict] = []

    for ground in grounds:
        audit = await audit_citations(ground)
        invented = [
            check.raw
            for check in audit.checks
            if check.status is CitationStatus.NOT_FOUND
        ]
        if invented:
            dropped.append({"ground": ground, "citations": invented})
            continue
        kept.append(ground)

    return kept, dropped


async def generate_case(area_of_law: str, difficulty: str) -> dict[str, Any]:
    """Generates one practice case, grounded in the corpus and audited.

    Raises ValueError when the model returns something that will not be persisted
    — an unparseable body, no parties, or too few grounds left standing after the
    citation audit — so a bad case is rejected rather than written to the
    database.
    """
    # How this area is heard decides the shape of the filing, whether witnesses
    # are drafted at all, and — once the case is stored — which phases a session
    # on it runs through.
    proceeding_type = AREA_PROCEEDING.get(area_of_law, TRIAL)
    profile = profile_for(proceeding_type)

    # Retrieve a palette of real provisions first, then constrain generation to
    # it. Without this the model invents plausible-looking section numbers, and a
    # moot-court tool that teaches fabricated citations is worse than useless.
    palette = await retrieve_area_palette(area_of_law)
    allowed = [item.section.citation for item in palette]
    if not allowed:
        raise ValueError(f"No provisions retrieved for area of law {area_of_law!r}")

    settings = get_settings()
    response = await get_client().chat.completions.create(
        model=settings.model_text,
        # Larger than the 2048 this used in Express: the brief roughly triples
        # the output, and a truncated JSON body fails the parse below.
        max_completion_tokens=4096,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": CASE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_prompt(
                    area_of_law,
                    difficulty,
                    proceeding_type,
                    format_sections_for_prompt(palette),
                    allowed,
                ),
            },
        ],
    )

    try:
        raw = json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError as err:
        raise ValueError(f"Generated case was not valid JSON: {err}") from err

    title = _clean(raw.get("title"), 200)
    summary = _clean(raw.get("summary"), 1200)
    if not title or not summary:
        raise ValueError("Generated case is missing a title or summary")

    petitioners = _parties(raw.get("petitioners"))
    respondents = _parties(raw.get("respondents"))
    if not petitioners or not respondents:
        raise ValueError("Generated case does not name both sides")

    grounds, dropped = await _surviving_grounds(
        _text_items(raw.get("grounds"), MAX_GROUNDS)
    )
    if dropped:
        logger.warning(
            "Dropped %d generated ground(s) citing provisions that do not exist: %s",
            len(dropped),
            dropped,
        )
    if len(grounds) < MIN_GROUNDS:
        raise ValueError(
            f"Only {len(grounds)} ground(s) survived the citation audit; "
            f"{MIN_GROUNDS} are required"
        )

    # Constraining the prompt reduces fabrication but does not eliminate it, so
    # every citation is checked against the corpus before the case is stored.
    audit = await audit_citations(_clean(raw.get("applicableLaws"), 600))
    citations = [
        {
            "citation": check.citation,
            "statuteCode": check.statute_code,
            "heading": check.heading or "",
            # The corpus's own provenance flag, not the audit status: an existing
            # provision whose text is unverified must still say so.
            "verified": check.verified_source,
        }
        for check in audit.checks
        if check.status is CitationStatus.VERIFIED and check.citation
    ]

    if audit.hallucinated:
        logger.warning(
            "Generated case cited %d provision(s) that do not exist; "
            "storing only verified citations: %s",
            audit.hallucinated,
            [
                check.raw
                for check in audit.checks
                if check.status is CitationStatus.NOT_FOUND
            ],
        )

    # The displayed string is rebuilt from verified citations only. A student can
    # never be shown a section number the corpus could not confirm.
    applicable_laws = (
        ", ".join(f"{entry['citation']} ({entry['heading']})" for entry in citations)
        if citations
        else _clean(raw.get("applicableLaws"), 600)
    )

    lead_petitioner = petitioners[0]
    lead_respondent = respondents[0]

    return {
        "title": title,
        "summary": summary,
        "applicableLaws": applicable_laws,
        # The scalar party columns keep the lead party, so everything that reads
        # a case today — the agents, the verdict, the case list — is unchanged.
        "petitionerName": lead_petitioner["name"],
        "petitionerRole": lead_petitioner["role"],
        "respondentName": lead_respondent["name"],
        "respondentRole": lead_respondent["role"],
        "proceedingType": proceeding_type,
        # Dropped rather than trusted for a proceeding with no witness box. The
        # prompt already says not to draft any, but a witness list that reached
        # the database would show a "call witness" control the route then
        # refuses, and the agents would be handed testimony nobody can give.
        "witnesses": (
            _witnesses(raw.get("witnesses")) if profile.has_witness_box else []
        ),
        "citations": citations,
        "brief": {
            "court": _clean(raw.get("court"), 160) or None,
            "caseNumber": _clean(raw.get("caseNumber"), 120) or None,
            "jurisdictionInvoked": _clean(raw.get("jurisdictionInvoked"), 200) or None,
            "petitioners": petitioners,
            "respondents": respondents,
            "facts": [
                {"label": str(number), "text": text}
                for number, text in enumerate(
                    _text_items(raw.get("facts"), MAX_FACTS), start=1
                )
            ],
            "grounds": [
                {"label": _GROUND_LABELS[position], "text": text}
                for position, text in enumerate(grounds)
            ],
            "prayer": [
                {"label": _PRAYER_LABELS[position], "text": text}
                for position, text in enumerate(
                    _text_items(raw.get("prayer"), MAX_PRAYER)
                )
            ],
        },
        "audit": {
            "total": audit.total,
            "verified": audit.verified,
            "hallucinated": audit.hallucinated,
            "droppedGrounds": dropped,
        },
    }
