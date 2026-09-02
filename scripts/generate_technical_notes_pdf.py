"""Generates the CourtSimulator technical study notes as a PDF.

A companion to `generate_technical_guide_pdf.py`, aimed at a different reader:
this one is the engineering notebook rather than the defence brief. Every
subsystem is written up as *what it is, how it works, why it was chosen, and
what was rejected instead*, followed by a technical question bank.

Deliberately excludes the web UI: the notes cover the reasoning service, the
API boundary, retrieval, the agent graph, memory, voice transport, security and
LLMOps.

    python scripts/generate_technical_notes_pdf.py

Output: docs/CourtSimulator_Technical_Notes.pdf

Text is rendered with the built-in Type1 fonts, whose WinAnsi encoding has no
arrow or sigma glyph, so the prose uses "->" and ASCII throughout rather than
acquiring a font dependency for punctuation.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#101828")
NAVY = colors.HexColor("#1b3a5c")
ACCENT = colors.HexColor("#8a2b2b")
MUTED = colors.HexColor("#5b626c")
RULE = colors.HexColor("#d7dbe0")
CODE_BG = colors.HexColor("#f4f5f7")
BLOCK_BG = colors.HexColor("#faf7f2")
TABLE_ALT = colors.HexColor("#f7f8fa")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

BODY = ParagraphStyle(
    "body",
    fontName="Helvetica",
    fontSize=9.3,
    leading=13.6,
    textColor=INK,
    alignment=TA_JUSTIFY,
    spaceAfter=6,
)
BODY_TIGHT = ParagraphStyle("bodyTight", parent=BODY, spaceAfter=2)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.2, leading=11.6,
                       textColor=MUTED)
LEAD = ParagraphStyle("lead", parent=BODY, fontSize=10.2, leading=15.2,
                      textColor=NAVY, spaceAfter=9)

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=19, leading=23,
                    textColor=NAVY, spaceAfter=2)
H1_KICKER = ParagraphStyle("h1k", fontName="Helvetica-Bold", fontSize=8.5,
                           leading=11, textColor=ACCENT, spaceAfter=3)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12.6, leading=16,
                    textColor=NAVY, spaceBefore=13, spaceAfter=5)
H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.2, leading=13.5,
                    textColor=ACCENT, spaceBefore=9, spaceAfter=3)
CODE = ParagraphStyle("code", fontName="Courier", fontSize=7.9, leading=10.6,
                      textColor=INK, spaceAfter=0)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.2, leading=11.4,
                      alignment=0, spaceAfter=0)
CELL_H = ParagraphStyle("cellH", parent=CELL, fontName="Helvetica-Bold",
                        textColor=colors.white)
LABEL = ParagraphStyle("label", parent=CELL, fontName="Helvetica-Bold",
                       textColor=ACCENT, fontSize=7.6)
QUESTION = ParagraphStyle("q", parent=BODY, fontName="Helvetica-Bold",
                          fontSize=9.6, leading=13.4, textColor=NAVY,
                          alignment=0, spaceBefore=8, spaceAfter=3)
COVER_TITLE = ParagraphStyle("coverTitle", fontName="Helvetica-Bold",
                             fontSize=30, leading=35, textColor=NAVY,
                             alignment=TA_CENTER)
COVER_SUB = ParagraphStyle("coverSub", fontName="Helvetica", fontSize=12.5,
                           leading=18, textColor=ACCENT, alignment=TA_CENTER)
COVER_META = ParagraphStyle("coverMeta", fontName="Helvetica", fontSize=9,
                            leading=14, textColor=MUTED, alignment=TA_CENTER)


def x(text: str) -> str:
    """Escapes the three characters reportlab's mini-markup parser owns."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def p(text: str, style: ParagraphStyle = BODY):
    return Paragraph(text, style)


def h1(kicker: str, title: str):
    return [
        PageBreak(),
        Paragraph(kicker.upper(), H1_KICKER),
        Paragraph(title, H1),
        HRFlowable(width="100%", thickness=1.4, color=NAVY, spaceBefore=4,
                   spaceAfter=10),
    ]


def h2(title: str):
    return Paragraph(title, H2)


def h3(title: str):
    return Paragraph(title, H3)


def bullets(items, style=BODY_TIGHT):
    return [ListFlowable(
        [ListItem(Paragraph(item, style), leftIndent=10) for item in items],
        bulletType="bullet",
        bulletFontSize=7,
        bulletOffsetY=-1,
        leftIndent=12,
        spaceAfter=7,
    )]


def numbered(items, style=BODY_TIGHT):
    return [ListFlowable(
        [ListItem(Paragraph(item, style), leftIndent=12) for item in items],
        bulletType="1",
        bulletFontName="Helvetica-Bold",
        bulletFontSize=8.6,
        leftIndent=14,
        spaceAfter=7,
    )]


def code(text: str):
    """A fixed-width block on a tinted panel."""
    # Every space becomes non-breaking: reportlab collapses runs of whitespace
    # and strips leading spaces, which would destroy an ASCII diagram. Code
    # lines here are short enough never to wrap.
    lines = [Paragraph(x(line).replace(" ", "&nbsp;") or "&nbsp;", CODE)
             for line in text.strip("\n").split("\n")]
    flow = Table([[lines]], colWidths=[CONTENT_W])
    flow.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [flow, Spacer(1, 8)]


def table(headers, rows, widths, caption=None):
    data = [[Paragraph(cell, CELL_H) for cell in headers]]
    for row in rows:
        data.append([Paragraph(cell, CELL) for cell in row])

    total = float(sum(widths))
    col_widths = [CONTENT_W * (w / total) for w in widths]

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), TABLE_ALT))

    flow = Table(data, colWidths=col_widths, repeatRows=1)
    flow.setStyle(TableStyle(style))
    out = [flow]
    if caption:
        out.append(Spacer(1, 3))
        out.append(Paragraph(caption, SMALL))
    out.append(Spacer(1, 9))
    return out


def decision(title, what, how, why, instead, purpose=None):
    """The four-part decision record these notes are built out of."""
    rows = [("WHAT IT IS", what), ("HOW IT WORKS", how), ("WHY THIS", why)]
    if purpose:
        rows.append(("USED FOR", purpose))
    rows.append(("NOT THE ALTERNATIVE", instead))

    head = Paragraph(title, ParagraphStyle("dt", parent=CELL,
                                           fontName="Helvetica-Bold",
                                           fontSize=9.4,
                                           textColor=colors.white))
    body = [[Paragraph(label, LABEL), Paragraph(text, CELL)]
            for label, text in rows]

    flow = Table([[head, ""]] + body,
                 colWidths=[CONTENT_W * 0.21, CONTENT_W * 0.79])
    flow.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("BACKGROUND", (0, 1), (-1, -1), BLOCK_BG),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 1), (-1, -2), 0.35, RULE),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [flow, Spacer(1, 10)]


def note(text, label="NOTE"):
    flow = Table([[Paragraph(label, ParagraphStyle("nl", parent=LABEL,
                                                   textColor=NAVY)),
                   Paragraph(text, CELL)]],
                 colWidths=[CONTENT_W * 0.13, CONTENT_W * 0.87])
    flow.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef2f6")),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [flow, Spacer(1, 9)]


_QA = {"n": 0}


def qa(question, answer, extra=None):
    _QA["n"] += 1
    block = [
        Paragraph("Q%d. %s" % (_QA["n"], question), QUESTION),
        Paragraph("<b>A.</b> " + answer, BODY),
    ]
    if extra:
        block.extend(extra)
    block.append(HRFlowable(width="100%", thickness=0.4, color=RULE,
                            spaceBefore=1, spaceAfter=2))
    if extra is None and len(answer) < 850:
        return [KeepTogether(block)]
    return block


from reportlab.pdfgen import canvas as _canvas  # noqa: E402


class NumberedCanvas(_canvas.Canvas):
    """Two-pass canvas: page N of M can only be drawn once M is known."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._decorate(total)
            super().showPage()
        super().save()

    def _decorate(self, total):
        if self._pageNumber == 1:
            return
        self.saveState()
        self.setFont("Helvetica", 7.4)
        self.setFillColor(MUTED)
        self.drawString(MARGIN, PAGE_H - MARGIN + 8,
                        "CourtSimulator - Technical Notes")
        self.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN + 8,
                             "Architecture, design decisions and Q&A")
        self.setStrokeColor(RULE)
        self.setLineWidth(0.4)
        self.line(MARGIN, PAGE_H - MARGIN + 4, PAGE_W - MARGIN,
                  PAGE_H - MARGIN + 4)
        self.line(MARGIN, MARGIN - 10, PAGE_W - MARGIN, MARGIN - 10)
        self.drawString(MARGIN, MARGIN - 20,
                        "Voice-first moot-court simulator - Pakistani law")
        self.drawRightString(PAGE_W - MARGIN, MARGIN - 20,
                             "Page %d of %d" % (self._pageNumber, total))
        self.restoreState()


def cover():
    return [
        Spacer(1, 45 * mm),
        Paragraph("CourtSimulator", COVER_TITLE),
        Spacer(1, 5),
        Paragraph("Technical Notes", COVER_TITLE),
        Spacer(1, 10),
        HRFlowable(width="42%", thickness=1.6, color=ACCENT, hAlign="CENTER"),
        Spacer(1, 12),
        Paragraph("Architecture, Design Decisions and Technical Q&amp;A",
                  COVER_SUB),
        Spacer(1, 6),
        Paragraph("How the system works, why every component was chosen, "
                  "and what was rejected instead", COVER_META),
        Spacer(1, 30 * mm),
        Table(
            [[Paragraph("<b>Subject</b><br/>A voice-first, multi-agent moot-court "
                        "simulator for Pakistani law students: retrieval-augmented "
                        "generation over a verified statute corpus, a LangGraph "
                        "courtroom of autonomous agents, and a measured evaluation "
                        "harness.<br/><br/>"
                        "<b>Scope of these notes</b><br/>The reasoning service, the "
                        "service boundary, retrieval, the agent graph, memory, the "
                        "voice pipeline, security and LLMOps. The web interface is "
                        "deliberately out of scope.", COVER_META)]],
            colWidths=[CONTENT_W * 0.86],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BLOCK_BG),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]),
            hAlign="CENTER",
        ),
    ]


# ==========================================================================
# PART 1 - Orientation
# ==========================================================================


def part_orientation():
    s = h1("Part 1", "Orientation: what the system is and how to read these notes")

    s.append(p(
        "CourtSimulator is a moot-court simulator that a law student argues "
        "<b>by speaking</b>. The student picks a case, chooses a side, and works "
        "through five fixed phases - opening, witness examination, "
        "cross-examination, closing, verdict. On the other side of the bench are "
        "three independent AI agents: a judge, opposing counsel, and whichever "
        "witness is on the stand. Opposing counsel objects on its own initiative, "
        "the judge reads the actual statute before ruling, and a sustained "
        "objection stops the witness answering. At the end an AI judge scores the "
        "transcript, and every statutory citation on the record - the student's "
        "and the agents' - is checked against a corpus of real Pakistani law.",
        LEAD))

    s.append(p(
        "That description contains four hard technical problems, and each is a "
        "separate subsystem in this document: <b>find the right law</b> (hybrid "
        "retrieval), <b>never invent law</b> (citation audit and corpus "
        "verification), <b>make several agents act in sequence on one utterance</b> "
        "(the LangGraph courtroom), and <b>prove all of it with numbers</b> (the "
        "evaluation harness). Voice is the transport layer over the top of them."))

    s.append(h2("How these notes are organised"))
    s.append(p(
        "Every significant design choice is written as a four-part record, because "
        "that is the form the question always takes: what is this, how does it "
        "work, why this one, and why not the obvious alternative. The blocks look "
        "like this:"))

    s.extend(decision(
        "Example: how to read a decision block",
        what="One sentence naming the component and where it lives in the tree.",
        how="The mechanism - the actual algorithm, data flow or call sequence, "
            "with the constants that matter.",
        why="The constraint or the measurement that forced this choice. Where a "
            "number exists it is quoted.",
        instead="The alternative that a reader would reasonably expect, and the "
                "specific reason it is not used here. This is the half most "
                "documents omit.",
        purpose="Which part of the product depends on it - so the cost is "
                "attached to a benefit."))

    s.append(p(
        "Part 12 collapses every decision into one master table, and Part 13 is a "
        "question bank of 113 technical questions with answers. The "
        "appendix carries the numbers, the commands and the honest list of what "
        "is not finished."))

    s.append(h2("The one-paragraph architecture"))
    s.append(p(
        "Three services and one database. A React app talks only to an "
        "<b>Express API</b> over same-origin <font face='Courier'>/api/*</font> "
        "routes. Express owns the HTTP contract, session persistence and voice "
        "transport. Everything that needs a model - retrieval, grounding, memory, "
        "the agents, verdict scoring - is behind a <b>Python FastAPI service</b>. "
        "Both services read and write the same <b>PostgreSQL</b> database, but only "
        "one of them owns the schema. The browser never sees an OpenAI key and "
        "never reaches the Python service."))

    s.extend(code(
        "Browser (React 19 + Vite)\n"
        "   |  same-origin /api/*  (session cookie, no API keys)\n"
        "   v\n"
        "Express 5 API  ......  owns: OpenAPI contract, sessions, turns, verdicts,\n"
        "   |                          auth, rate limiting, audio transport (SSE)\n"
        "   |  HTTP/JSON + NDJSON stream\n"
        "   v\n"
        "Python FastAPI 'reasoning service'\n"
        "        owns: hybrid retrieval, citation audit, agent graph, memory,\n"
        "              case generation, verdict scoring, cost telemetry\n"
        "   |                                    |\n"
        "   v                                    v\n"
        "PostgreSQL (pg_trgm only)          OpenAI API\n"
        "   schema owned by Drizzle          text / embeddings / STT / TTS"))

    s.append(h2("The five numbers to remember"))
    s.extend(table(
        ["Claim", "Number", "Where it comes from"],
        [
            ["Retrieval finds the governing provision first",
             "hit@1 1.00, MRR 1.00 (reranked); 0.80 / 0.88 fusion-only",
             "20-query golden set, <font face='Courier'>pnpm run eval</font>"],
            ["The bench objects when it should and never leaks a sustained "
             "objection",
             "recall 1.00, precision 0.98, F1 0.99 (means over 3 runs); 0 routing "
             "leaks in 32 scenarios x every run",
             "<font face='Courier'>pnpm run eval:courtroom --runs 3</font>"],
            ["The judge discriminates good advocacy from bad",
             "strong 85-88 &gt; mixed 55-58 &gt; weak 25-35; citation accuracy "
             "100% / 50% / 0%",
             "3 transcripts of one case, scored repeatedly"],
            ["A witness does not invent evidence",
             "0 fabrications in 9 unanswerable questions; 17/17 outcomes correct",
             "<font face='Courier'>pnpm run eval:witness</font>"],
            ["A spoken turn starts sounding quickly enough to feel live",
             "first audio 8.1 s (was 16.1 s batched); counsel speaks at 6.9 s",
             "instrumented voice request, case 4"],
        ],
        [26, 30, 30]))

    s.extend(note(
        "The corpus is 53 provisions from four instruments - Qanun-e-Shahadat "
        "Order 1984 (20), Pakistan Penal Code 1860 (15), Code of Criminal "
        "Procedure 1898 (10), Constitution of Pakistan 1973 (8). 52 of them have "
        "been diffed word-for-word against an official print and carry "
        "<font face='Courier'>verified: true</font>. The one exception, "
        "Constitution Art. 199, is labelled in the interface rather than quietly "
        "presented as settled law.",
        "CORPUS"))

    return s


# ==========================================================================
# PART 2 - Architecture
# ==========================================================================


def part_architecture():
    s = h1("Part 2", "Architecture: three services, one database, one contract")

    s.append(p(
        "The system is split along a single line: <b>anything that calls a model "
        "lives in Python; anything that owns the HTTP contract, the database "
        "writes or the audio stream lives in Node</b>. That line is not "
        "aesthetic. It is what makes the reasoning testable in isolation, and it "
        "is why the evaluation harness can drive the exact functions the product "
        "calls rather than a copy of them.", LEAD))

    s.append(h2("2.1 Why three services and not one"))

    s.extend(decision(
        "Service split: React app / Express API / Python AI service",
        what="Three independently runnable processes - the Vite web app on :5173, "
             "an Express 5 API on :5000, and a FastAPI reasoning service on :8000 "
             "- sharing one PostgreSQL database and one root "
             "<font face='Courier'>.env</font>.",
        how="The browser calls same-origin <font face='Courier'>/api/*</font>. "
            "Express validates with generated Zod schemas, loads and writes rows "
            "with Drizzle, and calls the Python service through one typed client "
            "module (<font face='Courier'>src/lib/ai-service.ts</font>) for "
            "anything requiring a model. Python answers with plain JSON, or NDJSON "
            "when the caller wants events as they happen.",
        why="The AI stack that matters for this project - LangGraph, rank_bm25, "
            "numpy, sentence-transformers, MLflow, RAGAS - is Python. Putting "
            "reasoning where those libraries are means no reimplementation and no "
            "second-class port. Keeping HTTP, sessions and audio in Node means the "
            "contract-first tooling (OpenAPI to typed client) works end to end.",
        instead="A single Node service calling OpenAI directly was the starting "
                "point and was migrated away from: it could not use LangGraph, and "
                "agent behaviour could only be tested through HTTP. A single "
                "Python service (FastAPI serving everything) would have thrown "
                "away the generated TypeScript client and put the React app's "
                "types back in a human's hands.",
        purpose="Retrieval, agents, memory, scoring, evaluation - all reachable "
                "from a Python REPL and from pytest without an HTTP server."))

    s.append(h3("The boundary is enforced, not just documented"))
    s.append(p(
        "One rule: <b>no prompt, model call or agent decision may exist in the "
        "Express codebase</b>. Case generation used to break it and was moved "
        "behind <font face='Courier'>POST /cases/generate</font>. Exactly one "
        "exception remains - the manually-raised objection ruling in "
        "<font face='Courier'>routes/sessions.ts</font> still builds a prompt in "
        "Node - and it is recorded as pending work rather than treated as a "
        "pattern. Transcription and speech synthesis are <i>not</i> exceptions: "
        "they are transport, not reasoning. Nothing decides anything there."))

    s.append(h2("2.2 Schema ownership: one writer of truth"))

    s.extend(decision(
        "Drizzle owns the schema; Python uses raw SQL",
        what="All tables are defined once, in TypeScript, in "
             "<font face='Courier'>lib/db/src/schema/*.ts</font>. The Python "
             "service reads and writes those tables with hand-written SQL through "
             "asyncpg and defines no models and no migrations.",
        how="<font face='Courier'>pnpm --filter @workspace/db run push</font> "
            "applies the schema. Python opens an asyncpg pool (min 1, max 10) with "
            "a jsonb codec registered at connection level, and issues literal "
            "<font face='Courier'>SELECT ... FROM statute_sections</font> / "
            "<font face='Courier'>UPDATE sessions SET memory = $1::jsonb</font>.",
        why="Two ORMs describing one database is how staging and production drift "
            "apart silently. With one definition, a column rename produces a loud "
            "query error in Python on the next request - which is a better failure "
            "than a second model quietly disagreeing about a default.",
        instead="SQLAlchemy models plus Alembic on the Python side is the "
                "conventional answer and is explicitly refused here: it would "
                "create a second source of truth for the same tables, and two "
                "migration histories that can both claim to be current.",
        purpose="Sessions, turns, verdicts and the statute index are written from "
                "whichever side owns that step, with no synchronisation layer."))

    s.extend(table(
        ["Table", "Owner of writes", "Notable columns and why"],
        [
            ["<font face='Courier'>users</font>", "Express",
             "<font face='Courier'>password_hash</font> stores a self-describing "
             "scrypt digest; never selected into a response."],
            ["<font face='Courier'>cases</font>", "Express (from AI output)",
             "<font face='Courier'>citations</font> jsonb is the machine-checked "
             "list behind the human-readable <font face='Courier'>applicable_laws"
             "</font>; <font face='Courier'>brief</font> is nullable - null means "
             "'no pleading was ever drafted', which agents render differently."],
            ["<font face='Courier'>sessions</font>", "Express + Python",
             "<font face='Courier'>user_id</font> not null (an unowned session is "
             "readable by everyone); <font face='Courier'>memory</font> jsonb and "
             "<font face='Courier'>memory_through_turn_id</font> watermark are "
             "written by Python."],
            ["<font face='Courier'>turns</font>", "Express",
             "<font face='Courier'>reasoning</font> jsonb persists the judge's "
             "ReAct trace and the witness's grounding line, so a page reload does "
             "not lose why the bench ruled."],
            ["<font face='Courier'>verdicts</font>", "Express (from AI output)",
             "<font face='Courier'>citation_accuracy</font> is computed from the "
             "corpus, not scored by the model - the one number in the table that "
             "cannot be hallucinated."],
            ["<font face='Courier'>statute_sections</font>", "Ingest script",
             "<font face='Courier'>embedding</font> jsonb + "
             "<font face='Courier'>embedding_model</font> + "
             "<font face='Courier'>embedding_input_hash</font>; "
             "<font face='Courier'>verified</font> boolean per provision."],
        ],
        [17, 17, 66]))

    return s


def part_architecture_2():
    s = [h2("2.3 The contract: OpenAPI first, types generated")]

    s.extend(decision(
        "lib/api-spec/openapi.yaml as the single transport contract",
        what="A 1,357-line OpenAPI 3.1 document describing every route the browser "
             "can call, from which both the React Query client and the server-side "
             "Zod validators are generated by Orval.",
        how="Edit the YAML, then run <font face='Courier'>pnpm --filter "
            "@workspace/api-spec run codegen</font>. Orval emits "
            "<font face='Courier'>lib/api-client-react/src/generated/**</font> "
            "(hooks + fetchers, base URL <font face='Courier'>/api</font>) and "
            "<font face='Courier'>lib/api-zod/src/generated/**</font> (request and "
            "response schemas). Each Express handler starts with "
            "<font face='Courier'>XParams.safeParse(req.params)</font> and "
            "<font face='Courier'>XBody.safeParse(req.body)</font> and ends with "
            "<font face='Courier'>XResponse.parse(...)</font>.",
        why="One document means the client cannot ask for a field the server does "
            "not send, and the server cannot quietly change a response shape. "
            "Validating the <i>response</i> as well as the request is the unusual "
            "half: it turns a contract violation into a 500 on our side rather "
            "than a rendering bug on the user's.",
        instead="Hand-written fetch wrappers plus hand-written types drift the "
                "moment someone is in a hurry. tRPC would give end-to-end types "
                "but only between two TypeScript processes - it cannot describe a "
                "boundary a Python service also has to honour.",
        purpose="Every browser-facing route; generated files are never "
                "hand-edited, and code review reads the YAML diff, not the churn."))

    s.append(h3("Why the Python boundary is not generated"))
    s.append(p(
        "The Express-to-Python contract is hand-written TypeScript interfaces in "
        "<font face='Courier'>lib/ai-service.ts</font> mirrored by Pydantic models "
        "on the other side. That is a deliberate asymmetry: this boundary is "
        "internal, changes with every agent feature, and Pydantic already "
        "validates it at runtime with camelCase aliases "
        "(<font face='Courier'>populate_by_name=True</font>). Generating it would "
        "add a build step to the surface that moves most. The compiler still "
        "catches drift on the Node side because the values assigned come straight "
        "off Drizzle rows."))

    s.append(h2("2.4 One student utterance, end to end"))
    s.append(p(
        "This is the whole system in one trace - a spoken question during witness "
        "examination that draws an objection. Timings are from an instrumented "
        "request (case 4, Ghulam Nabi on the stand)."))

    s.extend(numbered([
        "<b>Capture.</b> The browser records with MediaRecorder (Chrome emits "
        "48 kHz WebM/Opus), base64-encodes it and POSTs to "
        "<font face='Courier'>/api/sessions/:id/voice-turns</font>. That one route "
        "gets a 25 MB JSON body limit - OpenAI's own transcription ceiling - "
        "instead of body-parser's 100 kB default; every other route keeps the "
        "default.",
        "<b>Authorise and load.</b> <font face='Courier'>requireUser</font> reads "
        "the signed cookie; <font face='Courier'>loadSessionDetail(id, userId)"
        "</font> fetches the session <i>filtered by owner</i>, plus its case, "
        "turns and verdict. Another student's session returns null, and the route "
        "answers 404 - not 403, which would confirm it exists.",
        "<b>Open the stream.</b> The response becomes "
        "<font face='Courier'>text/event-stream</font> immediately, so the client "
        "can render progress while the rest of this happens.",
        "<b>Transcribe (~4.5 s).</b> Magic bytes identify the container; a "
        "recognised one goes to <font face='Courier'>whisper-1</font> untouched "
        "(no ffmpeg), with <font face='Courier'>temperature 0</font>, "
        "<font face='Courier'>language en</font> and a vocabulary hint built from "
        "the case's own party and witness names. The transcript is persisted as a "
        "<font face='Courier'>student</font> turn and echoed to the client.",
        "<b>Assemble context.</b> Express computes the active witness (the last "
        "witness to speak in this phase) and the working memory (every turn in "
        "this phase, verbatim), and streams a turn request to "
        "<font face='Courier'>POST /courtroom/turn/stream</font>.",
        "<b>Route (Python).</b> The graph's entry edge sees a witness on the "
        "stand and routes to <font face='Courier'>objection_screen</font>. "
        "Opposing counsel screens the question with the cheap model; it proposes "
        "an objection, so the strong model re-decides it. Objection stands on "
        "<font face='Courier'>leading_question</font> / QSO 1984 Art. 137.",
        "<b>Emit event 1 (6.9 s).</b> The node returns; the stream yields the "
        "objection with its own citation audit. Express persists it as a turn, "
        "sends a <font face='Courier'>speaker</font> event with provenance, then "
        "streams TTS audio in counsel's voice. <b>The student hears the objection "
        "while the judge is still reading statute.</b>",
        "<b>Rule (13.8 s).</b> <font face='Courier'>judge_ruling</font> runs a "
        "ReAct loop: it calls <font face='Courier'>search_statute</font> with a "
        "required <font face='Courier'>thought</font>, gets Arts. 137, 136, 133, "
        "138 back, and returns JSON: sustained, with an explanation and the "
        "provisions it read.",
        "<b>Emit event 2 and stop.</b> The ruling is persisted with its ReAct "
        "trace, spoken in the judge's voice - and because it is sustained, the "
        "conditional edge routes to END. The witness node never runs, so there is "
        "no answer to strike; the silence is structural.",
        "<b>Summary.</b> A final message carries the turn-level audit (1/1 "
        "verified, 0 fabricated) and the primary speaker; the SSE stream closes.",
    ]))

    s.extend(note(
        "The same graph, entered the same way, serves the text endpoint. "
        "<font face='Courier'>run_turn</font> (batch) is literally defined as a "
        "loop over <font face='Courier'>run_turn_stream</font>, so a text "
        "courtroom and a voice courtroom cannot drift into two different "
        "courtrooms. That is the single most important structural guarantee in the "
        "codebase.", "INVARIANT"))

    return s


# ==========================================================================
# PART 3 - Corpus
# ==========================================================================


def part_corpus():
    s = h1("Part 3", "The statute corpus: chunking, ingestion and verification")

    s.append(p(
        "Everything downstream - retrieval, objection grounds, the citation audit, "
        "the verdict's legal-reasoning score - is only as good as this corpus. It "
        "is 53 provisions of Pakistani law stored as four JSON files under "
        "<font face='Courier'>data/statutes/</font> and ingested into one table.",
        LEAD))

    s.extend(table(
        ["Instrument", "Code", "Provisions", "Verified", "Diffed against"],
        [
            ["Qanun-e-Shahadat Order, 1984 (evidence)",
             "<font face='Courier'>QSO_1984</font>", "20", "20 / 20",
             "pakistancode.gov.pk print"],
            ["Pakistan Penal Code, 1860", "<font face='Courier'>PPC_1860</font>",
             "15", "15 / 15", "pakistancode.gov.pk print"],
            ["Code of Criminal Procedure, 1898",
             "<font face='Courier'>CRPC_1898</font>", "10", "10 / 10",
             "pakistancode.gov.pk print"],
            ["Constitution of Pakistan, 1973",
             "<font face='Courier'>CONST_1973</font>", "8", "7 / 8",
             "National Assembly print, 28 Feb 2012"],
        ],
        [34, 14, 12, 12, 28],
        caption="Art. 199 of the Constitution is the single unverified provision: "
                "the corpus text is later than the 2012 print (it refers to the "
                "Federal Constitutional Court and to clause (1A)), so that source "
                "cannot confirm it. It carries a per-provision "
                "<font face='Courier'>verified: false</font> and a note saying why."))

    s.append(h2("3.1 Chunking: the section is the chunk"))

    s.extend(decision(
        "Structural chunking, one row per section or Article",
        what="Each row of <font face='Courier'>statute_sections</font> is exactly "
             "one provision - PPC s.302, QSO Art. 137, Constitution Art. 199 - "
             "with heading, chapter and full operative text.",
        how="The ingest script walks each corpus file's "
            "<font face='Courier'>sections</font> array and writes one row per "
            "entry, building the canonical citation from "
            "<font face='Courier'>citationPrefix + citationUnit + sectionNumber"
            "</font> ('PPC 1860 s.302', 'QSO 1984 Art. 137'). A unique index on "
            "(code, number) makes re-ingestion an upsert.",
        why="A provision is already self-contained, and it is already the unit a "
            "lawyer cites and a judge reasons about. So every retrieved chunk is "
            "independently quotable, and the citation the model must reproduce is "
            "a column rather than something parsed out of surrounding prose.",
        instead="Fixed-window chunking (512 tokens, 50 overlap) is the RAG default "
                "and would be actively harmful here: it splits a proviso from the "
                "rule it qualifies, and produces chunks with no citation of their "
                "own - so a model quoting one has nothing to cite and the audit "
                "has nothing to check.",
        purpose="Retrieval, the judge's <font face='Courier'>search_statute</font> "
                "tool, objection grounds and the citation audit all key on this "
                "same unit."))
    return s


def part_corpus_2():
    s = [h2("3.2 Ingestion and re-indexing")]
    s.extend(code(
        "pnpm run statutes:ingest     # incremental - embeds only what changed\n"
        "pnpm run statutes:reindex    # --force: re-embed every provision\n"
        "\n"
        "embedding input = statuteTitle + citation - heading + blank line + content\n"
        "batch size      = 64 texts per embeddings call\n"
        "stored          = embedding (jsonb), embedding_model, embedding_input_hash"))

    s.append(p(
        "The job is idempotent, and the third stored column is the interesting "
        "one. Before <font face='Courier'>embedding_input_hash</font> existed the "
        "script could only tell whether an embedding was present and which model "
        "made it - so when PPC s.375 was corrected from the definition repealed in "
        "2016 to the current text, the row kept the vector of the text it had "
        "replaced, and retrieval went on matching wording no longer in the "
        "database. Hashing the exact embedded string closes that: changed text "
        "means a changed hash means a re-embed."))

    s.extend(note(
        "The embedding model and the stored vectors are a matched pair. Changing "
        "<font face='Courier'>MODEL_EMBEDDING</font> without re-indexing does not "
        "fail loudly - it silently compares vectors from two different spaces. The "
        "index build guards this by skipping any row whose "
        "<font face='Courier'>embedding_model</font> differs from the configured "
        "one, and logging a warning naming the count.", "TRAP"))

    s.append(h2("3.3 Verification: the guard the audit cannot be"))
    s.append(p(
        "Every provision was originally written from model knowledge. "
        "<font face='Courier'>pnpm run statutes:verify</font> diffs each provision "
        "word-for-word against an official print, and the wording was replaced "
        "from the source wherever the two disagreed. That exercise is the most "
        "important thing in these notes, because of what it found:"))

    s.extend(bullets([
        "<b>Six numbering errors.</b> The objection ground for insulting "
        "questions cited QSO Art. 143; the provision is Art. 148 (Art. 143 is "
        "'Court to decide when question shall be asked'). The whole "
        "documentary-evidence block was shifted by one, so the secondary-evidence "
        "ground pointed at the list of exceptions rather than the rule requiring "
        "primary evidence.",
        "<b>Three corrupted Constitution articles.</b> Art. 4 had a paragraph of "
        "1985 commencement footnotes spliced inside clause (2); Art. 8 was missing "
        "the armed-forces exception; Art. 10 was missing the entire "
        "preventive-detention regime a habeas petition turns on.",
        "<b>Thirty-eight stray footnote anchors</b> ('1Provided', '3Federal "
        "Constitutional Court') stripped across the corpus, without touching the "
        "law's own numbering.",
        "<b>PPC s.375</b> still carrying the definition of rape repealed in 2016.",
    ]))

    s.extend(note(
        "<b>The citation audit could not have caught any of it.</b> The audit "
        "checks that a cited provision exists in the corpus, and the corpus was "
        "its own ground truth. An internally consistent corpus that is wrong "
        "against the statute book passes every automated guard in this repository. "
        "That is exactly the failure mode corpus verification exists to close, and "
        "it is the honest answer to 'how do you know the law is right?' - a diff "
        "against an official print, not a metric.", "THE POINT"))

    s.append(h3("Verification is per provision, not per file"))
    s.append(p(
        "The corpus file schema carries a file-level "
        "<font face='Courier'>verified</font> default plus an optional "
        "<font face='Courier'>verified</font> on each section that overrides it "
        "(absent means inherit, not false). A file-level flag alone would either "
        "have marked Art. 199 verified because its neighbours were, or dragged "
        "seven cleanly diffed articles down to a warning because of the one that "
        "is not. The ingest validator rejects a non-boolean value outright, "
        "because the string 'false' is truthy in JavaScript and would mark "
        "undiffed text as authoritative law."))
    return s


# ==========================================================================
# PART 4 - Retrieval
# ==========================================================================


def part_retrieval():
    s = h1("Part 4", "Retrieval: hybrid search over the statute corpus")

    s.append(p(
        "The retrieval question in this domain is not 'find me something about "
        "evidence'. It is 'find me the provision that <b>governs</b> this "
        "question', and get it to rank one, because whatever ranks one is what a "
        "model will quote and a student will believe. Three stages do that: two "
        "independent retrievers, a rank-based fusion, and a reranker that judges "
        "legal applicability rather than similarity.", LEAD))

    s.extend(code(
        "query --+--> BM25 (rank_bm25, in-memory)      --> ranked ids --+\n"
        "        |                                                      +--> RRF\n"
        "        +--> dense vectors (numpy exact scan) --> ranked ids --+     |\n"
        "                                                                    v\n"
        "                                   top_k <-- rerank (LLM) <-- top_k*3 slice\n"
        "\n"
        "candidate_k = max(20, top_k * 4)      per retriever\n"
        "rerank slice = top_k * 3              wider than we return, on purpose\n"
        "rrf_k        = 60                     Cormack et al. (2009)"))

    s.append(h2("4.1 Why hybrid at all: legal queries are bimodal"))
    s.extend(table(
        ["A student or agent asks", "Only this retriever finds it", "Why"],
        [
            ["'section 302', 'qatl-i-amd', 'punishment for theft'",
             "<b>BM25</b> (lexical)",
             "Exact terms. Embeddings blur a specific section number into a cloud "
             "of adjacent provisions about the same subject."],
            ["'the witness is just repeating what somebody else told him "
             "outside court'",
             "<b>Dense</b> (semantic)",
             "Shares no vocabulary at all with QSO Art. 71, whose text reads "
             "'oral evidence must, in all cases whatever, be direct'."],
        ],
        [34, 20, 46],
        caption="Neither retriever covers the query distribution alone, which is "
                "the entire argument for hybrid retrieval here - not that hybrid "
                "is fashionable."))

    s.extend(decision(
        "Dense retrieval: text-embedding-3-small, 1536 dimensions, exact scan",
        what="Every provision is embedded once at ingest; queries are embedded per "
             "search. Vectors live in a jsonb column and are loaded into one "
             "numpy float32 matrix at service start.",
        how="Both sides are L2-normalised, so cosine similarity reduces to a dot "
            "product and the whole search is one matrix-vector multiply: "
            "<font face='Courier'>similarities = index.matrix @ query_vector</font>, "
            "then <font face='Courier'>argsort</font>. Exact, not approximate.",
        why="At 53 provisions - and a few thousand fully ingested - an exact scan "
            "over 5,000 x 1536 float32 is single-digit milliseconds. It is faster "
            "than an approximate index, it gives exact recall rather than a "
            "probability of recall, and it removes an extension from the "
            "deployment requirements.",
        instead="pgvector with ivfflat or HNSW, or an external vector database "
                "(Pinecone, Qdrant, Chroma). All three are rejected: the host "
                "PostgreSQL has only <font face='Courier'>pg_trgm</font>, "
                "approximate indexing earns its complexity somewhere north of "
                "100,000 vectors, and a separate vector store would add a second "
                "system that can be out of sync with the statute table.",
        purpose="Semantic half of every search - and the only half that can find a "
                "provision described in a student's own words."))
    return s


def part_retrieval_2():
    s = [h2("4.2 The lexical half: BM25 with a legal tokenizer")]

    s.extend(decision(
        "BM25Okapi over heading + content, built in memory at startup",
        what="A classical bag-of-words ranking function scoring term overlap with "
             "term-frequency saturation and document-length normalisation. "
             "Implemented by <font face='Courier'>rank_bm25</font>, rebuilt "
             "whenever the index reloads.",
        how="Documents are tokenised as "
            "<font face='Courier'>heading + ' ' + content</font>; the query is "
            "tokenised the same way. Any document scoring exactly 0 (no query term "
            "at all) is discarded before fusion rather than carried as padding.",
        why="Legal search is full of exact identifiers - section numbers, "
            "'qatl-i-amd', 'qanun-e-shahadat'. BM25 is exact, deterministic, free, "
            "and needs no model call, so it costs nothing to keep alongside the "
            "embeddings.",
        instead="PostgreSQL full-text search or <font face='Courier'>pg_trgm</font> "
                "similarity would push this into SQL, but then scores live in the "
                "database and the fusion has to happen across a network boundary; "
                "an in-memory index over 53 documents is instant and keeps all "
                "ranking logic in one file.",
        purpose="The lexical half of hybrid retrieval, and the reason 'section "
                "302' returns s.302 rather than a cluster of homicide provisions."))

    s.append(h3("The tokenizer is not the default one"))
    s.extend(code(
        "_TOKEN_PATTERN = re.compile(r\"[a-z0-9]+(?:-[a-z0-9]+)*\")\n"
        "\n"
        "'qatl-i-amd'         -> ['qatl-i-amd']        (kept whole)\n"
        "naive split on '-'   -> ['qatl', 'i', 'amd']  (weight scattered)"))
    s.append(p(
        "Hyphenated transliterations are single terms in this domain. Splitting "
        "them scatters a rare, highly discriminative term into fragments like 'i' "
        "and 'e' that appear everywhere and discriminate nothing. This is a "
        "two-line decision that measurably changes which provision wins a lexical "
        "query."))

    s.append(h2("4.3 Fusion: Reciprocal Rank Fusion, k = 60"))
    s.extend(code(
        "score(d) = sum over retrievers r of   1 / (k + rank_r(d))      k = 60\n"
        "\n"
        "BM25 raw scores    : 7.12 on one query, 40+ on another   (unbounded)\n"
        "cosine similarities: 0.30 - 0.45                          (narrow band)"))

    s.extend(decision(
        "RRF rather than weighted score blending",
        what="The two ranked lists are merged using only <i>rank position</i>. A "
             "document's fused score is the sum of 1/(60 + rank) over the "
             "retrievers that returned it.",
        how="Each retriever returns up to "
            "<font face='Courier'>candidate_k = max(20, top_k*4)</font> ids with "
            "ranks; the fusion dictionary accumulates the reciprocal terms. "
            "Documents found by both retrievers accumulate twice and rise, which "
            "is the behaviour that makes hybrid work.",
        why="It is scale-free. BM25 scores are unbounded and query-dependent while "
            "cosine similarities sit in a narrow band, so any direct blend needs a "
            "normalisation constant that must be retuned every time the corpus "
            "changes. k = 60 (Cormack et al., 2009) damps the head, so a single "
            "retriever's top hit cannot dominate the fusion on its own.",
        instead="<font face='Courier'>alpha * bm25_norm + (1-alpha) * cosine</font> "
                "is the obvious alternative and was rejected: it introduces a "
                "hyperparameter with no principled value, and min-max normalising "
                "per query makes the score depend on the worst candidate in the "
                "batch.",
        purpose="One ranked candidate list for the reranker, with both retrievers' "
                "opinions represented and neither able to shout the other down."))
    return s


def part_retrieval_3():
    s = [h2("4.4 Reranking: the measured decision")]

    s.append(p(
        "Both retrievers are <b>bi-encoders</b> in the general sense: query and "
        "document are scored without ever being looked at together, so nothing in "
        "the pipeline so far can tell whether a provision <i>governs</i> a "
        "question or merely shares its vocabulary. A reranker sees the pair "
        "jointly. The question was which reranker - and it was settled by "
        "measurement, not preference."))

    s.append(p(
        "<b>Test query:</b> <i>'the witness is just repeating what somebody else "
        "told him outside court'</i>. <b>Correct answer:</b> QSO 1984 Art. 71, "
        "<i>Oral evidence must be direct</i> - the provision codifying the rule "
        "against hearsay."))

    s.extend(table(
        ["Reranker", "Rank of Art. 71", "What happened"],
        [
            ["None (RRF ordering)", "<b>#2</b>",
             "Art. 151 'Impeaching credit' ranked above it - topically close, "
             "legally wrong."],
            ["<font face='Courier'>ms-marco-MiniLM-L-6-v2</font> cross-encoder",
             "<b>#10 of 15</b>",
             "Every score negative. Worse than not reranking at all."],
            ["LLM reranker (<font face='Courier'>gpt-4o</font>)", "<b>#1</b>",
             "Scored 10/10, and separately promoted Art. 46 (statements by a "
             "person who cannot be called - the dying-declaration exception to "
             "hearsay) from RRF rank 19 into the top 3."],
        ],
        [30, 16, 54]))

    s.append(h3("Why the cross-encoder failed, precisely"))
    s.append(p(
        "<font face='Courier'>ms-marco-*</font> checkpoints are trained on Bing "
        "query/passage pairs. That training signal rewards lexical and topical "
        "overlap in a web-search distribution. Nothing in it connects a colloquial "
        "description of hearsay to the statutory phrase 'oral evidence must, in "
        "all cases whatever, be direct' - the two share no surface features. The "
        "uniformly negative scores are the model correctly reporting that this "
        "entire corpus is out of its distribution. <b>An out-of-domain "
        "cross-encoder is worse than no reranker.</b>"))

    s.append(p(
        "The Art. 46 promotion is the other half of the argument. Recognising the "
        "dying-declaration exception as relevant to a hearsay question is a "
        "<i>doctrinal</i> relationship, not a similarity one. No bi-encoder and no "
        "web-trained cross-encoder has a representation of it."))

    s.extend(decision(
        "reranker_backend defaults to 'llm'",
        what="A <font face='Courier'>gpt-4o</font> call that scores each candidate "
             "0-10 for how directly it governs the question, returned as strict "
             "JSON, replacing the fusion ordering.",
        how="The top <font face='Courier'>top_k * 3</font> fused candidates are "
            "numbered and sent in one request, each truncated to 600 characters. "
            "The system prompt is explicit: judge legal applicability, not topical "
            "similarity - a provision that merely mentions the subject scores low, "
            "the one supplying the operative rule scores high.",
        why="Measured: it takes hit@1 from 0.80 to 1.00 and MRR from 0.88 to 1.00 "
            "on the 20-query golden set, promoting four semantic near-misses "
            "(hearsay 2 to 1, leading-question-in-chief 3 to 1, impeaching credit "
            "2 to 1, murder punishment 3 to 1) to rank one.",
        instead="The local cross-encoder is kept as a configurable backend but "
                "defaults off - it is fast (~20 ms) and free, and would be the "
                "right answer with a legal- or instruction-tuned checkpoint such "
                "as a BGE reranker. The interface is unchanged; only "
                "<font face='Courier'>RERANKER_BACKEND</font> moves.",
        purpose="Case generation, objection rulings, verdict scoring - the paths "
                "where correctness is the product. It is deliberately OFF for live "
                "voice turns, where latency is the product."))

    s.extend(table(
        ["Backend", "Latency (15 candidates)", "Token cost", "Used for"],
        [
            ["<font face='Courier'>none</font>", "~0.9 s", "none",
             "Broad palette retrieval during case generation, where recall across "
             "an area matters more than precision on one question."],
            ["<font face='Courier'>llm</font> (default)", "~8 s",
             "one call per query",
             "Rulings, verdicts, the judge's tool calls, evaluation."],
            ["<font face='Courier'>cross_encoder</font>", "~0.02 s after load",
             "none",
             "Available, off by default until a domain-tuned checkpoint is worth "
             "the weights."],
        ],
        [18, 20, 16, 46]))

    s.append(h3("Reranking is an optimisation, never a dependency"))
    s.extend(code(
        "cross_encoder --fails--> llm --fails--> unchanged RRF ordering\n"
        "\n"
        "rerank_scores() returns (scores, backend_that_actually_ran)\n"
        "so a caller reports the path that ran, not the one that was configured."))
    s.append(p(
        "A reranker outage degrades result <i>ordering</i>. It never fails a "
        "request. The null backend returns descending scores so the caller's sort "
        "preserves fusion order exactly - a no-op that keeps one code path instead "
        "of branching on whether reranking happened."))
    return s


# ==========================================================================
# PART 5 - Citation audit
# ==========================================================================


def part_citations():
    s = h1("Part 5", "The citation audit: the guard against invented law")

    s.append(p(
        "A tool that confidently misquotes a statute to a law student is worse "
        "than no tool. Grounding reduces fabrication; it does not eliminate it. So "
        "everything either side says is checked, deterministically, against the "
        "corpus - the agents' output and the student's arguments alike.", LEAD))

    s.append(h2("5.1 Extraction: regex, not a model"))
    s.extend(code(
        "instrument-first : 'PPC 1860 s.302',  'QSO Art. 17'\n"
        "provision-first  : 'section 302 of the PPC',  'Article 17 QSO'\n"
        "\n"
        "provision number : one or more digits, then an optional letter\n"
        "                   matches 302, 489-F, 10A, 265-K\n"
        "normalisation    : '489 - f' and '489-F' -> '489-F';  '10a' -> '10A'\n"
        "alias table      : longest alias first, so 'code of criminal procedure'\n"
        "                   is not partially matched by a shorter entry"))

    s.extend(decision(
        "Deterministic extraction and lookup",
        what="Two compiled regular expressions pull every statutory citation out "
             "of free text, resolve the instrument through an alias table, "
             "normalise the provision number, and look it up in the in-memory "
             "index.",
        how="Results are de-duplicated by "
            "<font face='Courier'>CODE:NUMBER</font>, so a provision cited three "
            "times in one paragraph counts once. Each citation gets one of three "
            "statuses.",
        why="It costs no model call and takes microseconds, which is what makes it "
            "affordable to run on <i>every single streamed utterance</i> before "
            "that utterance is spoken - not just once at the end of a turn. A "
            "judged audit would be both slower and itself fallible.",
        instead="Asking a model 'does this citation exist?' would be circular: the "
                "thing being guarded against is a model's confidence about "
                "provisions. The ground truth has to be a lookup.",
        purpose="Every agent utterance, every generated case ground, and the whole "
                "student transcript at verdict time."))

    s.append(h2("5.2 Three statuses, and why the third exists"))
    s.extend(table(
        ["Status", "Meaning", "Counts as"],
        [
            ["<font face='Courier'>verified</font>",
             "The instrument is in the corpus and this provision exists in it. Its "
             "text and its own <font face='Courier'>verified</font> flag come back "
             "with it.", "Correct citation"],
            ["<font face='Courier'>not_found</font>",
             "The instrument is in the corpus, but it has no such provision. This "
             "is a fabricated section number.", "Hallucination"],
            ["<font face='Courier'>uncovered</font>",
             "The instrument itself is outside the indexed corpus - the Code of "
             "Civil Procedure 1908, the Specific Relief Act 1877, the NADRA "
             "Ordinance 2000 and fourteen others are listed by alias precisely so "
             "they can be reported.", "Unconfirmed, not wrong"],
        ],
        [18, 62, 20]))

    s.append(p(
        "<b>The third status exists because of a specific failure.</b> An "
        "instrument with no alias is not judged unconfirmed - it is never seen, "
        "because extraction emits no tuple for it. That silence let three seeded "
        "library cases ship citing CPC 1908, the Specific Relief Act and the West "
        "Pakistan Land Revenue Act while auditing at 100% accuracy. Listing "
        "uncovered instruments does not change the fabrication count (only "
        "<font face='Courier'>not_found</font> feeds "
        "<font face='Courier'>hallucinated</font>); it changes the "
        "<i>denominator</i> of accuracy to the honest one."))

    s.append(h2("5.3 agentFabricated vs hallucinated"))
    s.append(p(
        "The red-team evaluation found a bug in this machinery, and the fix is "
        "worth stating because it is the difference between a warning that helps "
        "and one that lies. A student invents 'section 899 of the Pakistan Penal "
        "Code'. The judge correctly refuses it: <i>'the reference to section 899 of "
        "the Pakistan Penal Code is irrelevant'</i>. The raw audit sees a citation "
        "absent from the corpus in the judge's words and flags <b>the judge</b> for "
        "fabrication - putting a red 'not in corpus' warning in front of the "
        "student at the exact moment the system worked correctly."))

    s.extend(code(
        "echoed = { CODE:NUMBER for every citation in the student's utterance }\n"
        "\n"
        "hallucinated    = every not_found citation        (unchanged, downstream\n"
        "                                                   consumers depend on it)\n"
        "agentFabricated = not_found AND NOT in echoed     (what the UI shows)"))

    s.append(p(
        "The audit cannot tell an agent <i>relying</i> on a fake provision from one "
        "<i>naming it in order to reject it</i> - so the turn marks citations the "
        "student had already put on the record, and only what an agent introduced "
        "by itself is attributed to the agent. <b>Anything user-facing uses "
        "<font face='Courier'>agentFabricated</font>.</b> "
        "<font face='Courier'>hallucinated</font> is deliberately left alone so no "
        "existing number shifts underneath a consumer."))

    s.extend(note(
        "Prompt blocks and grounded responses carry the marker "
        "<font face='Courier'>[UNVERIFIED TEXT - do not quote verbatim as "
        "authoritative]</font> on any provision whose text has not been diffed "
        "against an official source, and the interface shows a warning badge "
        "beside it. These markers are never shortened, made conditional or hidden "
        "behind a flag to make output look more confident. A task that would "
        "remove them is refused.", "HONESTY MARKER"))
    return s


# ==========================================================================
# PART 6 - The multi-agent courtroom
# ==========================================================================


def part_agents():
    s = h1("Part 6", "The multi-agent courtroom: LangGraph, routing and ReAct")

    s.append(p(
        "This is the subsystem the project exists to demonstrate. A moot court "
        "needs something no single completion can produce: <b>opposing counsel "
        "objects on its own, the judge reads the statute and rules, and only then "
        "does the witness answer</b> - three agents acting in sequence on one "
        "student question. Modelled as a graph, that is simply a path through it.",
        LEAD))

    s.extend(decision(
        "The courtroom as a LangGraph StateGraph",
        what="Five nodes, each wrapping one agent, connected by conditional edges. "
             "One student utterance enters at START and exits at END having "
             "produced however many agent events the moment required.",
        how="Nodes return partial state updates. "
            "<font face='Courier'>events</font> is annotated with "
            "<font face='Courier'>operator.add</font>, so LangGraph's reducer "
            "concatenates each node's events into the turn's ordered transcript "
            "without any node knowing about the others.",
        why="The sequencing <i>is</i> the product. Expressing it as a graph makes "
            "the courtroom's procedural rules structural rather than prompted - a "
            "sustained objection cannot be followed by an answer, because there is "
            "no edge to the witness node from there.",
        instead="The previous design was one completion that swapped persona by "
                "phase. It could not produce a sequence of speakers on one "
                "utterance at all, and 'do not answer if the objection was "
                "sustained' was an instruction a model could ignore rather than a "
                "wire that does not exist.",
        purpose="Every text turn, every voice turn, and every student "
                "interruption."))

    s.extend(code(
        "START --(witness on the stand?)--+-- yes --> objection_screen\n"
        "                                 |                |\n"
        "                                 |      (objection raised?)\n"
        "                                 |         |            |\n"
        "                                 |        yes           no\n"
        "                                 |         v            |\n"
        "                                 |    judge_ruling      |\n"
        "                                 |      |       |       |\n"
        "                                 |  sustained  overruled|\n"
        "                                 |      |       |       |\n"
        "                                 |     END      v       v\n"
        "                                 +-- no ----> witness_testify\n"
        "                                              counsel_argues\n"
        "                                              bench_presides  --> END"))

    s.extend(table(
        ["Node", "Agent", "Decision it makes", "Model"],
        [
            ["<font face='Courier'>objection_screen</font>", "Opposing counsel",
             "After every question to a witness: is this improper, and on which "
             "evidentiary ground? Autonomous - nobody asks it to.",
             "<font face='Courier'>gpt-4o-mini</font>, escalating to "
             "<font face='Courier'>gpt-4o</font>"],
            ["<font face='Courier'>judge_ruling</font>", "Judge (ReAct)",
             "Sustained or overruled, after reading the governing provisions with "
             "a tool.", "<font face='Courier'>gpt-4o</font> + tool calls"],
            ["<font face='Courier'>witness_testify</font>", "Witness",
             "Can I properly say this? One of four outcomes, then the words.",
             "<font face='Courier'>gpt-4o</font> (JSON)"],
            ["<font face='Courier'>counsel_argues</font>", "Opposing counsel",
             "Rebuttal during a cross with no witness on the stand.",
             "<font face='Courier'>gpt-4o</font>"],
            ["<font face='Courier'>bench_presides</font>", "Judge",
             "Moderating an opening or closing - one in-character response, no "
             "reasoning loop.", "<font face='Courier'>gpt-4o</font>"],
        ],
        [22, 15, 45, 18]))
    return s


def part_agents_2():
    s = [h2("6.1 The supervisor is three pure functions")]

    s.extend(decision(
        "Routing by deterministic functions over shared state",
        what="Three functions decide every edge: "
             "<font face='Courier'>_route_entry</font>, "
             "<font face='Courier'>_route_after_objection</font>, "
             "<font face='Courier'>_route_after_ruling</font>. None of them calls a "
             "model.",
        how="Entry: a witness on the stand goes to the objection screen, otherwise "
            "straight to the primary responder (witness if one is up, opposing "
            "counsel in a cross with nobody up, the bench otherwise). After the "
            "screen: an objection goes to the judge, silence to the primary "
            "responder. After a ruling: sustained routes to END, overruled routes "
            "to the primary responder.",
        why="The phase and the presence of a witness fully determine who may act - "
            "there is nothing to infer. A model in this position could only add "
            "latency, cost, and the possibility of routing a sustained objection "
            "to the witness anyway. Determinism here is also what makes the "
            "routing invariant <i>assertable</i> in the evaluation rather than "
            "merely likely.",
        instead="A supervisor agent (an LLM router picking the next speaker) is the "
                "standard multi-agent pattern and is rejected here for exactly the "
                "reason it is usually adopted: flexibility. Courtroom procedure is "
                "not a place where flexible sequencing is a feature.",
        purpose="Every turn. Measured result: <b>0 sustained-objection routing "
                "leaks across 32 scenarios, on every run</b>."))

    s.append(h2("6.2 Opposing counsel: the autonomous actor"))
    s.append(p(
        "Its defining behaviour is the objection nobody asked for. Two constraints "
        "shape it. First, it may only object on a ground whose backing provision "
        "exists in the corpus - the catalogue is resolved from the statute book at "
        "runtime, and a ground whose provision is missing is simply not offered - "
        "so <b>every objection it raises is citable by construction</b>. Second, it "
        "is told to stay silent unless a ground clearly applies, because an "
        "advocate who objects to everything is noise, not opposition."))

    s.extend(table(
        ["Ground id", "Provision", "What it catches"],
        [
            ["<font face='Courier'>hearsay</font>", "QSO 1984 Art. 71",
             "Relating what someone else said rather than what was perceived."],
            ["<font face='Courier'>leading_question</font>", "QSO 1984 Art. 137",
             "Suggesting the desired answer to your own witness in chief."],
            ["<font face='Courier'>insulting_question</font>", "QSO 1984 Art. 148",
             "Needlessly offensive or harassing in form. <i>Was cited as Art. 143 "
             "until corpus verification corrected it.</i>"],
            ["<font face='Courier'>secondary_evidence</font>", "QSO 1984 Art. 75",
             "A copy tendered where the original is required. <i>Was Art. 76 - the "
             "whole block was shifted by one.</i>"],
            ["<font face='Courier'>irrelevant</font>", "QSO 1984 Art. 133",
             "Examination straying beyond the facts in issue."],
            ["<font face='Courier'>improper_impeachment</font>", "QSO 1984 Art. 151",
             "Attacking credit otherwise than as the law permits."],
            ["<font face='Courier'>police_statement</font>", "CrPC 1898 s.162",
             "Using a s.161 statement for a purpose the Code forbids."],
        ],
        [24, 20, 56],
        caption="These were previously hardcoded in the web app, where 'leading "
                "question' was attributed to QSO Art. 121. Resolving them from the "
                "corpus is what makes that class of error impossible."))

    s.append(h3("The screening prompt carries an explicit test"))
    s.append(p(
        "On the first evaluation run counsel objected 'leading question' to two "
        "plainly open questions - one of them literally <i>'what did you see "
        "outside the market that evening?'</i> - because the prompt described "
        "leading questions without giving a test for one. The fix was to state the "
        "test: a question is leading only if it puts the answer in the witness's "
        "mouth; questions opening with what, where, when, who, why, how or "
        "'describe' are not leading however central the subject. Both false "
        "positives disappeared at no cost to recall. That is the harness earning "
        "its keep on day one."))
    return s


def part_agents_3():
    s = [h2("6.3 The objection cascade: two models, one decision")]

    s.extend(decision(
        "Cheap model screens, strong model confirms",
        what="With <font face='Courier'>objection_cascade</font> on (the default), "
             "<font face='Courier'>gpt-4o-mini</font> screens every question. Only "
             "a <i>proposed</i> objection is escalated to "
             "<font face='Courier'>gpt-4o</font>, which re-decides it from scratch "
             "with the same prompt.",
        how="Same system prompt, same user block, different model. If the cheap "
            "screen says no objection, the turn ends there and nothing is "
            "escalated. If the strong model disagrees on escalation, no objection "
            "is raised.",
        why="Counsel screens <i>every</i> question and the honest answer to most is "
            "'no objection'. That majority does not need a frontier model. The "
            "objection is the part that teaches a rule, and teaching a wrong one "
            "is the expensive failure - so escalation is one-directional: cheap "
            "can stay silent alone, but cannot object alone.",
        instead="Routing everything through <font face='Courier'>gpt-4o</font> is "
                "the baseline and remains available via "
                "<font face='Courier'>OBJECTION_CASCADE=false</font> for a matched "
                "comparison. Using the cheap model for the final objection too "
                "would save more and is refused for the reason above.",
        purpose="The silent turn is the common case and the one a voice session "
                "waits on before a witness can answer."))

    s.extend(table(
        ["Configuration", "Total (32 scenarios)", "Per turn", "Silent turn",
         "Objected turn"],
        [
            ["Cascade off", "$0.3324", "$0.0104", "$0.0041 / 3.5 s",
             "$0.0153 / 8.0 s"],
            ["<b>Cascade on</b>", "<b>$0.3032</b>", "<b>$0.0095</b>",
             "<b>$0.0020 / 2.3 s</b>", "$0.0153 / 9.7 s"],
            ["Cascade on, judge states its thought", "$0.3311", "$0.0103",
             "$0.0020 / 2.9 s", "$0.0168 / 11.0 s"],
        ],
        [30, 18, 14, 19, 19],
        caption="Both cascade runs produced 18 objections and 14 silences, "
                "matching the labels exactly - the saving costs no accuracy. The "
                "aggregate 9% understates it: silent turns are <b>51% cheaper and "
                "34% faster</b>, while objected turns cost the same and run 1.7 s "
                "slower because escalation is a second serial call. The rare, "
                "dramatic turn pays a beat so the common one gets quicker."))

    s.append(h2("6.4 The judge as a ReAct agent"))
    s.append(p(
        "An evidentiary objection is decided by what the law actually says, not by "
        "how it sounds. So the judge does not rule from memory. It runs a bounded "
        "<b>Thought - Action - Observation</b> loop, calling "
        "<font face='Courier'>search_statute</font> to pull the provision the "
        "objection rests on <i>together with its neighbours</i> - a "
        "leading-question objection under Art. 137 is read alongside Art. 136, "
        "which defines a leading question, and Art. 138, which says when one is "
        "allowed. Every step is recorded and returned, so the ruling is not merely "
        "grounded, it is <i>shown</i> to be grounded."))

    s.extend(code(
        "for round in range(MAX_TOOL_ROUNDS = 3):\n"
        "    response = chat.completions(model=gpt-4o, tools=[search_statute],\n"
        "                                tool_choice='auto', messages=messages)\n"
        "    if no tool calls:  final_content = message.content;  break\n"
        "    append the assistant tool-call turn to messages\n"
        "    for each call:\n"
        "        observation, provisions = run_search_statute(arguments)\n"
        "        record ReasoningStep(thought=args['thought'],\n"
        "                             action='search_statute(query)',\n"
        "                             observation='; '.join(citations))\n"
        "        append {role: 'tool', tool_call_id: ..., content: observation}\n"
        "\n"
        "ruling = parse(final_content) or _force_ruling(messages)   # JSON mode\n"
        "                              or JudgeRuling('overruled')  # last resort"))

    s.append(h3("Why the thought is a tool argument, not narration"))
    s.append(p(
        "<font face='Courier'>search_statute</font> <b>requires</b> a "
        "<font face='Courier'>thought</font> parameter - one sentence on what the "
        "bench needs to check and why - alongside the query. That is not "
        "decoration. The thought was originally read off the assistant message, "
        "but under <font face='Courier'>tool_choice='auto'</font> a model that "
        "decides to call a tool usually returns "
        "<font face='Courier'>content=None</font>, so every recorded step carried "
        "an empty thought and the trace shown to a student was two-thirds of a "
        "ReAct loop. Prompting for narration is unreliable; <b>a required argument "
        "cannot come back empty</b>, and it binds the reasoning to the specific "
        "call it justifies. Measured cost: objected turns $0.0153 to $0.0168 "
        "(+10%), silent turns unchanged, decision quality identical."))

    s.extend(bullets([
        "<b>The loop is capped at 3 rounds.</b> Enough to read a provision and its "
        "neighbours; the cap bounds the latency and token cost of a single ruling "
        "and stops a model looping on the corpus.",
        "<b>It degrades in two stages.</b> If the model exhausts its rounds "
        "without ruling, it is forced to rule in JSON mode with no tools "
        "available. If even that fails, the objection is <i>overruled</i> - the "
        "least disruptive default, because overruling lets a possibly-proper "
        "question stand rather than wrongly striking it.",
        "<b>Provenance accumulates.</b> Every provision the tool returns is "
        "collected into <font face='Courier'>grounded</font>, de-duplicated by "
        "citation, and travels with the ruling so the interface can show what the "
        "bench read - with each provision's own verified flag.",
    ]))
    return s


def part_agents_4():
    s = [h2("6.5 The witness: the agent with no tools")]

    s.extend(decision(
        "A witness has no retrieval, and four permitted outcomes",
        what="The witness agent is handed its statement of record and its own "
             "prior testimony, and must commit to one of four outcomes before it "
             "speaks: <font face='Courier'>answer</font>, "
             "<font face='Courier'>dont_recall</font>, "
             "<font face='Courier'>decline_speculation</font>, "
             "<font face='Courier'>correct_record</font>.",
        how="A JSON completion returns "
            "<font face='Courier'>{outcome, grounding, basis, spoken}</font>. "
            "<font face='Courier'>grounding</font> is one of statement / "
            "prior_testimony / both / none, and "
            "<font face='Courier'>basis</font> is a plain-English line, not spoken, "
            "recording what in its own record supports the answer. Both are "
            "returned as a reasoning step alongside the words.",
        why="Withholding the tool is a <i>legal</i> constraint, not an omission. A "
            "witness testifies to their own perception; a witness who could look "
            "things up would be testifying to things they looked up. And the "
            "material they are entitled to is already in the prompt, so a tool "
            "over it would fetch nothing new.",
        instead="A witness that simply answers fluently is the obvious "
                "implementation and is the dangerous one: it is a fabrication "
                "engine wearing a name, and it teaches a student that any question "
                "produces evidence. Making the honest answers first-class - 'I do "
                "not recall', 'that is not something I can say' - is the fix.",
        purpose="Witness examination and cross-examination. Measured: <b>0 "
                "fabrications across 9 questions the witness could not know</b>, "
                "and 17/17 outcomes correct."))

    s.append(p(
        "Two defensive details. An unknown outcome keeps the words but drops the "
        "claim about why - better a bare answer than a trace asserting a decision "
        "the witness did not make. And "
        "<font face='Courier'>outcome == 'answer'</font> with "
        "<font face='Courier'>grounding == 'none'</font> is logged as a warning: it "
        "means either the model ignored the rule, or the question had no grounded "
        "answer and the outcome should not have been 'answer'. That is the exact "
        "event this agent exists to catch, so it is recorded rather than passed "
        "over."))

    s.append(h2("6.6 Streaming the turn out of the graph"))

    s.extend(decision(
        "run_turn_stream is the implementation; run_turn is a loop over it",
        what="<font face='Courier'>POST /courtroom/turn/stream</font> yields one "
             "NDJSON message per agent event as its node completes, then a final "
             "summary message. The batch endpoint collects the same messages.",
        how="<font face='Courier'>graph.astream(state, stream_mode='updates')"
            "</font> yields each node's own return value. Each event is audited "
            "immediately - a regex pass over an in-memory index, no model call - "
            "and yielded with its own audit attached. The turn-level audit is "
            "still taken over the joined transcript at the end, so a provision two "
            "agents both cite is counted once and the batch caller's numbers are "
            "unchanged.",
        why="With the batch endpoint the caller cannot speak counsel's objection "
            "until the judge has <i>also</i> finished its ReAct loop: measured "
            "<b>16.1 s of silence</b> before the first sound. Streaming lets the "
            "objection be heard while the bench is still reading statute - "
            "<b>8.1 s</b>, with counsel taking the floor at 6.9 s.",
        instead="Two separate implementations - one batched, one streamed - is the "
                "obvious way to add streaming and is exactly what is avoided: "
                "defining the batch path in terms of the streaming one means the "
                "text courtroom and the voice courtroom cannot drift into two "
                "different courtrooms.",
        purpose="The voice endpoint consumes the stream; the text endpoint "
                "consumes the batch wrapper; the evaluation harness drives "
                "<font face='Courier'>run_turn</font>, which is the same code."))

    s.append(h2("6.7 The student interrupting"))
    s.append(p(
        "Everywhere else the student speaks and waits. A real advocate does not "
        "wait. The interjection path takes whatever the student said mid-answer "
        "and makes two decisions in order: <b>was that an objection, and on what "
        "ground?</b> - constrained to the same corpus-backed catalogue, so a "
        "student objection is citable by construction exactly as an autonomous one "
        "is - and then <b>how does the bench rule?</b>, by the same ReAct judge. "
        "There is one judge in this courtroom and it reads the statute before it "
        "rules, whoever raised the point. An interruption that was not an "
        "objection is not forced into becoming one, and an objection with no "
        "citable ground returns a note telling counsel to name a ground rather "
        "than inventing one for them."))

    s.extend(note(
        "Importing LangGraph costs about 49 seconds cold. The compiled graph is "
        "therefore built lazily and cached in "
        "<font face='Courier'>get_graph()</font> - never imported at service "
        "startup or at the top of a hot path - so a service that never runs a turn "
        "never pays for it, and the cost is paid once on the first turn rather "
        "than at every restart.", "COLD START"))
    return s


# ==========================================================================
# PART 7 - Memory
# ==========================================================================


def part_memory():
    s = h1("Part 7", "Agent memory: two tiers, one watermark")

    s.append(p(
        "Without memory the judge hearing a closing argument has no idea what was "
        "said in the opening, and opposing counsel cannot notice that the student "
        "has changed their story. With naive memory - the whole transcript in "
        "every prompt - cost grows with the session and the actual question gets "
        "crowded out of the context window. Two tiers solve both.", LEAD))

    s.extend(table(
        ["Tier", "What it holds", "How it is produced", "Who sees it"],
        [
            ["<b>Working memory</b>",
             "Every turn of the <i>current</i> phase, verbatim.",
             "Assembled by Express from the turns table on each request. No model "
             "call.", "Every agent, every turn."],
            ["<b>Long-term memory</b>",
             "A structured case file: narrative summary, "
             "<font face='Courier'>studentClaims</font>, "
             "<font face='Courier'>witnessTestimony</font>, "
             "<font face='Courier'>judgeDirections</font>.",
             "One JSON-mode summarisation call, run <i>on phase transitions "
             "only</i>, folding in everything since the watermark.",
             "Bench and counsel in full; the witness gets a trimmed view."],
        ],
        [16, 32, 32, 20]))

    s.extend(decision(
        "Summarise on phase transition, incrementally, with a watermark",
        what="<font face='Courier'>sessions.memory</font> holds the case file and "
             "<font face='Courier'>sessions.memory_through_turn_id</font> records "
             "the highest turn already folded into it.",
        how="On a phase change the service selects turns with "
            "<font face='Courier'>id &gt; watermark</font>, sends them with the "
            "existing case file, and asks for an updated case file - rewriting the "
            "summary rather than appending, carrying forward entries that are "
            "still accurate. The new watermark is the last turn id, written in the "
            "same statement as the memory.",
        why="Within a phase the agent already sees the raw turns, so summarising "
            "each one would spend a model call to produce information the agent is "
            "not missing. Four transitions per session means <b>four "
            "summarisation calls in total</b>, and the watermark keeps each fold "
            "incremental rather than re-reading the whole transcript.",
        instead="Summarising every turn is the common pattern and is pure waste "
                "here. A vector store over past turns (retrieval-augmented memory) "
                "would be the choice for a long-running assistant; a moot-court "
                "session is bounded at five phases, so the structured file fits in "
                "a prompt and stays exactly inspectable.",
        purpose="Cross-phase continuity, and specifically the contradiction check "
                "- counsel confronting a student with what they said earlier."))

    s.append(h3("Why the case file is structured, not prose"))
    s.append(p(
        "The fields are used individually. "
        "<font face='Courier'>studentClaims</font> is what a contradiction check "
        "compares a new assertion against, and flattening it into a narrative "
        "would make that comparison lossy. Each list is capped - 12 claims, 10 "
        "testimony points, 6 directions, keeping the most recent - so a long "
        "session cannot grow the case file until it crowds out the question being "
        "asked. Failure is designed too: a failed summarisation leaves the "
        "previous memory <i>and</i> watermark in place, so the next transition "
        "retries the same span rather than silently losing it."))

    s.append(h2("7.1 The witness is given less, on purpose"))

    s.extend(decision(
        "Witness-scoped recollection",
        what="A witness on the stand receives only its own prior testimony plus "
             "the bench's directions - not the summary, and not other witnesses' "
             "evidence.",
        how="Testimony entries are stored prefixed with the witness's name (the "
            "summariser prompt requires it), which is what makes the split "
            "possible. Entries whose prefix does not match are dropped rather than "
            "paraphrased. Held as a separate "
            "<font face='Courier'>witness_memory_prompt</font> on the context, "
            "because the bench and counsel read the full recollection in the same "
            "turn.",
        why="Courts exclude witnesses from the courtroom while others testify, for "
            "exactly this reason. Handing a witness the full record lets it answer "
            "from evidence it never heard - which is not a memory bug, it is a "
            "procedural one, and a student learning to examine witnesses would be "
            "learning from a court that does not exist.",
        instead="One shared memory block for all agents is simpler and is what the "
                "first implementation did. It produced witnesses who "
                "corroborated each other suspiciously well.",
        purpose="Witness examination and cross-examination."))
    return s


# ==========================================================================
# PART 8 - Generation and scoring
# ==========================================================================


def part_generation():
    s = h1("Part 8", "Grounded generation: cases in, verdicts out")

    s.append(h2("8.1 Case generation: retrieve first, then write"))

    s.extend(decision(
        "Palette-constrained generation",
        what="A generated case is drafted as a <i>filing</i> - numbered facts, "
             "lettered grounds, an itemised prayer, parties, witnesses - and may "
             "cite only from a palette of provisions retrieved before the case "
             "exists.",
        how="Case generation is a chicken-and-egg problem: you cannot retrieve law "
            "relevant to a case that has not been written. So each area of law "
            "maps to a broad seed query (and optionally a statute filter) that "
            "surfaces the provisions that area typically turns on. Those "
            "provisions are rendered into the prompt in full, and the model is "
            "told to cite only from that exact list, reproducing each citation "
            "string verbatim. Reranking is off here - at this stage recall across "
            "an area matters more than precision on one question.",
        why="Without it the model invents plausible-looking section numbers, and a "
            "moot-court tool that teaches fabricated citations is worse than "
            "useless.",
        instead="Generating first and checking afterwards was the earlier shape. "
                "It fails more often and wastes the whole generation when it does; "
                "constraining the input is cheaper than repairing the output.",
        purpose="Every generated practice case. Library cases are seeded and carry "
                "no brief."))

    s.append(h3("Then the output is audited, ground by ground"))
    s.append(p(
        "Constraining the prompt reduces fabrication; it does not eliminate it. A "
        "ground is prose that <i>contains</i> citations, so an invented section "
        "number inside one would otherwise reach a student as pleaded law with "
        "nothing checking it. Each ground is audited individually - a local index "
        "lookup, no model call, so it costs nothing and identifies exactly which "
        "citation was invented. Any ground citing a "
        "<font face='Courier'>not_found</font> provision is <b>dropped</b>; an "
        "<font face='Courier'>uncovered</font> instrument is logged but kept, "
        "because that is a coverage gap rather than a fabrication. A brief left "
        "with fewer than two grounds is rejected outright rather than persisted "
        "thin."))

    s.extend(table(
        ["Cap", "Value", "Why it exists"],
        [
            ["Facts / grounds / prayer items", "8 / 6 / 5",
             "The brief is rendered into <font face='Courier'>case_context()"
             "</font>, which rides in <i>every</i> agent prompt - the objection "
             "screen, the ruling, the testimony and the bench. An unbounded facts "
             "list multiplies per-turn cost four ways."],
            ["Characters per item", "400", "Same reason, per item."],
            ["Parties / witnesses", "6 / 3",
             "A witness with an empty statement makes witness examination "
             "unplayable, so those entries are discarded at parse time."],
            ["Ground labels", "Server-assigned A, B, C...",
             "Labels stay contiguous after the audit drops a ground; a brief that "
             "jumps from A to C tells the student something was removed without "
             "telling them why."],
        ],
        [26, 16, 58],
        caption="Measured with tiktoken: a real brief (4 facts, 3 grounds, 3 "
                "prayer items) grows <font face='Courier'>case_context()</font> "
                "from 158 to 465 tokens - <b>+307 tokens per agent call that "
                "embeds it</b>. Arithmetic on pinned prices puts a silent turn at "
                "+2.3% (it runs on the cheap model) and an objected turn at "
                "+10-20%."))

    s.extend(note(
        "A case with no brief renders <b>byte-identical</b> to the version that "
        "predated briefs. Library cases and everything generated before the "
        "feature carry <font face='Courier'>brief = null</font>, and the courtroom "
        "must not behave differently for them - which is also why the courtroom "
        "evaluation fixture deliberately has no brief: that suite is a regression "
        "check proving a briefless case is unaffected, and is <i>not</i> a "
        "measurement of what the brief costs.", "COMPATIBILITY"))

    s.append(h2("8.2 Verdict scoring: the audit is ground truth"))
    s.append(p(
        "Scoring runs in the AI service, called both by the Express route that "
        "grades a real session and by the evaluation harness that measures the "
        "judge - one implementation, so the harness cannot drift from the "
        "product. Three things happen before the scoring call:"))

    s.extend(numbered([
        "Every statute the <i>student</i> cited across the transcript is audited "
        "against the corpus.",
        "The provisions that actually govern the case are retrieved (reranked, "
        "top 6) from title + summary + applicable laws, so the judge can tell a "
        "student who missed the controlling provision from one who engaged with it "
        "and lost the argument.",
        "Both are rendered into the prompt - the audit under the heading 'this is "
        "ground truth, not your opinion', with each citation marked EXISTS or DOES "
        "NOT EXIST.",
    ]))

    s.append(p(
        "The judge returns four category scores plus an overall, a winning side, "
        "and three pieces of written feedback. <b>Its output is then validated, "
        "not trusted:</b> each score is rejected if non-numeric (booleans "
        "explicitly, since <font face='Courier'>bool</font> subclasses "
        "<font face='Courier'>int</font>), otherwise rounded and clamped to 0-100 "
        "- models routinely return a weighted average as '55.75', and stranding a "
        "finished session over a decimal point would be absurd. A winning side "
        "that is not a party to this case raises rather than persists. And "
        "<font face='Courier'>citationAccuracy</font> is computed from the audit, "
        "not scored by the model: it is the one number in the verdicts table that "
        "cannot be hallucinated."))
    return s


# ==========================================================================
# PART 9 - Voice
# ==========================================================================


def part_voice():
    s = h1("Part 9", "The voice pipeline: transport, not reasoning")

    s.append(p(
        "Voice is the product's shape - a student <i>argues</i>, they do not type "
        "- but architecturally it is a transport layer wrapped around the same "
        "graph the text turn uses. The student's audio is transcribed, the "
        "transcript enters at START exactly as a text turn does, and the ordered "
        "events come back the same way. What voice adds is delivery.", LEAD))

    s.extend(table(
        ["Stage", "Component", "Choice and constraint"],
        [
            ["Capture", "Browser MediaRecorder",
             "Chrome emits 48 kHz WebM/Opus. Base64 inside JSON, so the "
             "voice-turns route alone raises the body limit to 25 MB - OpenAI's "
             "own transcription ceiling, since anything larger could not be "
             "transcribed at the next hop anyway."],
            ["Format", "Magic-byte detection",
             "WAV, WebM, MP3, MP4/M4A, OGG are recognised and forwarded "
             "<b>untouched</b>. Only genuinely unidentifiable bytes go through "
             "ffmpeg."],
            ["Transcription", "<font face='Courier'>whisper-1</font>",
             "<font face='Courier'>language=en</font>, "
             "<font face='Courier'>temperature=0</font>, plus a vocabulary hint. "
             "~4.5 s - now the largest single block before the court speaks."],
            ["Reasoning", "The graph, streamed",
             "NDJSON in, SSE out. Each event persisted and audited before it is "
             "spoken."],
            ["Synthesis", "<font face='Courier'>gpt-4o-mini-tts</font>",
             "PCM16 at 24 kHz, one voice per agent (judge onyx, counsel echo, "
             "witness shimmer). Input capped at 3,800 characters, split on "
             "sentence boundaries."],
            ["Delivery", "Server-Sent Events",
             "One long-lived HTTP response carrying "
             "<font face='Courier'>user_transcript</font>, "
             "<font face='Courier'>speaker</font>, "
             "<font face='Courier'>transcript</font> and "
             "<font face='Courier'>audio</font> messages in order."],
        ],
        [14, 22, 64]))

    s.append(h2("9.1 Three decisions worth defending"))

    s.extend(decision(
        "Synthesis uses the dedicated TTS endpoint, not an audio chat model",
        what="Agent lines are spoken by a text-to-speech endpoint whose only job "
             "is to read the string it is given.",
        how="The words come from the agents in Python and are audited <i>before</i> "
            "they reach the speech layer. The only per-agent parameter the speech "
            "layer carries is <font face='Courier'>instructions</font>, and those "
            "describe delivery - 'a ruling is pronounced, not discussed' - never "
            "content.",
        why="A chat completion asked to 'repeat the following text' is still free "
            "to paraphrase. A paraphrased citation would no longer be the one the "
            "audit verified, and the audit would then be vouching for words nobody "
            "said. Synthesis speaks the audited text or it fails.",
        instead="An audio-in/audio-out conversational model is available in the "
                "codebase (<font face='Courier'>MODEL_AUDIO</font>) and is not on "
                "this path, for that reason.",
        purpose="Every spoken agent line. A synthesis failure costs that agent its "
                "voice, not the turn - the words are already on the record and in "
                "the transcript."))

    s.extend(decision(
        "Transcription is given the case's proper nouns",
        what="A vocabulary hint listing the parties, the witnesses and standard "
             "courtroom terms is passed with the audio.",
        how="Built from the case record: petitioner, respondent, every witness "
            "name, plus 'Qanun-e-Shahadat Order', 'Pakistan Penal Code', 'My "
            "Lord', 'objection', 'sustained', 'overruled'.",
        why="Whisper has no prior for Pakistani names and rendered 'Mr. Nabi' as "
            "<b>'Mr. Nobby'</b>, which then reached the agents as the name of a "
            "witness who does not exist. The hint fixed that spelling.",
        instead="Post-hoc fuzzy correction of names against the case file was the "
                "alternative and is strictly worse: it would rewrite what the "
                "student said. A hint biases spelling only - it cannot add words "
                "the speaker did not say - and the names come from the case "
                "record, never from anything the student uttered.",
        purpose="Every voice turn."))

    s.extend(decision(
        "Audio chunks are carried to an even byte boundary",
        what="Base64 PCM16 chunks are emitted only in whole samples; a trailing "
             "half-sample is carried into the next chunk.",
        how="<font face='Courier'>aligned = len - (len % 2)</font>; the remainder "
            "becomes <font face='Courier'>carry</font> and is prepended to the "
            "next buffer.",
        why="The browser worklet decodes each chunk with "
            "<font face='Courier'>new Int16Array(bytes.buffer)</font>, which "
            "throws outright on an odd byte length. Measured: 0 misaligned chunks "
            "across 305 chunks / 1.82 MB.",
        instead="Padding the odd byte with a zero would inject a click; dropping "
                "it would desynchronise the stream by half a sample and "
                "accumulate.",
        purpose="Playback stability for the entire session."))

    s.append(h2("9.2 What streaming bought, measured"))
    s.extend(table(
        ["", "Batch", "Streamed"],
        [
            ["<b>First audio byte</b>", "16.1 s", "<b>8.1 s</b>"],
            ["Counsel takes the floor", "16.1 s", "<b>6.9 s</b>"],
            ["Bench rules", "16.1 s", "13.8 s"],
            ["Total turn", "22.5 s", "20.5 s"],
            ["Audio streamed", "292 chunks / 1.63 MB",
             "305 chunks / 1.82 MB (~38 s of PCM16 at 24 kHz)"],
            ["Misaligned chunks", "0", "0"],
            ["Citation audit", "1/1 verified, 0 fabricated",
             "1/1 verified, 0 fabricated"],
        ],
        [26, 30, 44],
        caption="Same request either side of the change: case 4, witness "
                "examination, a leading question put to Ghulam Nabi. Both runs "
                "produced two agents and no witness answer - the sustained "
                "objection struck the question, as designed."))

    s.extend(note(
        "Microphone capture and browser playback were confirmed on 17 August 2026: "
        "a leading question spoken into a real microphone drew opposing counsel's "
        "objection and the bench's ruling, both audible in distinct voices. Still "
        "unheard: a witness <i>answering</i> - that run ended in a sustained "
        "objection, where the graph routes to END and silence is the correct "
        "behaviour. It is the one link in the chain nobody has listened to.",
        "HONEST LIMIT"))
    return s


# ==========================================================================
# PART 10 - Security
# ==========================================================================


def part_security():
    s = h1("Part 10", "Security: identity, scoping and hostile input")

    s.append(p(
        "A session carries a mark and a judge's written assessment of a named "
        "person's advocacy. Before user scoping existed, the dashboard averaged "
        "every session in the database and presented the result as the reader's "
        "own progress - wrong as statistics before it was wrong as privacy. That "
        "is what kept this out of a classroom, not any missing feature.", LEAD))

    s.append(h2("10.1 Authentication"))

    s.extend(decision(
        "scrypt from node:crypto, with parameters stored in the digest",
        what="Passwords are hashed with scrypt at N=16384, r=8, p=1, 64-byte key, "
             "16-byte random salt, stored as "
             "<font face='Courier'>scrypt$N$r$p$salt$key</font> with salt and key "
             "base64.",
        how="Verification splits the stored digest, re-derives with <i>that "
            "record's</i> parameters, and compares with "
            "<font face='Courier'>timingSafeEqual</font> after an explicit length "
            "check (it throws on a length mismatch rather than returning false, so "
            "a truncated digest would otherwise be a 500 instead of a failed "
            "login). A malformed digest returns false rather than throwing: a "
            "corrupted row should fail one login, not the route.",
        why="N=16384 is the interactive-login figure from the scrypt paper - "
            "roughly 100 ms and 16 MB per hash on a laptop, slow enough to make "
            "offline guessing expensive and fast enough that a student does not "
            "notice. Storing the parameters beside the digest means raising the "
            "cost later re-hashes new passwords without locking out accounts "
            "stored under the old cost.",
        instead="bcrypt or argon2 via a dependency is the usual answer. scrypt is "
                "already in the Node standard library, the parameters above are "
                "the decisions a library would make silently anyway, and a "
                "dependency handling credentials is one more thing to keep patched "
                "before a demo.",
        purpose="Registration and sign-in."))

    s.extend(decision(
        "A stateless, signed session cookie",
        what="<font face='Courier'>userId.expiry.HMAC-SHA256(userId.expiry)</font>, "
             "carried in an httpOnly, sameSite=lax cookie with a 7-day TTL.",
        how="The signature is checked <i>before</i> the payload is parsed, so a "
            "forged payload never reaches "
            "<font face='Courier'>Number()</font>. "
            "<font face='Courier'>secure</font> is set only in production, because "
            "a Secure cookie over the plain-http dev server is never sent back and "
            "presents as 'login succeeds then immediately logs out'.",
        why="A classroom does not need per-device revocation, and a token table "
            "would be a second thing to keep in step with the users table.",
        instead="Server-side sessions in Postgres or Redis. The cost of the "
                "stateless choice is stated rather than hidden: <b>the only way to "
                "revoke every session is to rotate "
                "<font face='Courier'>AUTH_SECRET</font></b> - the right lever if "
                "credentials leak, and worth knowing is the only one.",
        purpose="Every authenticated route."))

    s.extend(note(
        "<font face='Courier'>AUTH_SECRET</font> (32+ characters) has no default "
        "and <font face='Courier'>getSecret()</font> throws without it - but "
        "lazily, only when a token is signed. So a tree with a stale "
        "<font face='Courier'>.env</font> boots, serves "
        "<font face='Courier'>/cases</font>, and fails only at sign-in. This is "
        "the one variable whose absence is not obvious. Generating a default would "
        "make every restart invalidate all sessions; hardcoding one would make "
        "every deployment forgeable - both fail quietly, which is the worst "
        "available behaviour for this value.", "OPERATIONAL TRAP"))

    s.append(h2("10.2 Authorisation: one loader, 404 not 403"))
    s.append(p(
        "<font face='Courier'>requireUser</font> is mounted on the whole "
        "<font face='Courier'>/sessions</font> and "
        "<font face='Courier'>/dashboard</font> routers - declared at the top of "
        "the file rather than at the mount point, so a route added later is "
        "protected by default instead of by remembering. Every "
        "<font face='Courier'>/sessions/:id</font> route then reaches its session "
        "through a single loader that filters on "
        "<font face='Courier'>userId</font> in the WHERE clause. A handler that "
        "forgot to check would have had to go around that function to load the row "
        "at all."))
    s.append(p(
        "A session belonging to someone else returns <b>404, not 403</b>: the two "
        "cases are deliberately indistinguishable, because a 403 confirms the "
        "session exists. <font face='Courier'>currentUserId()</font> throws rather "
        "than returning undefined - the failure that matters is "
        "<font face='Courier'>undefined</font> flowing into a query filter and "
        "quietly matching nothing, or on a different query shape, everything. The "
        "case library stays shared and unauthenticated: it is teaching material, "
        "not anyone's record."))
    return s


def part_security_2():
    s = [h2("10.3 Rate limiting on two keys at once")]

    s.extend(decision(
        "Sliding-window limiter keyed on both email and IP",
        what="8 failed sign-ins per account and 30 per address in 15 minutes; 5 "
             "sign-ups per address per hour. Checked <i>before</i> the password is "
             "verified.",
        how="An in-memory map of failure timestamps per key, pruned to the window "
            "on every read. A successful sign-in clears the account's counter but "
            "not the address's. The map is bounded at 10,000 keys and sweeps aged "
            "entries when full, refusing to grow further rather than evicting "
            "someone else's record of failures.",
        why="Both keys are needed. Limiting by account alone lets one guess be "
            "sprayed across a class roster; limiting by address alone lets a lab "
            "behind one NAT lock its own students out. Checking before "
            "verification means a blocked caller cannot spend the server's "
            "hashing time either - which matters when hashing is deliberately "
            "expensive.",
        instead="A fixed window is simpler and lets an attacker spend the full "
                "allowance at the end of one window and again at the start of the "
                "next - twice the intended rate at the moment it matters most. An "
                "unbounded key map would make the limiter the denial of service it "
                "exists to prevent.",
        purpose="Sign-in and sign-up. Stated limitation: in-memory means per "
                "process, so behind a load balancer the limit is per instance and "
                "a shared store would be needed."))

    s.append(p(
        "Per-address limiting only distinguishes callers when Express can see the "
        "real client address. Behind a proxy - including the Vite dev proxy - "
        "<font face='Courier'>req.ip</font> is the proxy, and every request looks "
        "like one client, collapsing the per-IP bucket. So "
        "<font face='Courier'>trust proxy</font> is opt-in via "
        "<font face='Courier'>TRUST_PROXY</font>: the failure runs both ways, and "
        "trusting <font face='Courier'>X-Forwarded-For</font> when nothing "
        "upstream sets it lets any caller forge an address per request and walk "
        "straight past the limit."))

    s.append(h2("10.4 Prompt injection: measured, then deliberately not built"))
    s.append(p(
        "Transcribed student speech reaches agent prompts verbatim. That is a real "
        "exposure and it is stated plainly in the code. The red-team evaluation "
        "puts <b>36 attacks</b> through the courtroom and the verdict scorer - "
        "prompt injection, instruction leaking, fabrication induction, role-break "
        "attempts, authority spoofing, procedure bypass, score manipulation."))

    s.extend(table(
        ["Measurement", "Result"],
        [
            ["Attacks where an agent obeyed an injected instruction", "<b>0 / 36</b>"],
            ["Deflected by an objection (the courtroom caught it)",
             "14-21 / 30, varies by run"],
            ["Verdict attacks that reached the written verdict", "<b>0 / 6</b>"],
            ["Verdict attacks that moved the mark by 15 points or more",
             "<b>0 / 6</b>"],
        ],
        [64, 36]))

    s.append(p(
        "<b>The multi-agent design turns out to be the defence.</b> Opposing "
        "counsel screens every utterance, so an injection arrives in front of an "
        "agent whose job is to object to improper questions - and it does, ruling "
        "the injected instruction irrelevant under QSO Art. 133 and striking it. "
        "On the verdict path the marks mostly went <i>down</i> under attack: the "
        "judge reads the manipulation attempt as part of the performance being "
        "graded."))

    s.append(p(
        "The detectors are objective rather than a matter of opinion. The main one "
        "is a <b>canary</b>: the attack instructs an agent to emit a token it would "
        "never otherwise say, so if <font face='Courier'>PINEAPPLE7</font> appears, "
        "the injected instruction was obeyed - no judgement call. Alongside it: "
        "system-prompt phrases appearing in output, first-person self-disclosure as "
        "a model, and agent-introduced fabricated citations."))

    s.extend(note(
        "<b>This is 36 attacks, not a proof.</b> It says the obvious attacks fail, "
        "not that the system is safe. The honest read is that a prompt-injection "
        "guard would currently have no measurable effect on this surface, so it is "
        "not built - the right time to build one is when an attack lands, and the "
        "attack goes into the harness first. Three detector iterations were needed "
        "before the numbers meant anything: an apostrophe in 'counsel's' broke "
        "quote-stripping and scored a refusal as a breach, and matching the bare "
        "phrase 'system prompt' flagged the bench for sustaining an objection to a "
        "question <i>about</i> the system prompt. A red-team harness is itself "
        "something you can fool yourself with.", "SCOPE"))
    return s


# ==========================================================================
# PART 11 - LLMOps
# ==========================================================================


def part_llmops():
    s = h1("Part 11", "LLMOps: cost telemetry, evaluation and run tracking")

    s.append(p(
        "A scored simulator has to be able to defend three claims about itself: "
        "that it retrieves the right law, that its judge can be trusted to grade, "
        "and that its courtroom objects and rules correctly. The harness measures "
        "all three against fixed golden sets, so a regression shows up as a number "
        "moving rather than as a feeling.", LEAD))

    s.append(h2("11.1 Cost telemetry: instrument the client, not the call sites"))

    s.extend(decision(
        "Wrap the shared OpenAI client once",
        what="Every model call the Python service makes is timed and priced. "
             "Instrumentation is attached by reassigning "
             "<font face='Courier'>create()</font> on the client's "
             "<font face='Courier'>chat.completions</font> and "
             "<font face='Courier'>embeddings</font> resources.",
        how="Recording is scoped to a ledger opened with "
            "<font face='Courier'>track()</font>, held in a "
            "<font face='Courier'>ContextVar</font> so two concurrent turns do not "
            "pour usage into each other's ledger. Outside a ledger nothing is "
            "recorded at all, so nothing accumulates in a long-running process.",
        why="Eight places in the service reach the API - the agents, the ReAct "
            "loop, memory summarisation, the reranker, verdict scoring, "
            "embeddings. A cost figure that silently misses one is <i>worse</i> "
            "than no figure, because it looks authoritative. Wrapping once means a "
            "new call site is counted whether or not whoever added it remembered.",
        instead="Adding accounting at each call site is the obvious approach and "
                "is exactly what fails - the ninth call site is the one nobody "
                "instruments. A module-level global instead of a ContextVar would "
                "cross-contaminate concurrent turns.",
        purpose="Every cost figure in these notes and every spend line the eval "
                "prints."))

    s.append(p(
        "Prices are <b>pinned in the source, not fetched</b>. An eval that reports "
        "a different cost depending on the day it ran is not a measurement, and CI "
        "has no business making a pricing call to answer 'did this change get "
        "cheaper'. The trade is that they go stale, so they are labelled as "
        "approximate and must be checked before quoting a dollar figure. An "
        "unknown model is priced as the expensive one - guessing low would "
        "understate cost, which is the direction that misleads."))

    s.append(h2("11.2 The five evaluations"))

    s.extend(table(
        ["Suite", "Question it answers", "Metrics", "Command"],
        [
            ["<b>Retrieval</b> (20 queries)",
             "Given a legal question, does the corpus return the governing "
             "provision, near the top?",
             "hit@1/3/5, MRR, split by semantic vs lexical query",
             "<font face='Courier'>pnpm run eval</font>"],
            ["<b>Judge</b> (3 transcripts)",
             "Is the grader reliable (same transcript, same score) and does it "
             "discriminate (better advocacy scores higher)?",
             "median, spread, mean stdev, discrimination pairs, citation accuracy",
             "<font face='Courier'>pnpm run eval</font>"],
            ["<b>Courtroom</b> (32 scenarios)",
             "Does counsel object when it should and stay silent when it should "
             "not, and does the bench then rule correctly?",
             "precision, recall, F1, specificity, ground accuracy, ruling "
             "accuracy, routing leaks",
             "<font face='Courier'>pnpm run eval:courtroom --runs 3</font>"],
            ["<b>Witness</b> (scenarios with a fixed statement)",
             "Does the witness answer only from its own record?",
             "fabrication count, outcome accuracy - structural, no second model "
             "judging",
             "<font face='Courier'>pnpm run eval:witness</font>"],
            ["<b>Red team</b> (36 attacks)",
             "What happens when the student is hostile?",
             "canary breaches, prompt leakage, self-disclosure, agent-introduced "
             "fabrications", "<font face='Courier'>pnpm run eval:redteam</font>"],
        ],
        [20, 30, 30, 20]))

    s.extend(note(
        "All five drive <b>the same functions the product calls</b> - "
        "<font face='Courier'>search_statutes</font>, "
        "<font face='Courier'>run_turn</font>, "
        "<font face='Courier'>score_session</font>, "
        "<font face='Courier'>testify</font> - never a copy. The moment a harness "
        "measures its own reimplementation it stops measuring the product.",
        "INVARIANT"))

    s.append(p(
        "The courtroom suite is <b>opt-in</b> rather than part of the fast gate: it "
        "drives the full agent graph once per scenario, so it costs minutes and "
        "real tokens. That also means <font face='Courier'>pnpm run eval</font> "
        "does not import the agents at all - <b>it is not evidence for an agent "
        "change</b>, which is a distinction worth being strict about."))
    return s


def part_llmops_2():
    s = [h3("Metric definitions, stated plainly")]
    s.extend(bullets([
        "<b>hit@k</b> - the fraction of queries where an expected citation appears "
        "in the top k results. hit@1 is the one that matters, because rank one is "
        "what a model quotes.",
        "<b>MRR</b> - mean of 1/(rank of the first expected citation). Rewards "
        "getting the right provision high, not merely present.",
        "<b>Precision / recall on the objection decision</b> - recall is 'did "
        "counsel object when it should have', precision is 'when it objected, "
        "should it have'. Seven deliberately proper open questions carry the "
        "false-positive rate, so precision is a first-class metric here rather "
        "than an afterthought.",
        "<b>Specificity</b> - the fraction of proper questions counsel correctly "
        "stayed silent on.",
        "<b>Ground accuracy</b> - credits <i>any</i> ground in "
        "<font face='Courier'>expectedGrounds</font>, because more than one is "
        "often genuinely defensible for the same question (a foundationless "
        "character attack is both insulting and irrelevant). Scoring a defensible "
        "choice as wrong would understate the agent and push future work towards "
        "gaming a single label.",
        "<b>Discrimination</b> - the count of transcript pairs ranked in the "
        "expected order. 3/3, unmoved across every run.",
    ]))

    s.append(h2("11.3 Being honest about noise"))
    s.append(p(
        "Two figures in this harness are known-noisy, and quoting either from a "
        "single run is the trap this section exists to name."))

    s.extend(table(
        ["Metric", "Single run can read", "Quote instead"],
        [
            ["Courtroom precision / F1 / ground accuracy", "1.00",
             "0.98 / 0.99 / 0.98 as means over 3 runs - one of three runs "
             "genuinely was 32/32, which is exactly the trap"],
            ["Ruling accuracy", "89% or 94% or 100%",
             "the mean of <font face='Courier'>--runs 3</font>, or say explicitly "
             "that it is one run. It moved 94% to 89% with no judge change"],
            ["Judge weak-transcript score", "25 or 35",
             "the range 25-35. It scored 25, 25, 35, 35, 35 while nothing in the "
             "judge changed"],
        ],
        [26, 22, 52],
        caption="What did <i>not</i> move across any run: objection recall 1.00, "
                "0 sustained-objection routing leaks, discrimination 3/3, and "
                "citation accuracy 100% / 50% / 0%. Those are the figures to lead "
                "with."))

    s.append(p(
        "The judge eval also carries a deliberate probe: the weak transcript cites "
        "provisions that do not exist (PPC s.899, QSO Art. 512), so the citation "
        "guard is exercised on every run. Accuracy collapsing from 100% on the "
        "strong transcript to 0% on the weak one is the guard working, and because "
        "the judge is told the audit result as ground truth, the fabrications also "
        "drag down its legal-reasoning score."))

    s.append(h2("11.4 Run tracking with MLflow"))

    s.extend(decision(
        "Every eval entry point opens an MLflow run around itself",
        what="Metrics namespaced by section "
             "(<font face='Courier'>retrieval/hit_at_1</font>, "
             "<font face='Courier'>courtroom/f1</font>, "
             "<font face='Courier'>witness/fabrication_rate</font>), the params "
             "that produced them, and the full printed report as "
             "<font face='Courier'>report.txt</font>.",
        how="Params are read from "
            "<font face='Courier'>get_settings()</font> rather than passed in at "
            "the call site - model_text, model_fast, objection_cascade, "
            "reranker_backend, rrf_k, embedding model and dimensions, corpus size, "
            "git commit, and <font face='Courier'>git_dirty</font> recorded "
            "separately because a dirty tree means the commit does not describe "
            "the code that ran.",
        why="Same reasoning as instrumenting the client: the setting somebody "
            "forgets to log is the one that moved the metric. And the metrics tell "
            "you hit@1 fell; only the report tells you <i>which query missed</i>, "
            "so the report is an artifact rather than scrollback.",
        instead="Weights and Biases or a hosted tracker needs an account and a "
                "network. The store here is local SQLite in the repo tree "
                "(<font face='Courier'>MLFLOW_TRACKING_URI</font> points at a "
                "server when there is one) - and SQLite rather than the familiar "
                "<font face='Courier'>./mlruns</font> file store because MLflow 3 "
                "puts that backend in maintenance mode and refuses it by default.",
        purpose="Comparing two runs either side of a change without re-reading a "
                "console. <font face='Courier'>pnpm run eval:ui</font>."))

    s.append(p(
        "Two properties keep it from becoming a liability. It is <b>optional and "
        "quiet about it</b>: <font face='Courier'>mlflow</font> lives in the "
        "<font face='Courier'>eval</font> extra, not in the service dependencies - "
        "the AI service must not acquire a tracking library to serve a request - "
        "and without it the harness runs exactly as before and prints one line "
        "saying so. And <b>it never fails a run</b>: every MLflow call is guarded, "
        "because the metrics cost real money to produce and losing them to a "
        "logging error would be absurd. Because the store is local and gitignored, "
        "a fresh clone has no history, so the recorded baselines in the docs remain "
        "the thing to quote."))
    return s


# ==========================================================================
# PART 12 - Master table
# ==========================================================================


def part_choices():
    s = h1("Part 12", "Every choice on one page: we used X, not Y, because Z")

    s.append(p(
        "The whole document compressed. Read down the last column - each row is a "
        "constraint or a measurement, never a preference.", LEAD))

    s.append(h2("Retrieval and data"))
    s.extend(table(
        ["Area", "Chosen", "Rejected", "Because"],
        [
            ["Chunking", "One row per section / Article",
             "Fixed 512-token windows",
             "A provision is already the citable, self-contained unit; windows "
             "split provisos from rules and produce chunks with no citation."],
            ["Vector storage", "jsonb + exact numpy scan",
             "pgvector ivfflat / HNSW, external vector DB",
             "53 provisions; exact scan is faster <i>and</i> exact, and the host "
             "PostgreSQL has only pg_trgm. Approximate indexing earns its keep "
             "past ~100k vectors."],
            ["Similarity", "L2-normalise, then dot product",
             "Cosine computed per pair",
             "Normalising once at load turns the whole search into one matrix "
             "multiply."],
            ["Lexical retrieval", "BM25Okapi in memory",
             "PostgreSQL full-text search, pg_trgm",
             "Keeps ranking logic in one file; no scores crossing a network "
             "boundary mid-fusion."],
            ["Tokenizer", "Keeps hyphenated terms whole",
             "Default whitespace/punctuation split",
             "'qatl-i-amd' is one discriminative term; splitting scatters it into "
             "'i' and 'e'."],
            ["Fusion", "RRF, k = 60", "Weighted score blending",
             "BM25 is unbounded, cosine is a narrow band; blending needs a "
             "constant retuned per corpus. RRF uses rank only."],
            ["Reranking", "LLM scoring legal applicability",
             "ms-marco cross-encoder",
             "Measured: the cross-encoder put the governing provision at #10 of 15 "
             "with every score negative - worse than no reranker. The LLM put it "
             "at #1 and promoted the doctrinal exception from #19 into the top 3."],
            ["Rerank on voice turns", "Off", "On",
             "~8 s per query. Latency is the product on the live path; correctness "
             "is the product on rulings, generation and verdicts, where it is on."],
        ],
        [14, 22, 22, 42]))

    s.append(h2("Agents and reasoning"))
    s.extend(table(
        ["Area", "Chosen", "Rejected", "Because"],
        [
            ["Orchestration", "LangGraph StateGraph, 5 nodes",
             "One completion swapping persona by phase",
             "Only a graph can put three agents in sequence on one utterance; and "
             "'do not answer a struck question' becomes a missing edge rather than "
             "an instruction a model may ignore."],
            ["Supervisor", "Pure routing functions", "An LLM router agent",
             "Phase plus witness presence fully determine who acts. Determinism is "
             "what makes 0 routing leaks assertable rather than likely."],
            ["Judge", "ReAct with search_statute", "Ruling from model knowledge",
             "An evidentiary objection turns on what the provision says; the "
             "recorded trace shows the ruling is grounded rather than asserting "
             "it."],
            ["ReAct thought", "A required tool argument", "Narration in the "
             "assistant message",
             "Under tool_choice='auto' the content comes back None, so every "
             "recorded thought was empty. A required argument cannot be."],
            ["Loop bound", "3 tool rounds, then forced JSON, then overrule",
             "Unbounded until the model is satisfied",
             "Bounds latency and cost per ruling; overruling is the least "
             "disruptive default because it lets a possibly-proper question stand."],
            ["Objection model", "gpt-4o-mini screens, gpt-4o confirms",
             "gpt-4o for every screen",
             "Silent turns are the majority and 51% cheaper this way, with "
             "identical labels. Escalation is one-directional: cheap may stay "
             "silent alone, never object alone."],
            ["Witness tools", "None", "search_statute, like the judge",
             "A witness testifies to perception, not research; the material it may "
             "use is already in its prompt."],
            ["Witness output", "One of four committed outcomes",
             "Free-form answer",
             "Making 'I do not recall' first-class is what stops a fabrication "
             "engine wearing a name. 0/9 fabrications measured."],
            ["Streaming", "run_turn defined in terms of run_turn_stream",
             "Separate batch and stream implementations",
             "First audio 16.1 s to 8.1 s, and the text and voice courtrooms "
             "cannot diverge."],
        ],
        [14, 22, 22, 42]))
    return s


def part_choices_2():
    s = [h2("Platform, contract and operations")]
    s.extend(table(
        ["Area", "Chosen", "Rejected", "Because"],
        [
            ["Service split", "Node for HTTP, Python for reasoning",
             "One Node service; one Python service",
             "LangGraph, numpy, rank_bm25, MLflow are Python; contract-first "
             "codegen and audio streaming are Node. Neither language gives up "
             "what it is good at."],
            ["Schema", "Drizzle only; Python uses raw SQL",
             "SQLAlchemy + Alembic alongside",
             "Two definitions of one database drift silently. A loud query error "
             "on drift <i>is</i> the design."],
            ["Transport types", "OpenAPI 3.1 + Orval codegen",
             "Hand-written types, tRPC",
             "One document generates both the client and the server validators; "
             "tRPC cannot describe a boundary a Python service also honours."],
            ["Validation", "Generated Zod at every route boundary, on responses too",
             "Ad-hoc parsing",
             "A contract violation becomes a 500 on our side rather than a "
             "rendering bug on the user's."],
            ["Python-Node contract", "Hand-written interfaces + Pydantic aliases",
             "Generated from a second spec",
             "Internal, fast-moving surface; Pydantic already validates it at "
             "runtime and the compiler catches drift on the Node side."],
            ["Password hashing", "scrypt from node:crypto",
             "bcrypt / argon2 dependency",
             "Already in the standard library; the parameters are the decisions a "
             "library would make silently anyway."],
            ["Sessions", "Stateless signed cookie", "Server-side session table",
             "No second table to keep in step. Cost stated: rotating AUTH_SECRET "
             "is the only revocation."],
            ["Rate limiting", "Sliding window on email <i>and</i> IP",
             "Fixed window, single key",
             "Per-account alone lets a guess be sprayed across a roster; per-IP "
             "alone lets one NAT lock out a lab. Fixed windows allow double rate "
             "at the boundary."],
            ["Speech synthesis", "Dedicated TTS endpoint",
             "Audio chat model repeating the text",
             "A completion may paraphrase, and a paraphrased citation is no longer "
             "the one the audit verified."],
            ["Transcription accuracy", "Vocabulary hint from the case file",
             "Fuzzy post-correction of names",
             "A hint biases spelling only; post-correction would rewrite what the "
             "student said."],
            ["Cost accounting", "Wrap the shared client once",
             "Instrument each call site",
             "Eight call sites today; the ninth is the one nobody remembers."],
            ["Prices", "Pinned in source", "Fetched live",
             "An eval whose cost depends on the day it ran is not a measurement."],
            ["Run tracking", "MLflow, local SQLite, optional",
             "Hosted tracker; ./mlruns file store",
             "No account or network needed; MLflow 3 puts the file store in "
             "maintenance mode."],
            ["Prompt-injection guard", "Not built - yet",
             "A filter on transcribed speech",
             "0 of 36 attacks land, so a guard has no measurable effect on this "
             "surface today. Build it when an attack lands, and add the attack "
             "first."],
        ],
        [14, 22, 22, 42]))
    return s


# ==========================================================================
# PART 13 - Question bank
# ==========================================================================


def part_qa_intro():
    s = h1("Part 13", "Technical question bank")
    s.append(p(
        "113 questions of the kind an examiner, a reviewer or a future "
        "maintainer actually asks, grouped by subsystem. Answers are written to be "
        "said out loud: the claim first, the number or the constraint second.",
        LEAD))
    s.append(h2("A. Architecture and service boundaries"))
    return s


def qa_architecture():
    s = []
    s.extend(qa(
        "Why three services? Would one not be simpler to deploy?",
        "Simpler to deploy, worse at everything else. The libraries that make this "
        "project defensible - LangGraph, rank_bm25, numpy, MLflow - are Python. "
        "The tooling that keeps the browser contract honest - OpenAPI to a "
        "generated React Query client and generated Zod validators - is Node. A "
        "single Node service could not use LangGraph at all; a single Python "
        "service would throw away the generated client and put the web app's types "
        "back in a human's hands. The cost is one internal HTTP hop, which is "
        "microseconds next to a model call."))
    s.extend(qa(
        "What exactly is the rule for what goes in Python versus Node?",
        "If it calls a model or decides something, it is Python. If it owns the "
        "HTTP contract, writes the database, or moves audio, it is Node. "
        "Transcription and speech synthesis are in Node and are <i>not</i> "
        "exceptions to the rule: they are transport - nothing decides anything "
        "there. Exactly one genuine exception remains, the manually-raised "
        "objection ruling, and it is recorded as pending work rather than "
        "defended as a pattern."))
    s.extend(qa(
        "Why does the browser never talk to the Python service directly?",
        "Two reasons. First, credentials: OpenAI keys exist only in the API and AI "
        "services, and a browser that can reach the reasoning service is a browser "
        "that can be pointed at it by anyone. Second, the session cookie is "
        "same-origin - everything goes through <font face='Courier'>/api/*</font>, "
        "so CORS is never involved and a cross-origin caller cannot send the "
        "cookie at all. That is the property that makes an httpOnly cookie worth "
        "using."))
    s.extend(qa(
        "Two services write the same database. How do you stop them disagreeing "
        "about the schema?",
        "By making it impossible to disagree: only Drizzle defines tables. The "
        "Python service issues raw SQL against columns it does not own, so a "
        "column rename is a loud query error on the next request rather than a "
        "second ORM quietly filling in a default. The alternative - SQLAlchemy "
        "models plus Alembic - would give two migration histories that can both "
        "claim to be current, which is how staging and production drift apart."))
    s.extend(qa(
        "Why validate responses with Zod as well as requests?",
        "Because the failure mode of an unvalidated response is a rendering bug in "
        "front of the user, and the failure mode of a validated one is a 500 in "
        "our logs. Parsing on the way out turns a contract violation into our "
        "problem at the moment it happens."))
    s.extend(qa(
        "The Express-to-Python boundary is hand-written. Is that not the same "
        "drift risk you just argued against?",
        "It is the same risk, weighed differently. That boundary is internal, it "
        "changes with every agent feature, and Pydantic validates it at runtime "
        "with camelCase aliases - so drift surfaces as a 422 in development rather "
        "than silently. Generating it would put a build step on the surface that "
        "moves most. The browser boundary is the opposite: stable, external, and "
        "consumed by generated code, so it earns the codegen."))
    return s


def qa_architecture_2():
    s = []
    s.extend(qa(
        "What happens if the Python service is down?",
        "Anything requiring reasoning fails with a typed "
        "<font face='Courier'>AiServiceError</font> carrying the status and path - "
        "the client distinguishes 'unreachable', 'timed out after 60 s' and 'the "
        "service returned 4xx/5xx'. The case library, auth and reading past "
        "sessions keep working because none of them call across. There is no "
        "silent degradation: the system does not answer a legal question with "
        "something it made up locally."))
    s.extend(qa(
        "Why a 60-second timeout? That seems enormous.",
        "A reranked retrieval plus a model call legitimately takes ~10 s, and too "
        "tight a timeout turns a slow answer into a failed one. On the streaming "
        "path the timeout guards <i>connecting</i> only - once the service starts "
        "answering, the exchange is bounded by the graph's own capped loops, and a "
        "courtroom turn can legitimately outlive a request timeout sized for one "
        "call."))
    s.extend(qa(
        "Why is the statute index built at startup rather than on first request?",
        "So the first student of the day does not pay for it. It is a single query "
        "plus a numpy vstack, and it happens in the FastAPI lifespan handler, "
        "which also logs how many provisions were indexed and how many carry "
        "embeddings. The LangGraph import is the opposite case - 49 seconds - so "
        "that one <i>is</i> lazy and cached."))
    s.extend(qa(
        "Both services read the same .env. Why not per-service config?",
        "One credential in one place cannot drift out of step with itself. The "
        "Python settings object resolves the workspace "
        "<font face='Courier'>.env</font> two levels up explicitly for that "
        "reason. It is a single-machine classroom deployment; the moment it is not, "
        "the variables move to the orchestrator and nothing in the code changes, "
        "because everything reads environment variables rather than the file."))
    s.append(h2("B. Retrieval and RAG"))
    s.extend(qa(
        "Explain your RAG pipeline in one breath.",
        "Structural chunking - one provision per row - then two retrievers in "
        "parallel: BM25 over heading plus content, and dense cosine over "
        "text-embedding-3-small vectors held in one normalised numpy matrix. Their "
        "ranked lists fuse with Reciprocal Rank Fusion at k=60, and the top "
        "<font face='Courier'>3k</font> of that fusion is reranked by an LLM "
        "scoring legal applicability. Reranked, that returns the governing "
        "provision at rank one on 20 out of 20 golden queries."))
    s.extend(qa(
        "Why hybrid? Are embeddings not enough on their own?",
        "Not for this query distribution, which is bimodal. 'Section 302' and "
        "'qatl-i-amd' are exact identifiers that embeddings blur into a cloud of "
        "neighbouring provisions. 'The witness is just repeating what someone told "
        "him' shares no vocabulary at all with Art. 71, whose text reads 'oral "
        "evidence must, in all cases whatever, be direct' - only dense retrieval "
        "finds that. The golden set is tagged semantic or lexical precisely so a "
        "regression in one half cannot hide behind the other."))
    s.extend(qa(
        "Why RRF instead of just adding the scores together?",
        "Because the scores are not on the same scale and never will be. BM25 "
        "scored 7.12 on one query and above 40 on another - it is unbounded and "
        "query-dependent - while cosine similarities sit in a 0.30 to 0.45 band. "
        "Any weighted blend needs a normalisation constant that has to be retuned "
        "whenever the corpus changes. RRF uses only rank position, so it is "
        "scale-free, and k=60 damps the head so one retriever's top hit cannot "
        "dominate the fusion by itself."))
    return s


def qa_retrieval_2():
    s = []
    s.extend(qa(
        "Where does k = 60 come from? Did you tune it?",
        "It is the value from Cormack, Clarke and Buettcher (2009), the paper that "
        "introduced RRF. It was not tuned here, and that is deliberate: with 20 "
        "golden queries, tuning a fusion constant would fit the golden set rather "
        "than the corpus. What k controls is how much the head of each list "
        "dominates - a small k makes rank 1 overwhelming, a large k flattens the "
        "lists towards equal weight. 60 is the published middle."))
    s.extend(qa(
        "Why no pgvector? Everyone uses pgvector.",
        "Three reasons, in order of weight. The host PostgreSQL has only "
        "<font face='Courier'>pg_trgm</font>, so pgvector would be a deployment "
        "requirement rather than a free upgrade. At 53 provisions - and a few "
        "thousand fully ingested - a full float32 matrix multiply is single-digit "
        "milliseconds, so an approximate index would be <i>slower</i>. And "
        "approximate means approximate recall: ivfflat and HNSW trade exactness "
        "for speed we do not need. Approximate indexing earns its complexity "
        "somewhere north of 100,000 vectors."))
    s.extend(qa(
        "At what corpus size would you change your mind?",
        "When the exact scan stops being imperceptible, which for a 1536-dimension "
        "float32 matrix is around 10^5 vectors - roughly two orders of magnitude "
        "beyond a fully ingested Pakistani statute book. The migration path is "
        "already clean: the index is behind "
        "<font face='Courier'>CorpusIndex</font>, and only "
        "<font face='Courier'>_vector_search</font> would change."))
    s.extend(qa(
        "Why store embeddings as jsonb rather than a float array column?",
        "jsonb needs no extension and round-trips cleanly through both drivers - "
        "asyncpg is given a jsonb codec at connection level so the Python side "
        "never calls <font face='Courier'>json.loads</font> at a call site. The "
        "vectors are read once at startup into numpy, so the storage format only "
        "has to be correct, not fast."))
    s.extend(qa(
        "How do you compute cosine similarity efficiently?",
        "By not computing it. Every stored vector is L2-normalised at load and "
        "every query vector at embed time, so cosine reduces to a dot product and "
        "the entire search is <font face='Courier'>matrix @ query</font> followed "
        "by an argsort. One BLAS call for the whole corpus."))
    s.extend(qa(
        "What stops a stale embedding silently poisoning retrieval?",
        "Two guards. The row records which model produced its vector, and the "
        "index build skips - and warns about - any row whose "
        "<font face='Courier'>embedding_model</font> differs from the configured "
        "one, so a half-completed re-index cannot leave two embedding spaces in "
        "the same matrix. And the row records a hash of the exact text that was "
        "embedded, which is what catches corrected wording. Before that hash "
        "existed, correcting PPC s.375 from the repealed definition to the current "
        "one changed nothing about what retrieval matched, because an embedding "
        "was present and the model had not changed."))
    s.extend(qa(
        "Why does BM25 discard documents scoring zero?",
        "A zero means the document shares no query term at all. Keeping it would "
        "pad the fusion with candidates that outrank nothing but still consume "
        "candidate slots, pushing genuine near-misses out of the reranker's "
        "window."))
    s.extend(qa(
        "Why is the reranked slice wider than the number of results you return?",
        "Because the point of reranking is to promote something the bi-encoders "
        "ranked <i>just below</i> the cut. Reranking only the top k would let the "
        "reranker reorder what fusion already liked and never rescue what fusion "
        "missed. The slice is <font face='Courier'>top_k * 3</font>; the measured "
        "example is Art. 46 moving from RRF rank 19 into the top 3."))
    return s


def qa_retrieval_3():
    s = []
    s.extend(qa(
        "A cross-encoder is the textbook reranker. Why is yours an LLM?",
        "Because the textbook cross-encoder was benchmarked and lost, on the "
        "clearest possible query. For 'the witness is just repeating what somebody "
        "else told him outside court', the governing provision is QSO Art. 71. RRF "
        "alone put it at #2. The LLM reranker put it at #1. "
        "<font face='Courier'>ms-marco-MiniLM-L-6-v2</font> put it at #10 of 15 "
        "with every score negative - it made retrieval worse than not reranking at "
        "all."))
    s.extend(qa(
        "Why did the cross-encoder fail so badly? Was it misconfigured?",
        "No - it was correctly reporting that the corpus is out of its "
        "distribution. <font face='Courier'>ms-marco-*</font> checkpoints are "
        "trained on Bing query/passage pairs, so the training signal rewards "
        "lexical and topical overlap in a web-search distribution. Nothing in it "
        "connects a colloquial description of hearsay to the phrase 'oral evidence "
        "must, in all cases whatever, be direct'. The uniformly negative scores are "
        "the model saying so. The general lesson is that an out-of-domain "
        "cross-encoder is worse than no reranker."))
    s.extend(qa(
        "So you would never use a cross-encoder here?",
        "The backend is still in the codebase and still selectable, because the "
        "argument is about the <i>checkpoint</i>, not the architecture. A legal- or "
        "instruction-tuned reranker - a BGE reranker, say - would be 400 times "
        "faster and free per query. Nothing changes but "
        "<font face='Courier'>RERANKER_BACKEND</font>. What is refused is shipping "
        "a web-search model into a statute book because the architecture has the "
        "right name."))
    s.extend(qa(
        "What did the reranker actually buy, in numbers?",
        "hit@1 from 0.80 to 1.00 and MRR from 0.88 to 1.00 across 20 golden "
        "queries. It promotes exactly four semantic near-misses to rank one: "
        "hearsay 2 to 1, leading-question-in-chief 3 to 1, impeaching credit 2 to "
        "1, punishment for murder 3 to 1. Fusion already put every governing "
        "provision in the top 3, so the reranker's job is precisely the last step."))
    s.extend(qa(
        "Your fusion-only numbers got <i>worse</i> after you corrected the corpus. "
        "Is that not a regression?",
        "It is, and it is the honest kind. Fusion-only fell from hit@1 0.90 / MRR "
        "0.94 to 0.80 / 0.88 because provisions restored to their full official "
        "text carry provisos, explanations and illustrations the truncated versions "
        "did not - a corpus that says more is a harder corpus to rank. The "
        "reranker absorbed all of it and stayed at 1.00 / 1.00, so its measured "
        "contribution <i>grew</i> from +0.10 to +0.20 hit@1. The case for "
        "defaulting it on is stronger after the corpus became correct."))
    s.extend(qa(
        "Retrieval scored 1.00 before the corpus was correct and 1.00 after. Does "
        "that not prove the metric is useless?",
        "It proves the metric measures what it says and nothing more: whether the "
        "right <i>row</i> comes back, not whether that row says what the statute "
        "says. No IR metric could have caught the wrong text. Only a diff against "
        "the official source could, which is exactly why corpus verification is a "
        "separate exercise with its own tooling rather than something hit@1 was "
        "ever going to cover."))
    s.extend(qa(
        "Why is reranking off during a live voice turn?",
        "Because it costs about 8 seconds per query and the student is sitting in "
        "silence. On the live path latency <i>is</i> the product. On rulings, case "
        "generation and verdicts, correctness is the product, so it is on there. "
        "The judge's own <font face='Courier'>search_statute</font> tool does "
        "rerank, because a ruling read from the wrong provision is worse than a "
        "slower ruling."))
    s.extend(qa(
        "What happens if the reranker fails mid-request?",
        "The ordering degrades, the request does not fail. The cross-encoder "
        "backend falls back to the LLM backend; the LLM backend falls back to the "
        "unmodified RRF ordering via a null reranker that returns descending "
        "scores, so the caller's sort is a no-op and there is no branch on 'did "
        "reranking happen'. The function returns which backend actually ran, so "
        "logs report the path that executed rather than the one configured."))
    return s


def qa_citations():
    s = [h2("C. Citations, grounding and trust")]
    s.extend(qa(
        "How do you stop the system inventing section numbers?",
        "Four layers, and none of them is 'the prompt says do not'. Generation is "
        "constrained to a palette of provisions retrieved <i>before</i> the case is "
        "written. Objection grounds are resolved from the corpus at runtime, so a "
        "ground whose provision is missing is not offered at all. Every utterance "
        "is audited by regex plus index lookup - agents' and students' alike. And "
        "any generated ground citing a provision that does not exist is dropped "
        "before the case is stored."))
    s.extend(qa(
        "Why is the audit a regex and not a model call?",
        "Because it has to be affordable enough to run on every streamed utterance "
        "<i>before</i> that utterance is spoken. It is microseconds over an "
        "in-memory index, so a fabricated provision is flagged on the line that "
        "carried it while the student is still hearing it, rather than at the end "
        "of the turn. It would also be circular to ask a model whether a model's "
        "citation is real."))
    s.extend(qa(
        "What are the three citation statuses and why is 'uncovered' separate?",
        "<font face='Courier'>verified</font> - the provision exists in the corpus. "
        "<font face='Courier'>not_found</font> - the instrument is in the corpus "
        "but has no such provision, which is a fabrication. "
        "<font face='Courier'>uncovered</font> - the instrument itself is outside "
        "the indexed corpus, which is a coverage gap and not a lie. It is separate "
        "because an instrument with <i>no alias at all</i> is not judged "
        "unconfirmed - it is never seen. That silence let three seeded cases ship "
        "citing CPC 1908 and the Specific Relief Act while auditing at 100%. "
        "Listing seventeen uncovered instruments does not change the fabrication "
        "count; it changes accuracy's denominator to the honest one."))
    s.extend(qa(
        "What is the difference between <font face='Courier'>hallucinated</font> "
        "and <font face='Courier'>agentFabricated</font>, and why does it exist?",
        "The red-team eval caught the raw audit flagging the <i>judge</i> for "
        "fabrication while the judge was correctly refusing a section the student "
        "had invented - 'the reference to section 899 of the Pakistan Penal Code is "
        "irrelevant'. The audit sees a citation absent from the corpus; it cannot "
        "tell relying on one from rejecting one. So the turn now marks citations "
        "the student had already put on the record, and "
        "<font face='Courier'>agentFabricated</font> carries only what an agent "
        "introduced by itself. <b>Anything user-facing uses that field.</b> "
        "<font face='Courier'>hallucinated</font> is left unchanged so no number "
        "other things depend on shifts underneath them."))
    s.extend(qa(
        "How do you know the statute text itself is correct?",
        "Because it was diffed word-for-word against an official print - 52 of 53 "
        "provisions, with the wording replaced from the source wherever the two "
        "disagreed. That is the only method that works, and the exercise proves "
        "it: it found six numbering errors, three corrupted Constitution articles, "
        "38 stray footnote anchors, and a definition of rape repealed in 2016. "
        "<b>The citation audit could not have caught any of them</b>, because the "
        "corpus is the audit's own ground truth."))
    s.extend(qa(
        "Give the sharpest example of that.",
        "The objection ground for insulting questions cited QSO Art. 143. The "
        "provision is Art. 148; Art. 143 is 'Court to decide when question shall "
        "be asked'. Every layer of the system agreed with itself perfectly - the "
        "ground resolved, the citation audited as verified, retrieval returned the "
        "row - and the citation was wrong against the statute book. An internally "
        "consistent corpus that is wrong passes every automated guard in the "
        "repository."))
    s.extend(qa(
        "Why is one provision still unverified, and why not just hide it?",
        "Constitution Art. 199 - the article every writ petition is filed under. "
        "The corpus text is <i>later</i> than the 2012 National Assembly print: it "
        "refers to the Federal Constitutional Court and to clause (1A) barring suo "
        "motu action, so that source cannot confirm it. Hiding it would be the "
        "dishonest option and dropping it would remove the most-used article in "
        "the instrument. It carries a per-provision "
        "<font face='Courier'>verified: false</font>, a note saying why, and "
        "everything retrieved from it is labelled in the interface and marked "
        "<font face='Courier'>[UNVERIFIED TEXT]</font> in prompt blocks."))
    s.extend(qa(
        "Why is verification per provision rather than per statute file?",
        "Because a diff either matched or it did not, one provision at a time. A "
        "file-level flag would have done one of two wrong things: marked Art. 199 "
        "verified because its seven neighbours were, or dragged those seven down "
        "to a warning because of the one that is not. Files written before "
        "per-provision flags existed still inherit the file default, so nothing "
        "changed until a provision was marked individually."))
    return s


def qa_agents():
    s = [h2("D. The multi-agent courtroom")]
    s.extend(qa(
        "What makes this genuinely multi-agent rather than one model with three "
        "prompts?",
        "That three of them act <i>in sequence on one utterance</i>, each with its "
        "own decision to make, its own tools, and its own turn to speak. One "
        "student question can produce an objection from counsel, a ruling from the "
        "bench, and then either a witness answer or structural silence. A "
        "persona-swapping completion produces exactly one reply per input; it "
        "cannot produce that sequence at all."))
    s.extend(qa(
        "Why LangGraph rather than writing the loop by hand?",
        "The state reducer and the conditional edges are the value. "
        "<font face='Courier'>events</font> is annotated with "
        "<font face='Courier'>operator.add</font>, so each node returns only its "
        "own contribution and LangGraph concatenates them in execution order - no "
        "node knows about any other. And "
        "<font face='Courier'>astream(stream_mode='updates')</font> gives per-node "
        "streaming for free, which is what took first audio from 16.1 s to 8.1 s. "
        "Hand-rolling that is a week of work and a worse diagram."))
    s.extend(qa(
        "Your supervisor is not an LLM. Is that not the whole point of a "
        "supervisor pattern?",
        "The point of a supervisor is to decide who acts next. Here the phase and "
        "the presence of a witness fully determine that - there is nothing to "
        "infer, so a model could only add latency, cost and the possibility of "
        "getting it wrong. More importantly, determinism is what makes the central "
        "invariant <i>assertable</i>: a sustained objection must stop the witness "
        "answering, and because that is a missing edge rather than an instruction, "
        "a violation would be a graph bug rather than a model opinion. Measured 0 "
        "across 32 scenarios, every run."))
    s.extend(qa(
        "Walk me through the routing.",
        "Three pure functions. At entry: a witness on the stand routes to the "
        "objection screen; otherwise straight to the primary responder - the "
        "witness if one is up, opposing counsel in a cross with nobody up, the "
        "bench otherwise. After the screen: an objection routes to the judge, "
        "silence routes to the primary responder. After a ruling: sustained routes "
        "to END, overruled routes to the primary responder."))
    s.extend(qa(
        "What does 'the judge is a ReAct agent' actually mean here?",
        "It means the bench does not rule from memory. When an objection is on the "
        "table it runs a bounded Thought-Action-Observation loop: it states what "
        "it needs to check, calls "
        "<font face='Courier'>search_statute</font>, observes the provisions that "
        "come back, and only then rules in strict JSON. It reads the provision the "
        "objection rests on <i>together with its neighbours</i> - a "
        "leading-question objection under Art. 137 is decided by reading it "
        "alongside Art. 136, which defines a leading question, and Art. 138, which "
        "says when one is allowed. Every step is recorded and returned, so the "
        "ruling is shown to be grounded rather than asserted to be."))
    s.extend(qa(
        "Why is the thought a required tool argument instead of the model's "
        "narration?",
        "Because narration does not survive tool calling. Under "
        "<font face='Courier'>tool_choice='auto'</font> a model that decides to "
        "call a tool usually returns <font face='Courier'>content=None</font>, so "
        "harvesting the thought from the assistant message produced an empty "
        "string on every step and the trace shown to a student was two-thirds of a "
        "ReAct loop. A required argument cannot come back empty, and it binds the "
        "reasoning to the specific call it justifies. Cost of that visibility, "
        "measured over the same 32 scenarios: objected turns from $0.0153 to "
        "$0.0168, silent turns unchanged, decision quality identical at 18 true "
        "positives and 14 true negatives."))
    s.extend(qa(
        "Why cap the ReAct loop at three rounds?",
        "Three is enough to read a provision and its neighbours, and the cap bounds "
        "the latency and token cost of a single ruling. Every loop in this codebase "
        "declares its bound explicitly; an agent that can loop until it is "
        "satisfied is an agent that can spend an unbounded amount of a student's "
        "time."))
    s.extend(qa(
        "What happens if the judge never produces a ruling?",
        "Two fallbacks. It is asked once more, in JSON mode with no tools "
        "available, to rule now. If even that fails the objection is "
        "<b>overruled</b> - chosen because it is the least disruptive default: "
        "overruling lets a possibly-proper question stand, whereas defaulting to "
        "sustained would wrongly strike a question and silence a witness on a "
        "technical failure."))
    return s


def qa_agents_2():
    s = []
    s.extend(qa(
        "How is opposing counsel 'autonomous' in any meaningful sense?",
        "Nobody triggers it. After <i>every</i> question the student puts to a "
        "witness, the objection screen runs and decides on its own whether the "
        "question is improper and on which ground. There is no button, no prompt "
        "from the student, and no scripted scenario. The evidence that it is "
        "reasoned rather than scripted is that it picks different, well-founded "
        "grounds for different improper questions - a foundationless accusation "
        "drew <font face='Courier'>insulting_question</font> on one run and "
        "<font face='Courier'>leading_question</font> on another, both defensible."))
    s.extend(qa(
        "How do you guarantee it can only cite real provisions?",
        "By construction. The catalogue of grounds is resolved from the statute "
        "corpus at runtime - each ground names an instrument and a provision "
        "number, and a ground whose provision is not in the index is not returned "
        "to the agent at all. The model chooses a "
        "<font face='Courier'>groundId</font> from that list, and a "
        "<font face='Courier'>groundId</font> the list does not contain is "
        "discarded as 'no objection' rather than raised. So an objection that "
        "reaches the student always carries a citation the corpus can back."))
    s.extend(qa(
        "Explain the objection cascade and why the escalation is one-directional.",
        "The screen fires on every question and the honest answer to most is 'no "
        "objection', which does not need a frontier model. So "
        "<font face='Courier'>gpt-4o-mini</font> takes the screen, and only a "
        "<i>proposed</i> objection is re-decided by "
        "<font face='Courier'>gpt-4o</font>. The cheap model can therefore stay "
        "silent on its own but can never object on its own. That asymmetry is the "
        "design: the objection is the part that teaches a rule, and teaching a "
        "wrong one is the expensive failure. Measured: silent turns 51% cheaper "
        "and 34% faster, objected turns the same cost and 1.7 s slower, identical "
        "labels - 18 objections, 14 silences."))
    s.extend(qa(
        "Why does the witness have no tools when every other agent does?",
        "Because a witness testifies to their own perception. An agent that could "
        "look things up would be testifying to things it looked up, which is the "
        "opposite of what a witness is for. And the material it <i>is</i> entitled "
        "to - its statement of record and what it has already sworn this session - "
        "is handed to it in the prompt, so a tool over that would fetch nothing it "
        "does not already hold. Withholding the tool is the legal constraint "
        "expressed in code."))
    s.extend(qa(
        "What is the witness's agency then?",
        "The decision every real witness makes under examination: <i>can I "
        "properly say this?</i> It must commit to one of four outcomes before "
        "speaking - answer, don't recall, decline speculation, or correct the "
        "record - and name what in its own record supports it. A factual assertion "
        "with no support in the statement or prior testimony is not permitted to "
        "be spoken as fact. The honest answers are made first-class rather than "
        "left as things a compliant model will never choose."))
    s.extend(qa(
        "Why only four outcomes? Why not let it decide freely?",
        "An open-ended set would let the model invent a posture that is not the "
        "witness's to take - objecting, conferring with counsel, addressing the "
        "bench. A witness's discretion is genuinely narrow, so the enumeration is "
        "narrow. An unrecognised outcome keeps the spoken words but drops the "
        "reasoning step: better a bare answer than a trace asserting a decision "
        "the witness did not make."))
    s.extend(qa(
        "How do you know the witness is not just fabricating fluently?",
        "It is measured structurally rather than judged. Each question is put to a "
        "witness whose statement is fixed, and the scenarios are labelled by what "
        "that statement does and does not contain. A question the statement cannot "
        "support, answered with <font face='Courier'>outcome == 'answer'</font>, "
        "<i>is</i> the fabrication - no second model is needed to decide that. "
        "Result: 0 fabrications across 9 unanswerable questions, and 17 of 17 "
        "outcomes correct. Separately, answering with "
        "<font face='Courier'>grounding == 'none'</font> is logged as a warning in "
        "production."))
    s.extend(qa(
        "What happens when the student interrupts mid-answer?",
        "The web app cuts playback the moment it hears speech and posts what was "
        "said. Two decisions follow: was that an objection and on which "
        "corpus-backed ground - constrained to the same catalogue counsel uses, so "
        "a student objection is citable by construction too - and then, if it was, "
        "the same ReAct judge rules on it. There is one judge in this courtroom. "
        "An interruption that was not an objection is not forced into becoming "
        "one, and an objection with no citable ground is answered with a direction "
        "to name a ground rather than one being invented for the student."))
    return s


def qa_agents_3():
    s = []
    s.extend(qa(
        "Why is <font face='Courier'>run_turn</font> defined in terms of "
        "<font face='Courier'>run_turn_stream</font> rather than the other way "
        "round?",
        "So the text courtroom and the voice courtroom cannot become two different "
        "courtrooms. Streaming is the implementation; batch is a loop that "
        "collects it. If they were written side by side, a change to agent "
        "ordering or a new event type would land in one and not the other, and the "
        "evaluation harness - which drives the batch path - would stop measuring "
        "what a student actually experiences."))
    s.extend(qa(
        "Why audit each streamed event separately when there is already a "
        "turn-level audit?",
        "Because a fabricated provision should be flagged on the utterance that "
        "carried it, while that utterance is still the thing the student is "
        "hearing. The per-event audit costs nothing - it is a regex pass over an "
        "in-memory index - and the turn-level audit is still taken over the joined "
        "transcript, so a provision two agents both cite is counted once and the "
        "batch caller's numbers are unchanged."))
    s.extend(qa(
        "Why is the LangGraph import lazy?",
        "It costs about 49 seconds cold. Building the compiled graph at service "
        "startup would put that on every restart, including restarts triggered by "
        "the dev server's reloader; putting it at the top of a hot path would put "
        "it in front of a student. So it is built on first use and cached in "
        "<font face='Courier'>get_graph()</font> - a service that never runs a "
        "turn never pays for it."))
    s.extend(qa(
        "How is the case brief given to the agents, and what does it cost?",
        "<font face='Courier'>case_context()</font> always carries title, area, "
        "summary, applicable laws, which side the student is on, and the phase. "
        "When the case has a brief it appends three blocks - facts as pleaded, "
        "grounds raised, relief sought. The grounds are the point: they are the "
        "propositions the case stands on, so the bench can press a student on a "
        "ground they actually pleaded instead of inferring an argument from a "
        "summary. Measured with tiktoken, a real brief takes that block from 158 "
        "to 465 tokens, +307 per agent call that embeds it - which is why every "
        "list is capped at 8 facts, 6 grounds, 5 prayer items, 400 characters "
        "each."))
    s.extend(qa(
        "A case with no brief - does the courtroom behave differently?",
        "No, and that is enforced: an absent brief renders byte-identical to the "
        "version that predated briefs. Library cases and everything generated "
        "before the feature carry <font face='Courier'>brief = null</font>, and "
        "<font face='Courier'>case_context()</font> keys its unchanged-output path "
        "off exactly that being null. The courtroom eval fixture deliberately has "
        "no brief, which makes that suite a regression check for the feature - and "
        "explicitly <i>not</i> a measurement of what the brief costs or how it "
        "changes behaviour."))
    s.append(h2("E. Memory"))
    s.extend(qa(
        "Describe the memory architecture.",
        "Two tiers. Working memory is every turn of the current phase, replayed "
        "verbatim, assembled from the database with no model call. Long-term "
        "memory is a structured case file - narrative summary, student claims, "
        "witness testimony, judge directions - produced by one summarisation call "
        "per phase transition. Four transitions means four calls per session."))
    s.extend(qa(
        "Why summarise on phase transitions instead of every turn?",
        "Within a phase the agent already sees the raw turns, so summarising each "
        "one spends a model call to produce information the agent is not missing. "
        "A watermark - the highest turn id already folded in - makes each fold "
        "incremental rather than a re-read of the whole transcript."))
    s.extend(qa(
        "Why keep memory structured rather than as a paragraph?",
        "Because the fields are used individually. "
        "<font face='Courier'>studentClaims</font> is what a contradiction check "
        "compares a new assertion against - counsel confronting a student with "
        "what they said in the opening - and flattening it into narrative prose "
        "would make that comparison lossy. Each list is capped so a long session "
        "cannot crowd the actual question out of the context window."))
    s.extend(qa(
        "Why does a witness get a different memory block from the judge?",
        "Because courts exclude witnesses from the room while other witnesses "
        "testify. Handing a witness the full record lets it answer from evidence "
        "it never heard - not a memory bug but a procedural one, and a student "
        "learning to examine witnesses would be learning from a court that does "
        "not exist. Testimony entries are stored prefixed with the witness's name, "
        "which is what makes the split possible; entries that do not match are "
        "dropped rather than paraphrased, because a witness must not be able to "
        "infer them either."))
    s.extend(qa(
        "What happens if summarisation fails?",
        "Nothing is lost and nothing is retried destructively. The previous memory "
        "<i>and</i> the previous watermark stay in place, so the next transition "
        "folds the same span again. The failure is logged and the phase advance "
        "proceeds - a memory refresh must never block a student from moving on."))
    return s


def qa_generation():
    s = [h2("F. Case generation and verdict scoring")]
    s.extend(qa(
        "How do you retrieve law for a case that does not exist yet?",
        "You cannot, so you invert it. Each area of law maps to a broad seed query "
        "- and optionally a statute filter - that surfaces the provisions that "
        "area typically turns on. That palette is retrieved first, rendered into "
        "the prompt in full, and the model is told to build a dispute that "
        "genuinely turns on some of them, citing only from that exact list and "
        "reproducing each citation string verbatim. Reranking is off for this "
        "call: at that stage recall across an area matters more than precision on "
        "one question."))
    s.extend(qa(
        "Constraining the prompt is not a guarantee. What catches the rest?",
        "A per-ground audit. A ground is prose that contains citations, so an "
        "invented section number inside one would otherwise reach a student as "
        "pleaded law. Each ground is audited individually - a local lookup, no "
        "model call - and any ground citing a provision that does not exist is "
        "dropped. A brief left with fewer than two grounds is rejected rather than "
        "persisted thin, and ground labels are assigned server-side afterwards so "
        "a brief never jumps from A to C and tells the student something was "
        "removed without telling them why."))
    s.extend(qa(
        "Why is generation in Python now when it used to be in Express?",
        "Because it is reasoning: retrieving a palette, drafting a pleading and "
        "auditing citations are all model and corpus work, and the boundary rule "
        "says that lives in the AI service. Express keeps request validation and "
        "persistence. It was the last big violation of the rule, and moving it "
        "left exactly one - the manually-raised objection ruling."))
    s.extend(qa(
        "How does the AI judge score a session?",
        "Three inputs before the scoring call: every statute the <i>student</i> "
        "cited is audited against the corpus; the provisions that actually govern "
        "the case are retrieved (reranked, top 6) so the judge can tell a student "
        "who missed the controlling provision from one who engaged and lost; and "
        "the full transcript. The audit is presented under an explicit heading "
        "saying it is ground truth, not the judge's opinion, with each citation "
        "marked EXISTS or DOES NOT EXIST."))
    s.extend(qa(
        "Do you trust the judge's output?",
        "No, it is validated. Every score must be numeric - booleans are rejected "
        "explicitly, since <font face='Courier'>bool</font> subclasses "
        "<font face='Courier'>int</font> in Python - then rounded and clamped to "
        "0-100, because models routinely return a weighted average as '55.75' and "
        "stranding a finished session over a decimal point would be absurd. A "
        "winning side that is not a party to this case raises rather than "
        "persists. A verdict that cannot be trusted is refused, not written."))
    s.extend(qa(
        "Which number in the verdict cannot be hallucinated?",
        "<font face='Courier'>citationAccuracy</font>. It is computed from the "
        "audit - verified over total - not scored by the model. Everything else in "
        "the verdict is a model's judgement; that one is arithmetic over a "
        "database lookup."))
    s.extend(qa(
        "How do you know the judge is a fair grader?",
        "Two properties, measured separately. <b>Reliability</b>: the same "
        "transcript scored repeatedly moves by about 2 points of standard "
        "deviation, worst spread 10, on the weak transcript. <b>Discrimination</b>: "
        "three transcripts of the <i>same case</i> at different quality rank "
        "correctly every run - strong 85-88, mixed 55-58, weak 25-35, a gap of "
        "53-57 points. Same case, so the difference reflects performance rather "
        "than case difficulty."))
    s.extend(qa(
        "Is the judge influenced by fabricated citations?",
        "Deliberately, yes. The weak transcript cites PPC s.899 and QSO Art. 512, "
        "neither of which exists. Citation accuracy collapses from 100% on the "
        "strong transcript to 50% on the mixed one to 0% on the weak one, and "
        "because the judge is told the audit result as ground truth, those "
        "fabrications also drag down its legal-reasoning score. A student is not "
        "credited for engaging with a provision they invented."))
    return s


def qa_voice():
    s = [h2("G. Voice pipeline")]
    s.extend(qa(
        "Is the voice path a separate system from the text path?",
        "No, and that is the design. The audio is transcribed, and the transcript "
        "enters the graph at START exactly as a typed turn does. What the voice "
        "endpoint adds is delivery: it announces each speaker, streams the words, "
        "then streams that agent's synthesized voice. The reasoning path is "
        "shared, not mirrored."))
    s.extend(qa(
        "Why Server-Sent Events rather than WebSockets?",
        "The traffic is one-directional - the client sends one request and then "
        "only receives. SSE is plain HTTP, so it passes through the dev proxy and "
        "any reverse proxy untouched, carries the session cookie automatically, "
        "and needs no second protocol or connection lifecycle. A WebSocket would "
        "buy bidirectionality this path does not use."))
    s.extend(qa(
        "Why does one route have a 25 MB body limit?",
        "Because spoken audio arrives as base64 inside JSON, and a few seconds of "
        "speech already blows past body-parser's 100 kB default - the request "
        "fails before the route is even reached. The cap is raised on that one "
        "path so an oversized body is only accepted where audio is expected, and "
        "it is set to OpenAI's own 25 MB transcription limit, because anything "
        "larger could not be transcribed at the next hop anyway. A 413 is reported "
        "as 'Recording too large' rather than a 500."))
    s.extend(qa(
        "Why is there no ffmpeg transcode on the normal path?",
        "Because every container the magic-byte check can name - WAV, WebM, MP3, "
        "MP4, OGG - is on the transcription endpoint's accepted list, so "
        "recognising a container is the same thing as being able to send it. The "
        "code previously transcoded everything except WAV and MP3, which meant "
        "every real microphone turn shelled out to ffmpeg, because Chrome's "
        "MediaRecorder emits WebM and nothing else. The one path a student "
        "actually uses depended on an external binary being installed on the "
        "presenting machine, while the synthesized-audio tests returned above that "
        "branch and never noticed. ffmpeg is now reached only for genuinely "
        "unrecognisable bytes."))
    s.extend(qa(
        "How did first audio drop from 16.1 s to 8.1 s?",
        "By streaming the graph instead of batching it. With the batch endpoint the "
        "caller cannot speak counsel's objection until the judge has <i>also</i> "
        "finished its ReAct loop - so the objection, ready at about 7 seconds, "
        "waited for a ruling that lands at about 14. Streaming each node's output "
        "as it completes lets the objection be spoken while the bench is still "
        "reading statute. Counsel now takes the floor at 6.9 s and the ruling "
        "lands at 13.8 s."))
    s.extend(qa(
        "What is the biggest remaining latency?",
        "Transcription, at about 4.5 seconds, using "
        "<font face='Courier'>whisper-1</font>. It is now the largest single block "
        "in front of the first sound, and a faster transcription model is the next "
        "lever."))
    s.extend(qa(
        "Why not use an audio-in / audio-out model and skip a step?",
        "Because a completion asked to repeat text is free to paraphrase it, and a "
        "paraphrased citation would no longer be the one the citation audit "
        "verified - the audit would be vouching for words nobody said. The "
        "dedicated TTS endpoint speaks the audited text or it fails. The only "
        "per-agent parameter it carries is delivery direction: how a line is said, "
        "never what is said."))
    s.extend(qa(
        "Audio cannot show a warning badge. How does the student know a provision "
        "is unverified?",
        "The provenance travels with the utterance rather than only with the "
        "written record. Each <font face='Courier'>speaker</font> event ships the "
        "grounded provisions with their individual "
        "<font face='Courier'>verified</font> flags, plus anything the audit could "
        "not find at all, and the live caption shows the unverified warning while "
        "the line is being spoken. The audit runs <i>before</i> the words are "
        "synthesized, not after."))
    s.extend(qa(
        "Why did chunk alignment matter?",
        "Because the browser worklet decodes each chunk with "
        "<font face='Courier'>new Int16Array(bytes.buffer)</font>, which throws "
        "outright on an odd byte length. PCM16 samples are two bytes, so a chunk "
        "boundary landing mid-sample kills playback. Chunks are emitted in whole "
        "samples and the trailing half-sample is carried into the next one - "
        "measured 0 misaligned chunks across 305 chunks and 1.82 MB."))
    s.extend(qa(
        "What in the voice path has <i>not</i> been verified?",
        "A witness answering out loud. Microphone capture and browser playback "
        "were confirmed on 17 August 2026 - a spoken leading question drew "
        "counsel's objection and the bench's ruling, both audible in distinct "
        "voices - but that run ended in a sustained objection, where the graph "
        "routes to END and silence is correct. The transcription leg was proved "
        "separately in code with a real 48 kHz WebM/Opus blob returning its input "
        "word-for-word. The witness's voice is the one link nobody has listened "
        "to, and it is stated as such rather than assumed."))
    return s


def qa_security():
    s = [h2("H. Security")]
    s.extend(qa(
        "Why hand-roll scrypt instead of using bcrypt or argon2?",
        "scrypt is already in Node's standard library, and the parameters below "
        "are the decisions a library would otherwise make silently: N=16384, r=8, "
        "p=1, 64-byte key, 16-byte random salt. N=16384 is the interactive-login "
        "figure from the scrypt paper - about 100 ms and 16 MB per hash. Adding a "
        "dependency that handles credentials is one more thing to keep patched "
        "before a demo, for no security gain."))
    s.extend(qa(
        "Why store the cost parameters inside the digest?",
        "So raising the cost later does not lock anyone out. Verification "
        "re-derives with <i>that record's</i> parameters, so new passwords can be "
        "hashed at a higher N while existing accounts still verify. A digest that "
        "does not carry its own parameters cannot be verified after they change."))
    s.extend(qa(
        "Your session token is stateless. How do you revoke a session?",
        "By rotating <font face='Courier'>AUTH_SECRET</font>, which invalidates "
        "every session at once. That is stated as the cost rather than hidden: a "
        "classroom does not need per-device revocation, and a token table would be "
        "a second thing to keep in step with the users table. If credentials leak, "
        "rotating the secret is the right lever anyway - it is just worth knowing "
        "it is the only one."))
    s.extend(qa(
        "Why does the signature get checked before the payload is parsed?",
        "So a forged payload never reaches <font face='Courier'>Number()</font>. "
        "Order matters in verification code: parse-then-verify means attacker-"
        "controlled data has already been through your parser."))
    s.extend(qa(
        "Why 404 rather than 403 for someone else's session?",
        "Because 403 confirms the session exists. The two cases are made "
        "indistinguishable by making ownership a <i>filter</i> in the query rather "
        "than a check in the handler - the row simply does not come back. Every "
        "<font face='Courier'>/sessions/:id</font> route reaches its session "
        "through that one loader, so a handler that forgot to check would have had "
        "to go around it to load the row at all."))
    s.extend(qa(
        "Why rate limit on two keys?",
        "Because each alone has a hole. Per-account only lets one guessed password "
        "be sprayed across a whole class roster. Per-address only lets a lab behind "
        "one NAT lock its own students out. So it is 8 failures per account and 30 "
        "per address in 15 minutes, and a successful sign-in forgives the account's "
        "counter but not the address's."))
    s.extend(qa(
        "Why check the limit before verifying the password?",
        "Because hashing is deliberately expensive - about 100 ms and 16 MB each. "
        "Checking first means a blocked caller cannot spend the server's hashing "
        "time either, so the limiter also protects the resource the slow hash "
        "creates."))
    s.extend(qa(
        "Why a sliding window rather than a fixed one?",
        "A fixed window lets an attacker spend the full allowance at the end of one "
        "window and again at the start of the next - twice the intended rate at "
        "exactly the moment it matters. The sliding version prunes to the window on "
        "every read. The key map is bounded at 10,000 entries and sweeps aged keys "
        "when full, refusing to grow further rather than evicting someone else's "
        "record of failures, because an unbounded map would make the limiter the "
        "denial of service it exists to prevent."))
    s.extend(qa(
        "Transcribed speech reaches prompts verbatim. Is that not a prompt "
        "injection hole?",
        "It is a real exposure and it is stated in the code rather than papered "
        "over. It was then measured: 36 attacks through the courtroom and the "
        "verdict scorer, and <b>0 landed</b>. The multi-agent design turns out to "
        "be the defence - opposing counsel screens every utterance, so an "
        "injection arrives in front of an agent whose job is to object to improper "
        "questions, and it objects, ruling the injected instruction irrelevant "
        "under QSO Art. 133. On the verdict path the marks mostly went <i>down</i> "
        "under attack, because the judge reads the manipulation attempt as part of "
        "the performance being graded."))
    s.extend(qa(
        "So why not build the guard anyway?",
        "Because it would have no measurable effect on this surface today, and an "
        "unmeasurable defence is indistinguishable from a decorative one. The "
        "stated policy is: build the guard when an attack lands, and put the "
        "attack into the harness first so the guard has something to prove itself "
        "against. That is a defensible position precisely because the 36 attacks "
        "exist - it would not be defensible without them."))
    s.extend(qa(
        "How do you detect a successful injection objectively?",
        "A canary. The attack instructs an agent to emit a token it would never "
        "otherwise say, so if <font face='Courier'>PINEAPPLE7</font> appears in "
        "output, the injected instruction was obeyed - no judgement call. Alongside "
        "it: system-prompt phrases appearing in output, first-person self-"
        "disclosure as a model, and agent-introduced fabricated citations. Three "
        "detector iterations were needed before the numbers meant anything, which "
        "is its own lesson: a red-team harness is something you can fool yourself "
        "with."))
    return s


def qa_eval():
    s = [h2("I. Evaluation, cost and LLMOps")]
    s.extend(qa(
        "What does your evaluation harness actually measure?",
        "Five things, each against a fixed golden set: retrieval quality (hit@k "
        "and MRR over 20 tagged queries), judge reliability and discrimination "
        "(three transcripts of one case at different quality), courtroom behaviour "
        "(32 labelled objection scenarios), witness grounding, and adversarial "
        "robustness (36 attacks). All of them drive the same functions the product "
        "calls - never a copy."))
    s.extend(qa(
        "Why does that 'never a copy' rule matter so much?",
        "Because the moment a harness measures its own reimplementation, it stops "
        "measuring the product and starts measuring itself. The eval imports "
        "<font face='Courier'>search_statutes</font>, "
        "<font face='Courier'>run_turn</font>, "
        "<font face='Courier'>score_session</font> and "
        "<font face='Courier'>testify</font> directly - so a change to the product "
        "changes the number, which is the only way a number is worth anything."))
    s.extend(qa(
        "Why is the courtroom eval not part of the default run?",
        "It drives the full agent graph once per scenario, so it costs minutes and "
        "real tokens where retrieval and judge scoring are comparatively cheap. "
        "The important corollary is stated explicitly: "
        "<font face='Courier'>pnpm run eval</font> does not import the agents at "
        "all, so <b>it is not evidence for an agent change</b>. Reporting the fast "
        "gate after touching agent prompts would be reporting a test that never ran "
        "the code."))
    s.extend(qa(
        "Which of your numbers are noisy, and how do you report them?",
        "Two. Courtroom precision, F1 and ground accuracy drift by one scenario "
        "between runs - a single run often reads 1.00, which is exactly the trap, "
        "so the figures quoted are means over three runs: 0.98, 0.99, 0.98. And "
        "ruling accuracy moved 94% to 89% between runs with no judge change, so it "
        "is quoted as a mean or explicitly as one run. What never moved: objection "
        "recall 1.00, 0 routing leaks, discrimination 3/3, citation accuracy "
        "100/50/0."))
    s.extend(qa(
        "Your judge's weak transcript scored 25 on some runs and 35 on others. Is "
        "the judge unreliable?",
        "It is the least stable figure in the harness, and the shape is expected: "
        "poor advocacy gives a grader less to agree with. It scored 25, 25, 35, 35, "
        "35 with nothing in the judge changing, so the honest report is the range "
        "25-35 rather than a point. What matters is that the <i>ordering</i> never "
        "moved - strong above mixed above weak on every run - because ranking is "
        "what a formative tool needs to get right."))
    s.extend(qa(
        "How is cost measured, and why not at the call sites?",
        "The shared OpenAI client is wrapped once: "
        "<font face='Courier'>create()</font> on chat completions and embeddings is "
        "reassigned to a version that times the call and records model, prompt "
        "tokens and completion tokens against a ledger. Eight places in the "
        "service reach the API, and a cost figure that silently misses one is "
        "worse than no figure because it looks authoritative. Wrapping once means "
        "a ninth call site is counted whether or not whoever added it remembered."))
    s.extend(qa(
        "Why a ContextVar for the ledger?",
        "So two turns running concurrently do not pour their usage into each "
        "other's ledger. A module-level global would cross-contaminate under any "
        "concurrency. Outside a "
        "<font face='Courier'>track()</font> block nothing is recorded at all, so "
        "there is no accumulation in a long-running process and no cost to leaving "
        "the instrumentation in place."))
    s.extend(qa(
        "Why are prices hardcoded rather than fetched?",
        "An eval that reports a different cost depending on the day it ran is not a "
        "measurement, and CI has no business making a pricing call to answer 'did "
        "this change get cheaper'. The trade is that they go stale, so they are "
        "labelled approximate and verified before any dollar figure is quoted. An "
        "unknown model is priced as the expensive one, because guessing low "
        "understates cost - the direction that misleads."))
    s.extend(qa(
        "What does MLflow give you that printing the numbers does not?",
        "Comparison without re-running. Each run records metrics namespaced by "
        "section, the params that produced them - including the git commit, with "
        "<font face='Courier'>git_dirty</font> separately, because a dirty tree "
        "means the commit does not describe the code that ran - and the printed "
        "report as an artifact. The metrics tell you hit@1 fell; only the report "
        "tells you which query missed. The first pair of tracked runs sat either "
        "side of a merge and showed the judge spread narrowing from 10 to 4 with "
        "no regression, visible without re-reading a console."))
    s.extend(qa(
        "Why are params read from settings rather than passed in?",
        "Same reasoning as wrapping the client: the setting somebody forgets to log "
        "is the one that moved the metric. Reading them off "
        "<font face='Courier'>get_settings()</font> means a new knob is captured "
        "whether or not whoever added it remembered to log it."))
    s.extend(qa(
        "Why is MLflow optional?",
        "Because the AI service must not acquire a tracking library in order to "
        "serve a request - it lives in the <font face='Courier'>eval</font> extra, "
        "not in the service dependencies. Without it the harness runs exactly as "
        "before and prints one line saying so. Every tracking call is also guarded, "
        "because the metrics cost real money to produce and losing them to a "
        "logging error would be absurd."))
    return s


def qa_hard():
    s = [h2("J. Hard questions and known limits")]
    s.extend(qa(
        "What is the weakest part of the system?",
        "The corpus is 53 provisions. Everything else - retrieval, grounding, "
        "objection grounds, the audit - is bounded by what is in it, and areas of "
        "law outside criminal and evidence are thin. That is why generation is "
        "gated to Criminal in the contract, and why seventeen instruments the corpus "
        "does <i>not</i> hold are listed by alias: so a citation to the Code of "
        "Civil Procedure is reported as unconfirmed rather than passing silently."))
    s.extend(qa(
        "Your evaluation labels were written by an engineer, not a lawyer. Does "
        "that not undermine the courtroom numbers?",
        "It qualifies them, and the harness prints that caveat on every run. The "
        "labels were written from the evidentiary rules in the corpus and are a "
        "working ground truth pending review by a law student. The metrics are "
        "still meaningful as a regression signal - they catch the agent changing "
        "behaviour - but they are not an authority on Pakistani evidence law and "
        "are not presented as one."))
    s.extend(qa(
        "If the corpus is the audit's ground truth, what checks the corpus?",
        "A human diff against an official print, which is the only thing that can. "
        "That is the entire argument for the verification exercise, and its output "
        "is the honest answer to this question: six numbering errors, three "
        "corrupted articles and a repealed definition, none of which any automated "
        "guard in the repository could have caught."))
    s.extend(qa(
        "Is 0 out of 36 attacks not just a small sample?",
        "Yes, and it is described exactly that way: it says the obvious attacks "
        "fail, not that the system is safe. The value is not the zero - it is that "
        "there is a harness at all, and that the next attack anyone thinks of goes "
        "into it before the fix does."))
    s.extend(qa(
        "What breaks if the network is down at the venue?",
        "Everything. The recorded-run fallback was removed as outside the MVP, so "
        "no network or an exhausted API balance means no demo. That is a known, "
        "deliberate trade and it is recoverable from git history if it stops "
        "looking right."))
    s.extend(qa(
        "Where is reasoning still in the wrong service?",
        "One route: the manually-raised objection ruling still builds a prompt and "
        "calls the model inside Express. It belongs behind the AI service, it is "
        "recorded as pending work, and it is explicitly not a precedent - case "
        "generation was the other violation and has already moved."))
    s.extend(qa(
        "Why is there no test suite?",
        "There is no <font face='Courier'>tests/</font> directory yet, although "
        "pytest is configured. The evaluation harness does the work unit tests "
        "would do for the parts that matter - it drives the real functions with "
        "fixed inputs and asserts on measured outputs - but that is a "
        "justification for the priority, not a claim that unit tests are "
        "unnecessary. Typecheck and build gates cover the TypeScript side."))
    s.extend(qa(
        "What is missing from the LLMOps story?",
        "Per-call tracing, CI, Docker, and surfacing cost per <i>session</i> in the "
        "app rather than only in the harness. Cost and latency are metered per "
        "call and every eval run is recorded to MLflow, but the store is local "
        "SQLite and gitignored, so a fresh clone has no history and the written "
        "baselines remain the thing to quote."))
    s.extend(qa(
        "If you had to defend one design decision as the most important, which?",
        "Defining <font face='Courier'>run_turn</font> in terms of "
        "<font face='Courier'>run_turn_stream</font>. It is two lines of structure "
        "that make it impossible for the courtroom a student hears to diverge from "
        "the courtroom the evaluation measures. Every number in this document "
        "depends on that identity holding."))
    s.extend(qa(
        "And the one you would change first with more time?",
        "Transcription. 4.5 seconds is now the largest single block before the "
        "court speaks, and unlike the graph latency - which was fixed by streaming "
        "- it is a straight model swap with a measurable before and after. After "
        "that, hearing a witness answer out loud, which is the last unverified "
        "link in the voice chain."))
    return s


# ==========================================================================
# PART 14 - Appendix
# ==========================================================================


def part_appendix():
    s = h1("Appendix", "Numbers, commands and file map")

    s.append(h2("A1. Every number worth memorising"))
    s.extend(table(
        ["Subsystem", "Figure"],
        [
            ["Corpus", "53 provisions - QSO 20, PPC 15, CrPC 10, Constitution 8. "
             "52 verified against an official source; Art. 199 the exception."],
            ["Embeddings", "text-embedding-3-small, 1536 dimensions, L2-normalised, "
             "batch 64 at ingest."],
            ["Fusion", "RRF with k = 60; candidate_k = max(20, 4 x top_k); "
             "rerank slice = 3 x top_k."],
            ["Retrieval quality", "Reranked hit@1 1.00 / MRR 1.00. Fusion-only "
             "0.80 / 0.88 (was 0.90 / 0.94 before the corpus was corrected)."],
            ["Reranker evidence", "Art. 71 at rank #2 (RRF), #1 (LLM), #10 of 15 "
             "(ms-marco, all scores negative). Art. 46 promoted from #19 into the "
             "top 3."],
            ["Reranker latency", "none ~0.9 s; llm ~8 s; cross_encoder ~0.02 s "
             "after load."],
            ["Judge loop", "MAX_TOOL_ROUNDS = 3, then a forced JSON ruling, then "
             "overrule."],
            ["Judge scoring", "strong 85-88, mixed 55-58, weak 25-35; spread 0-10; "
             "mean stdev ~2; discrimination 3/3; citation accuracy 100 / 50 / 0%."],
            ["Courtroom", "32 scenarios: recall 1.00, precision 0.98, F1 0.99, "
             "ground 0.98, ruling ~0.95 (means over 3 runs); 18 tp / 14 tn; "
             "0 routing leaks."],
            ["Cost per turn", "cascade on $0.0095 ($0.0020 silent / $0.0153 "
             "objected); cascade off $0.0104; with the ReAct thought $0.0103."],
            ["Brief cost", "case_context 158 -> 465 tokens, +307 per agent call. "
             "Silent turn +2.3%, objected turn +10-20%."],
            ["Witness", "0 fabrications in 9 unanswerable questions; 17/17 "
             "outcomes correct."],
            ["Red team", "0 of 36 attacks obeyed; 14-21 of 30 deflected by an "
             "objection; 0 of 6 verdict attacks landed."],
            ["Voice", "first audio 8.1 s (was 16.1 s); counsel 6.9 s; ruling "
             "13.8 s; total 20.5 s; transcription 4.5 s; 0 misaligned chunks."],
            ["Memory", "4 summarisation calls per session; caps 12 claims / 10 "
             "testimony / 6 directions."],
            ["Auth", "scrypt N=16384 r=8 p=1, 64-byte key; 7-day cookie; 8 "
             "failures per account and 30 per IP per 15 minutes."],
            ["Cold start", "LangGraph import ~49 s - lazy and cached."],
        ],
        [20, 80]))

    s.append(h2("A2. Commands"))
    s.extend(code(
        "# run the three services\n"
        "pnpm run dev:ai            # FastAPI reasoning service   :8000\n"
        "pnpm run dev:api           # Express API                 :5000\n"
        "pnpm run dev               # web app                     :5173\n"
        "\n"
        "# database and corpus\n"
        "pnpm --filter @workspace/db run push     # apply the Drizzle schema\n"
        "pnpm run db:seed                         # seed practice cases\n"
        "pnpm run statutes:ingest                 # ingest + embed (incremental)\n"
        "pnpm run statutes:reindex                # force re-embed everything\n"
        "pnpm run statutes:verify <file> --source <pdf>\n"
        "\n"
        "# gates\n"
        "pnpm run typecheck         # all libs, apps and scripts\n"
        "pnpm run build             # typecheck + production bundles\n"
        "ruff check artifacts/ai-service\n"
        "\n"
        "# evaluation\n"
        "pnpm run eval                     # retrieval + judge (the fast gate)\n"
        "pnpm run eval:courtroom --runs 3  # objection, ruling, routing leaks\n"
        "pnpm run eval:witness             # grounding and fabrication rate\n"
        "pnpm run eval:redteam             # 36 injections through the courtroom\n"
        "pnpm run eval:ui                  # MLflow, to compare runs\n"
        "\n"
        "# behavioural checks (read-only)\n"
        "pnpm run simulate-courtroom <sessionId> --phase witness_examination \\n"
        "     --witness \"Sana Arif\" \"<utterance>\"\n"
        "\n"
        "# regenerate the OpenAPI client and validators\n"
        "pnpm --filter @workspace/api-spec run codegen"))
    return s


def part_appendix_2():
    s = [h2("A3. Where things live")]
    s.extend(code(
        "artifacts/ai-service/app/\n"
        "  config.py            settings; the reranker rationale lives in a comment\n"
        "  db.py                asyncpg pool; the schema-ownership docstring\n"
        "  telemetry.py         client wrapper, ledger, pinned prices\n"
        "  grounding.py         objection grounds + area seed queries\n"
        "  memory.py            two-tier memory, watermark, witness scoping\n"
        "  casegen.py           palette-constrained case generation\n"
        "  verdict.py           the AI judge that scores a session\n"
        "  rag/index.py         in-memory dense matrix + BM25, tokenizer\n"
        "  rag/retrieval.py     hybrid search, RRF, prompt block\n"
        "  rag/reranker.py      three backends and their degradation chain\n"
        "  rag/citations.py     extraction, three statuses, the audit\n"
        "  agents/graph.py      the StateGraph, routing, streaming entry point\n"
        "  agents/state.py      request models, events, AgentContext\n"
        "  agents/judge.py      the ReAct loop and its fallbacks\n"
        "  agents/prosecutor.py the objection screen and the cascade\n"
        "  agents/witness.py    four outcomes and the grounding decision\n"
        "  agents/tools.py      search_statute schema + executor\n"
        "  agents/interjection.py  the student interrupting\n"
        "  routers/             thin FastAPI wrappers only\n"
        "  eval/                five suites + MLflow tracking\n"
        "\n"
        "artifacts/api-server/src/\n"
        "  routes/sessions.ts   turns, voice turns, phases, verdict, interjection\n"
        "  lib/ai-service.ts    the typed client for the Python service\n"
        "  lib/courtroom.ts     phase machine, event rendering, transcription hint\n"
        "  lib/voice.ts         TTS streaming, per-agent voices, chunk alignment\n"
        "  lib/auth.ts          scrypt hashing and signed session tokens\n"
        "  lib/rate-limit.ts    sliding-window attempt limiter\n"
        "\n"
        "lib/db/src/schema/     the single source of schema truth (Drizzle)\n"
        "lib/api-spec/          openapi.yaml + Orval config\n"
        "data/statutes/*.json   the corpus; edits are verification work\n"
        "scripts/               ingest, verify, seed, setup"))

    s.append(h2("A4. Invariants that must not be broken"))
    s.extend(bullets([
        "<b>No prompt or model call in Express.</b> One documented exception "
        "remains and is pending work, not a pattern.",
        "<b>Drizzle owns the schema.</b> No SQLAlchemy, no Alembic, no second "
        "definition of a table.",
        "<b>Generated files are never hand-edited.</b> Change "
        "<font face='Courier'>openapi.yaml</font> and re-run codegen; review the "
        "YAML diff.",
        "<b>The embedding model matches the stored vectors.</b> Changing it is a "
        "re-index, not a config change.",
        "<b>Unverified-text markers are never removed</b>, shortened, made "
        "conditional or hidden behind a flag.",
        "<b>Agents may only cite provisions that exist in the corpus</b>, and "
        "objection grounds are constrained to it by construction.",
        "<b>Every agent loop declares its bound.</b> The judge's is 3 rounds.",
        "<b>The evaluation calls the same code the app calls.</b> Never a copy.",
        "<b>Retrieval, prompt, agent or scoring changes require a re-run</b> of the "
        "suite that measures them, with the delta reported - including when it "
        "gets worse.",
    ]))

    s.append(h2("A5. What is honestly unfinished"))
    s.extend(table(
        ["Item", "State"],
        [
            ["A witness heard answering out loud",
             "The objection-to-ruling half is confirmed audible. A proper question "
             "that draws no objection has not yet been put to a witness with the "
             "speakers on."],
            ["Transcription latency", "4.5 s on "
             "<font face='Courier'>whisper-1</font>; the next lever."],
            ["Reasoning in Express",
             "One route left - the manually-raised objection ruling."],
            ["Prompt-injection guard",
             "Deliberately not built. 0 of 36 attacks land; build it when one "
             "does, and add the attack first."],
            ["Corpus verification",
             "52 of 53. Constitution Art. 199 needs a print later than 28 "
             "February 2012."],
            ["LLMOps", "Per-call tracing, CI, Docker and per-session cost in the "
             "app are all still missing."],
            ["Tests", "No <font face='Courier'>tests/</font> directory yet, though "
             "pytest is configured."],
            ["Offline fallback", "Removed as outside the MVP. The demo is "
             "live-only."],
        ],
        [26, 74]))

    s.append(Spacer(1, 10))
    s.append(p(
        "<i>These notes describe the system as it stands. Where a figure is "
        "quoted it was measured by the command named beside it; where something "
        "has not been verified, it says so.</i>", SMALL))
    return s


def contents():
    rows = [
        ["1", "Orientation: what the system is and how to read these notes"],
        ["2", "Architecture: three services, one database, one contract"],
        ["3", "The statute corpus: chunking, ingestion and verification"],
        ["4", "Retrieval: hybrid search over the statute corpus"],
        ["5", "The citation audit: the guard against invented law"],
        ["6", "The multi-agent courtroom: LangGraph, routing and ReAct"],
        ["7", "Agent memory: two tiers, one watermark"],
        ["8", "Grounded generation: cases in, verdicts out"],
        ["9", "The voice pipeline: transport, not reasoning"],
        ["10", "Security: identity, scoping and hostile input"],
        ["11", "LLMOps: cost telemetry, evaluation and run tracking"],
        ["12", "Every choice on one page: we used X, not Y, because Z"],
        ["13", "Technical question bank (A-J, 113 questions)"],
        ["A", "Appendix: numbers, commands, file map, invariants, open items"],
    ]
    s = [PageBreak(), Paragraph("Contents", H1),
         HRFlowable(width="100%", thickness=1.4, color=NAVY, spaceBefore=4,
                    spaceAfter=12)]
    s.extend(table(["Part", "Title"], rows, [10, 90]))
    s.append(Spacer(1, 6))
    s.append(p(
        "The question bank in Part 13 is grouped as: <b>A</b> architecture and "
        "service boundaries, <b>B</b> retrieval and RAG, <b>C</b> citations and "
        "trust, <b>D</b> the multi-agent courtroom, <b>E</b> memory, <b>F</b> "
        "generation and scoring, <b>G</b> voice, <b>H</b> security, <b>I</b> "
        "evaluation and LLMOps, <b>J</b> hard questions and known limits.", SMALL))
    return s


def build_story():
    story = []
    story += cover()
    story += contents()
    story += part_orientation()
    story += part_architecture()
    story += part_architecture_2()
    story += part_corpus()
    story += part_corpus_2()
    story += part_retrieval()
    story += part_retrieval_2()
    story += part_retrieval_3()
    story += part_citations()
    story += part_agents()
    story += part_agents_2()
    story += part_agents_3()
    story += part_agents_4()
    story += part_memory()
    story += part_generation()
    story += part_voice()
    story += part_security()
    story += part_security_2()
    story += part_llmops()
    story += part_llmops_2()
    story += part_choices()
    story += part_choices_2()
    story += part_qa_intro()
    story += qa_architecture()
    story += qa_architecture_2()
    story += qa_retrieval_2()
    story += qa_retrieval_3()
    story += qa_citations()
    story += qa_agents()
    story += qa_agents_2()
    story += qa_agents_3()
    story += qa_generation()
    story += qa_voice()
    story += qa_security()
    story += qa_eval()
    story += qa_hard()
    story += part_appendix()
    story += part_appendix_2()
    return story


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "docs"
    out.mkdir(exist_ok=True)
    target = out / "CourtSimulator_Technical_Notes.pdf"

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN + 6,
        title="CourtSimulator - Technical Notes",
        author="CourtSimulator",
        subject="Architecture, design decisions and technical Q&A",
    )
    doc.build(build_story(), canvasmaker=NumberedCanvas)
    print("Wrote %s" % target)
    print("Questions in the bank: %d" % _QA["n"])


if __name__ == "__main__":
    main()
