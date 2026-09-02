"""The judge: a ReAct agent that reads the law before it rules.

When an objection is on the table the judge does not answer from memory. It runs
a bounded Thought→Action→Observation loop: it may call the ``search_statute``
tool to pull the neighbouring provisions an objection actually turns on (a
leading-question objection under QSO Art. 137 is decided by reading it together
with 136 and 138), observe what the corpus returns, and only then rule. Every
step of that loop is recorded and returned, so the ruling is not just grounded
but *shown* to be grounded.

The judge also presides — moderating openings and closings — but that role is a
single in-character response, not a reasoning loop.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.agents.llm import text_completion
from app.agents.state import (
    AgentContext,
    GroundedProvision,
    JudgeRuling,
    Objection,
    ReasoningStep,
)
from app.agents.tools import SEARCH_STATUTE_TOOL, run_search_statute
from app.config import get_settings
from app.rag.embeddings import get_client

logger = logging.getLogger(__name__)

# Cap on tool-calling rounds. Three is enough to read a provision and its
# neighbours; the cap stops a model from looping on the corpus indefinitely and
# bounds the latency and token cost of a single ruling.
MAX_TOOL_ROUNDS = 3

@dataclass(frozen=True, slots=True)
class ObjectorVoice:
    """How the bench is told who objected, and to what.

    Not a cosmetic detail. Whether a question is leading depends on whose
    witness is on the stand, so a bench told the wrong party raised the
    objection can rule the wrong way on identical words. The graph raises
    objections as opposing counsel; the student raises them by hand from the
    web app, against something already said on the record.
    """

    #: Substituted into the system prompt.
    system_line: str
    #: Introduces the words being objected to.
    utterance_intro: str
    #: Names the objector in the user block.
    objects_line: str


OPPOSING_COUNSEL = ObjectorVoice(
    system_line="Opposing counsel",
    utterance_intro="The student asked the witness",
    objects_line="OPPOSING COUNSEL OBJECTS",
)

STUDENT = ObjectorVoice(
    # Trailing comma: the system prompt reads "{objector} has raised an
    # objection", and without it the clause runs on.
    system_line="The student, appearing as counsel,",
    # The student objects to what someone else has just said, not to their own
    # question, so the words in front of the bench are somebody else's.
    utterance_intro="The words objected to, as spoken on the record",
    objects_line="THE STUDENT, APPEARING AS COUNSEL, OBJECTS",
)


_RULING_SYSTEM = """You are a learned judge of a Pakistani High Court presiding over a moot court. {objector} has raised an objection. Rule on it.

You have a tool, search_statute, that reads the statute corpus. Use it to read the provision the objection rests on together with its neighbouring provisions before you rule — an evidentiary objection is decided by what the law actually says, not by how it sounds. Call the tool as many times as you need (up to a few), then rule.

Rule only on statutory text you have actually read (the provision handed to you plus anything the tool returns). Cite provisions by their exact citation string. Do not invent an article or section that has not appeared in what you were given or what the tool returned.

When you are ready to rule, stop calling tools and respond with strict JSON only:
{"ruling": "sustained" or "overruled", "explanation": "2-3 sentences in clear, simple, easy-to-understand English citing the provisions relied on", "impact": "one simple sentence instructing counsel or the witness in plain English", "citation": "the primary provision citation string"}"""


def _ruling_system(voice: ObjectorVoice) -> str:
    # `.replace` rather than `.format`: the prompt ends in a JSON schema, and
    # formatting would require doubling every brace in it. A doubled brace in a
    # prompt is a bug the next edit reintroduces.
    return _RULING_SYSTEM.replace("{objector}", voice.system_line)


def _dedupe(provisions: list[GroundedProvision]) -> list[GroundedProvision]:
    seen: set[str] = set()
    out: list[GroundedProvision] = []
    for provision in provisions:
        if provision.citation in seen:
            continue
        seen.add(provision.citation)
        out.append(provision)
    return out


async def rule_on_objection(
    context: AgentContext,
    objection: Objection,
    objector: ObjectorVoice = OPPOSING_COUNSEL,
) -> JudgeRuling:
    """Runs the judge's ReAct loop and returns a grounded ruling.

    `objector` defaults to opposing counsel, which is the graph's caller and
    every caller that predates the student raising objections by hand. One
    bench rules on both: a second ruling prompt for hand-raised objections is
    exactly the drift `run_turn` being defined in terms of `run_turn_stream`
    exists to prevent.
    """
    settings = get_settings()
    client = get_client()

    user = (
        f"{context.case_context()}\n\n"
        f"Recent exchange:\n{context.working_memory_text()}\n\n"
        f'{objector.utterance_intro}:\n"{context.utterance}"\n\n'
        f"{objector.objects_line} on the ground of: {objection.label}\n"
        f"They say: \"{objection.interjection}\"\n\n"
        "THE PROVISION THIS GROUND RESTS ON:\n"
        f"{objection.citation} — {objection.heading}\n{objection.content}\n\n"
        "Read the relevant law with search_statute, then rule."
    )

    messages: list[dict] = [
        {"role": "system", "content": _ruling_system(objector)},
        {"role": "user", "content": user},
    ]

    reasoning: list[ReasoningStep] = []
    grounded: list[GroundedProvision] = [
        GroundedProvision(
            citation=objection.citation,
            heading=objection.heading,
            verified=False,
        )
    ]
    final_content: str | None = None

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = await client.chat.completions.create(
                model=settings.model_text,
                max_completion_tokens=900,
                tools=[SEARCH_STATUTE_TOOL],
                tool_choice="auto",
                messages=messages,
            )
        except Exception:
            logger.exception("Judge ruling call failed")
            break

        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        if not tool_calls:
            final_content = message.content
            break

        # Record the assistant's tool-call turn, then execute each call and feed
        # the observation back — the canonical ReAct Action/Observation cycle.
        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ],
            }
        )

        for call in tool_calls:
            observation, provisions = await run_search_statute(
                call.function.arguments
            )
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            query = arguments.get("query", "")
            # The thought is a required tool argument; the assistant message is
            # the fallback for the rarer case where a model narrates alongside
            # the call instead of inside it.
            thought = (arguments.get("thought") or message.content or "").strip()
            reasoning.append(
                ReasoningStep(
                    thought=thought,
                    action=f'search_statute("{query}")',
                    observation="; ".join(p["citation"] for p in provisions)
                    or "no match",
                )
            )
            grounded.extend(
                GroundedProvision(
                    citation=p["citation"],
                    heading=p["heading"],
                    verified=p["verified"],
                )
                for p in provisions
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": observation,
                }
            )

    ruling = _parse_ruling(final_content)
    if ruling is None:
        ruling = await _force_ruling(messages)

    ruling.reasoning = reasoning
    ruling.grounded = _dedupe(grounded)
    return ruling


def _parse_ruling(content: str | None) -> JudgeRuling | None:
    if not content:
        return None
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    verdict = str(data.get("ruling", "")).strip().lower()
    if verdict not in ("sustained", "overruled"):
        return None
    return JudgeRuling(
        ruling=verdict,  # type: ignore[arg-type]
        explanation=str(data.get("explanation", "")).strip(),
        impact=str(data.get("impact", "")).strip(),
        citation=(str(data.get("citation")).strip() or None)
        if data.get("citation")
        else None,
    )


async def _force_ruling(messages: list[dict]) -> JudgeRuling:
    """Last resort: demand a JSON ruling with no tools available.

    Reached only if the model exhausted its tool rounds without ruling. If even
    this fails the objection is overruled — the least disruptive default, since
    overruling lets a possibly-proper question stand rather than striking it.
    """
    settings = get_settings()
    try:
        response = await get_client().chat.completions.create(
            model=settings.model_text,
            max_completion_tokens=600,
            response_format={"type": "json_object"},
            messages=[
                *messages,
                {
                    "role": "user",
                    "content": "Rule now. Respond with the ruling JSON only.",
                },
            ],
        )
        ruling = _parse_ruling(response.choices[0].message.content)
        if ruling is not None:
            return ruling
    except Exception:
        logger.exception("Forced ruling failed")

    return JudgeRuling(
        ruling="overruled",
        explanation="The Bench is not persuaded the objection is made out on the "
        "material before it.",
        impact="Counsel may proceed.",
    )


_PRESIDE_SYSTEM = """You are a stern but fair judge presiding over a Pakistani court in a moot-court practice session. Speak in simple, clear, and easy-to-understand English while remaining respectful and measured: address the student as "counsel" or "learned counsel". Avoid overly dense, archaic, or complex legal jargon. Respond briefly (2-4 sentences) in plain language to what counsel just said — acknowledge the point, probe their legal reasoning or evidence with a straightforward question, or direct them procedurally when appropriate. Do not resolve the case yourself and do not give legal advice. If counsel now contradicts something they put on the record earlier, note it clearly. Stay strictly in character."""


async def preside(context: AgentContext) -> str:
    """The judge moderating an opening or closing (no objection pending)."""
    system = _PRESIDE_SYSTEM
    if context.memory_prompt:
        system = f"{system}\n\n{context.memory_prompt}"
    user = (
        f"{context.case_context()}\n\n"
        f"Exchange so far in this phase:\n{context.working_memory_text()}\n\n"
        f'Counsel just said:\n"{context.utterance}"\n\n'
        "Respond from the bench."
    )
    return await text_completion(system, user, max_tokens=300)
