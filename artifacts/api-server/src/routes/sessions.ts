import { Router, type IRouter } from "express";
import { and, eq, desc } from "drizzle-orm";
import {
  db,
  casesTable,
  sessionsTable,
  turnsTable,
  verdictsTable,
  type Session,
  type Turn,
  type Case,
  type Verdict,
} from "@workspace/db";
import {
  ListSessionsResponse,
  CreateSessionBody,
  CreateSessionResponse,
  GetSessionParams,
  GetSessionResponse,
  SendSessionVoiceTurnParams,
  SendSessionVoiceTurnBody,
  SendSessionInterjectionParams,
  SendSessionInterjectionBody,
  CallWitnessParams,
  CallWitnessBody,
  CallWitnessResponse,
  AdvanceSessionPhaseParams,
  AdvanceSessionPhaseBody,
  AdvanceSessionPhaseResponse,
  GetSessionVerdictParams,
  GetSessionVerdictResponse,
  RaiseObjectionParams,
  RaiseObjectionBody,
  RaiseObjectionResponse,
  ListObjectionGroundsResponse,
  ListObjectionGroundsQueryParams,
  SendCourtroomTurnParams,
  SendCourtroomTurnBody,
  SendCourtroomTurnResponse,
} from "@workspace/api-zod";
import {
  auditCitations,
  findObjectionGround,
  listObjectionGrounds,
  refreshSessionMemory,
  runCourtroomTurn,
  runInterjection,
  scoreVerdict,
  searchStatutes,
  streamCourtroomTurn,
  type CourtroomStreamMessage,
} from "../lib/ai-service";
import { openai } from "@workspace/integrations-openai-ai-server";
import {
  ensureCompatibleFormat,
  speechToText,
} from "@workspace/integrations-openai-ai-server/audio";
import {
  courtroomCaseBrief,
  isSessionPhase,
  isStudentSide,
  isValidPhaseTransition,
  phasesFor,
  proceedingHasWitnessBox,
  recordEvent,
  speechText,
  transcriptionHint,
} from "../lib/courtroom";
import { streamSpeech } from "../lib/voice";
import { currentUserId, requireUser } from "../middlewares/require-user";

const router: IRouter = Router();

// Every route in this file reads or writes one student's own record of
// proceedings. Declared here rather than at the mount point so a route added
// later is protected by default instead of by remembering.
router.use(requireUser);

/**
 * Loads a session, or null if it does not exist **or is not this student's**.
 *
 * The two cases are deliberately indistinguishable to the caller, which is why
 * ownership is a filter here rather than a check in each handler. Every
 * `/sessions/:id` route reaches its session through this one function, so
 * scoping is enforced in one place; a handler that forgot to check would have
 * to have gone around it to load the row at all. Callers turn null into 404 —
 * not 403, which would confirm the session exists.
 */
async function loadSessionDetail(sessionId: number, userId: number) {
  const [session] = await db
    .select()
    .from(sessionsTable)
    .where(
      and(eq(sessionsTable.id, sessionId), eq(sessionsTable.userId, userId)),
    );

  if (!session) return null;

  const [courtCase] = await db
    .select()
    .from(casesTable)
    .where(eq(casesTable.id, session.caseId));

  const turns = await db
    .select()
    .from(turnsTable)
    .where(eq(turnsTable.sessionId, sessionId))
    .orderBy(turnsTable.createdAt);

  const [verdict] = await db
    .select()
    .from(verdictsTable)
    .where(eq(verdictsTable.sessionId, sessionId));

  return {
    session,
    courtCase: courtCase ?? null,
    turns,
    verdict: verdict ?? null,
  };
}

function serializeSessionDetail(
  session: Session,
  courtCase: Case,
  turns: Turn[],
  verdict: Verdict | null,
) {
  return {
    ...session,
    // Served rather than left for the client to derive. The web app used to
    // build its progress strip by listing the SessionPhase enum, which was only
    // ever correct while every case was a trial.
    phases: phasesFor(courtCase.proceedingType),
    case: courtCase,
    turns,
    verdict,
  };
}

router.get("/sessions", async (req, res): Promise<void> => {
  const rows = await db
    .select({
      id: sessionsTable.id,
      caseId: sessionsTable.caseId,
      caseTitle: casesTable.title,
      areaOfLaw: casesTable.areaOfLaw,
      studentSide: sessionsTable.studentSide,
      phase: sessionsTable.phase,
      status: sessionsTable.status,
      createdAt: sessionsTable.createdAt,
      completedAt: sessionsTable.completedAt,
      overallScore: verdictsTable.overallScore,
    })
    .from(sessionsTable)
    .innerJoin(casesTable, eq(sessionsTable.caseId, casesTable.id))
    .leftJoin(verdictsTable, eq(verdictsTable.sessionId, sessionsTable.id))
    .where(eq(sessionsTable.userId, currentUserId(req)))
    .orderBy(desc(sessionsTable.createdAt));

  res.json(
    ListSessionsResponse.parse(
      rows.map((row) => ({ ...row, overallScore: row.overallScore ?? null })),
    ),
  );
});

router.post("/sessions", async (req, res): Promise<void> => {
  const parsed = CreateSessionBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const [courtCase] = await db
    .select()
    .from(casesTable)
    .where(eq(casesTable.id, parsed.data.caseId));

  if (!courtCase) {
    res.status(400).json({ error: "Case not found" });
    return;
  }

  const [session] = await db
    .insert(sessionsTable)
    .values({
      // Taken from the cookie, never from the request body. A client-supplied
      // owner would let anyone file a session into another student's record.
      userId: currentUserId(req),
      caseId: parsed.data.caseId,
      studentSide: parsed.data.studentSide,
      phase: "opening",
      status: "in_progress",
    })
    .returning();

  res
    .status(201)
    .json(
      CreateSessionResponse.parse(
        serializeSessionDetail(session, courtCase, [], null),
      ),
    );
});

router.get("/sessions/:id", async (req, res): Promise<void> => {
  const params = GetSessionParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const detail = await loadSessionDetail(params.data.id, currentUserId(req));
  if (!detail || !detail.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  res.json(
    GetSessionResponse.parse(
      serializeSessionDetail(
        detail.session,
        detail.courtCase,
        detail.turns,
        detail.verdict,
      ),
    ),
  );
});

router.post("/sessions/:id/voice-turns", async (req, res): Promise<void> => {
  const params = SendSessionVoiceTurnParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const body = SendSessionVoiceTurnBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const detail = await loadSessionDetail(params.data.id, currentUserId(req));
  if (!detail || !detail.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  const { session, courtCase, turns } = detail;

  if (
    session.status === "completed" ||
    session.phase === "verdict" ||
    !isSessionPhase(session.phase) ||
    !isStudentSide(session.studentSide)
  ) {
    res.status(400).json({ error: "Session has already concluded" });
    return;
  }

  const phase = session.phase;

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders?.();

  const send = (payload: unknown): void => {
    if (res.writableEnded || res.destroyed) return;
    res.write(`data: ${JSON.stringify(payload)}\n\n`);
  };

  try {
    const rawAudio = Buffer.from(body.data.audio, "base64");
    const { buffer, format } = await ensureCompatibleFormat(rawAudio);

    // Untrusted input. This transcription reaches agent prompts verbatim and
    // the prompt-injection guard is still pending (#8). Going through the graph
    // does not add a new *kind* of exposure — the text turn endpoint already
    // feeds it to the same agents — but it does put spoken words in front of
    // three of them instead of one.
    const studentTranscript = await speechToText(
      buffer,
      format,
      transcriptionHint(courtCase),
    );
    send({ type: "user_transcript", data: studentTranscript });

    await db.insert(turnsTable).values({
      sessionId: session.id,
      phase,
      speaker: "student",
      witnessName: null,
      transcript: studentTranscript,
    });

    // Active witness: the most recent witness to take the stand in this phase.
    // The graph's supervisor decides from this who may act — there is no
    // persona choice left on this side of the boundary.
    const activeWitness =
      [...turns]
        .reverse()
        .find((t) => t.speaker === "witness" && t.phase === phase)
        ?.witnessName ?? null;

    // Two-tier memory: the current phase is replayed verbatim as working
    // memory, and the AI service loads its own recollection of earlier phases
    // when it assembles the agents' context.
    const workingMemory = turns
      .filter((t) => t.phase === phase)
      .map((t) => ({
        speaker: t.speaker,
        witnessName: t.witnessName,
        transcript: t.transcript,
      }));

    let summary: Extract<CourtroomStreamMessage, { type: "summary" }> | null =
      null;

    // One student utterance can put several agents on the floor in sequence —
    // counsel objects, the bench rules, and only then the witness answers.
    // Each is persisted, announced and spoken *as the graph produces it*, so
    // the objection is already sounding while the judge is still reading
    // statute. Waiting for the whole turn first cost 16.1s of silence.
    for await (const message of streamCourtroomTurn({
      sessionId: session.id,
      phase,
      studentSide: session.studentSide,
      activeWitness,
      case: courtroomCaseBrief(courtCase),
      utterance: studentTranscript,
      workingMemory,
    })) {
      if (message.type === "error") {
        throw new Error(`Courtroom graph failed: ${message.message}`);
      }
      if (message.type === "summary") {
        summary = message;
        continue;
      }
      if (res.writableEnded || res.destroyed) break;

      const { event, objection, citationAudit } = message;

      // On the record before it is spoken: a student who closes the tab
      // halfway through an answer still has the objection and the ruling.
      await db.insert(turnsTable).values({
        sessionId: session.id,
        phase,
        ...recordEvent(event, objection, activeWitness),
      });

      // Grounding is not a guarantee. This utterance was audited before it was
      // spoken, so a provision the agent invented is flagged on the line that
      // carried it rather than at the end of the turn.
      //
      // Only what the *agent* introduced counts. A student can invent
      // "section 899 PPC" and the bench will name it while striking it — the
      // red-team eval caught the raw audit reporting that as the judge
      // fabricating law, which would put a false warning in front of a student
      // at the exact moment the system was working correctly.
      const fabricated =
        citationAudit.agentFabricated ??
        citationAudit.checks
          .filter((check) => check.status === "not_found")
          .map((check) => check.raw);
      if (fabricated.length > 0) {
        req.log.warn(
          { sessionId: session.id, speaker: event.speaker, fabricated },
          "An agent cited provisions absent from the corpus during a voice turn",
        );
      }

      send({
        type: "speaker",
        speaker: event.speaker,
        kind: event.kind,
        witnessName: event.speaker === "witness" ? activeWitness : null,
        ground: event.ground,
        citation: event.citation,
        ruling: event.ruling,
        // Provenance travels with the utterance: audio cannot carry the
        // unverified-text badge the written record shows, so the flags the
        // badge is drawn from are sent alongside it — along with anything the
        // audit could not find in the corpus at all.
        grounded: event.grounded,
        fabricated,
        // The bench's ReAct trace, sent before its ruling is spoken. A student
        // hearing "sustained" should be able to see which provisions the judge
        // read to get there, while it is being said rather than afterwards.
        reasoning: event.reasoning?.length ? event.reasoning : null,
      });

      const spoken = speechText(event);
      send({ type: "transcript", data: spoken });

      try {
        for await (const chunk of streamSpeech(spoken, event.speaker)) {
          if (res.writableEnded || res.destroyed) break;
          send({ type: "audio", data: chunk });
        }
      } catch (err) {
        // A failed synthesis costs this agent its voice, not the turn: the
        // words are already on the record and in the transcript above.
        req.log.error(
          { err, sessionId: session.id, speaker: event.speaker },
          "Speech synthesis failed for an agent event",
        );
      }
    }

    if (summary) {
      req.log.info(
        {
          sessionId: session.id,
          primarySpeaker: summary.primarySpeaker,
          citations: summary.citationAudit.total,
          verified: summary.citationAudit.verified,
          accuracy: summary.citationAudit.accuracy,
        },
        "Voice turn complete",
      );
    }

    send({ done: true });
    res.end();
  } catch (err) {
    req.log.error({ err }, "Voice turn failed");
    try {
      send({ type: "error", error: "Voice turn failed" });
      res.end();
    } catch {
      // response likely already closed
    }
  }
});

/**
 * The student cuts across whoever is speaking. The web app stops playback the
 * moment it hears speech and posts what was said; everything after that is the
 * same machinery a normal turn uses — one judge, one ruling path, one record.
 */
router.post("/sessions/:id/interject", async (req, res): Promise<void> => {
  const params = SendSessionInterjectionParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const body = SendSessionInterjectionBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const detail = await loadSessionDetail(params.data.id, currentUserId(req));
  if (!detail || !detail.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  const { session, courtCase, turns } = detail;

  if (
    session.status === "completed" ||
    session.phase === "verdict" ||
    !isSessionPhase(session.phase) ||
    !isStudentSide(session.studentSide)
  ) {
    res.status(400).json({ error: "Session has already concluded" });
    return;
  }

  const phase = session.phase;

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders?.();

  const send = (payload: unknown): void => {
    if (res.writableEnded || res.destroyed) return;
    res.write(`data: ${JSON.stringify(payload)}\n\n`);
  };

  try {
    const rawAudio = Buffer.from(body.data.audio, "base64");
    const { buffer, format } = await ensureCompatibleFormat(rawAudio);

    // Untrusted input, same as a spoken turn (#8).
    const studentTranscript = await speechToText(
      buffer,
      format,
      transcriptionHint(courtCase),
    );
    send({ type: "user_transcript", data: studentTranscript });

    // On the record before it is classified: an interruption the bench declines
    // to rule on still happened, and the transcript should show that counsel
    // rose.
    const [studentTurn] = await db
      .insert(turnsTable)
      .values({
        sessionId: session.id,
        phase,
        speaker: "student",
        witnessName: null,
        transcript: studentTranscript,
      })
      .returning();

    const activeWitness =
      [...turns]
        .reverse()
        .find((t) => t.speaker === "witness" && t.phase === phase)
        ?.witnessName ?? null;

    const result = await runInterjection({
      sessionId: session.id,
      phase,
      studentSide: session.studentSide,
      activeWitness,
      case: courtroomCaseBrief(courtCase),
      utterance: studentTranscript,
      workingMemory: turns
        .filter((t) => t.phase === phase)
        .map((t) => ({
          speaker: t.speaker,
          witnessName: t.witnessName,
          transcript: t.transcript,
        })),
    });

    if (!result.isObjection || result.events.length === 0) {
      // Nothing to rule on. Say why rather than leaving the student wondering
      // whether the court heard them.
      send({ type: "note", data: result.note ?? "No objection was raised." });
      send({ done: true });
      res.end();
      return;
    }

    // Now that the ground is known, restate the student's line on the record in
    // the form the transcript renders as an objection.
    if (result.objection && studentTurn) {
      await db
        .update(turnsTable)
        .set({
          transcript:
            `[OBJECTION: ${result.objection.label} — ` +
            `${result.objection.citation}] ${studentTranscript}`,
        })
        .where(eq(turnsTable.id, studentTurn.id));
    }

    for (const event of result.events) {
      if (res.writableEnded || res.destroyed) break;

      await db.insert(turnsTable).values({
        sessionId: session.id,
        phase,
        ...recordEvent(event, result.objection, activeWitness),
      });

      send({
        type: "speaker",
        speaker: event.speaker,
        kind: event.kind,
        witnessName: null,
        ground: result.objection?.groundId ?? null,
        citation: event.citation,
        ruling: event.ruling,
        grounded: event.grounded,
        fabricated: result.citationAudit.agentFabricated ?? [],
        reasoning: event.reasoning?.length ? event.reasoning : null,
      });

      const spoken = speechText(event);
      send({ type: "transcript", data: spoken });

      try {
        for await (const chunk of streamSpeech(spoken, event.speaker)) {
          if (res.writableEnded || res.destroyed) break;
          send({ type: "audio", data: chunk });
        }
      } catch (err) {
        req.log.error(
          { err, sessionId: session.id },
          "Speech synthesis failed for a ruling on an interjection",
        );
      }
    }

    send({ done: true });
    res.end();
  } catch (err) {
    req.log.error({ err }, "Interjection failed");
    try {
      send({ type: "error", error: "The Bench could not hear that objection" });
      res.end();
    } catch {
      // response likely already closed
    }
  }
});

router.post("/sessions/:id/call-witness", async (req, res): Promise<void> => {
  const params = CallWitnessParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const body = CallWitnessBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const detail = await loadSessionDetail(params.data.id, currentUserId(req));
  if (!detail || !detail.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  const { session, courtCase } = detail;

  if (!proceedingHasWitnessBox(courtCase.proceedingType)) {
    // Checked before the phase, so the error names the real reason. A writ is
    // heard on affidavits and the record; there is no stand to take.
    res.status(400).json({
      error: "This matter is heard on the record and has no witness box",
    });
    return;
  }

  if (
    session.phase !== "witness_examination" &&
    session.phase !== "cross_examination"
  ) {
    res.status(400).json({
      error:
        "Witnesses can only be called during examination or cross-examination",
    });
    return;
  }

  const witness = courtCase.witnesses.find(
    (w) => w.name === body.data.witnessName,
  );
  if (!witness) {
    res.status(400).json({ error: "Witness not found on this case" });
    return;
  }

  await db.insert(turnsTable).values({
    sessionId: session.id,
    phase: session.phase,
    speaker: "witness",
    witnessName: witness.name,
    transcript: `${witness.name} takes the stand. "${witness.statement}"`,
  });

  const updated = await loadSessionDetail(session.id, currentUserId(req));
  if (!updated || !updated.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  res.json(
    CallWitnessResponse.parse(
      serializeSessionDetail(
        updated.session,
        updated.courtCase,
        updated.turns,
        updated.verdict,
      ),
    ),
  );
});

router.post("/sessions/:id/advance-phase", async (req, res): Promise<void> => {
  const params = AdvanceSessionPhaseParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const body = AdvanceSessionPhaseBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const detail = await loadSessionDetail(params.data.id, currentUserId(req));
  if (!detail || !detail.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  const { session, courtCase, turns } = detail;

  if (
    !isSessionPhase(session.phase) ||
    !isValidPhaseTransition(
      courtCase.proceedingType,
      session.phase,
      body.data.phase,
    )
  ) {
    res.status(400).json({ error: "Invalid phase transition" });
    return;
  }

  if (body.data.phase === "verdict") {
    if (!isStudentSide(session.studentSide)) {
      res.status(400).json({ error: "Session has an invalid student side" });
      return;
    }

    // Scoring lives in the AI service: it audits the student's citations, reads
    // the governing provisions, scores the transcript, and validates its own
    // output — returning an error rather than a verdict it cannot trust.
    let scored;
    try {
      scored = await scoreVerdict({
        title: courtCase.title,
        areaOfLaw: courtCase.areaOfLaw,
        summary: courtCase.summary,
        applicableLaws: courtCase.applicableLaws,
        studentSide: session.studentSide,
        turns: turns.map((t) => ({
          phase: t.phase,
          speaker: t.speaker,
          witnessName: t.witnessName,
          transcript: t.transcript,
        })),
      });
    } catch (err) {
      req.log.error({ err }, "AI verdict scoring failed");
      res.status(500).json({ error: "Failed to generate verdict" });
      return;
    }

    await db.transaction(async (tx) => {
      await tx.insert(verdictsTable).values({
        sessionId: session.id,
        winningSide: scored.winningSide,
        overallScore: scored.overallScore,
        legalReasoningScore: scored.legalReasoningScore,
        persuasivenessScore: scored.persuasivenessScore,
        procedureScore: scored.procedureScore,
        factualCommandScore: scored.factualCommandScore,
        citationAccuracy: scored.citationAccuracy,
        citationChecks: scored.citationChecks,
        judgeRemarks: scored.judgeRemarks,
        strengths: scored.strengths,
        areasForImprovement: scored.areasForImprovement,
      });

      await tx
        .update(sessionsTable)
        .set({
          phase: "verdict",
          status: "completed",
          completedAt: new Date(),
        })
        .where(eq(sessionsTable.id, session.id));
    });
  } else {
    // Fold the phase that just ended into long-term memory before moving on,
    // so agents in the next phase inherit what happened in this one. Once per
    // transition rather than once per turn keeps the cost to four calls a
    // session. Failures here are swallowed and retried on the next transition.
    await refreshSessionMemory(session.id).catch((err) => {
      req.log.warn({ err }, "Memory refresh failed; retrying on next transition");
    });

    await db
      .update(sessionsTable)
      .set({ phase: body.data.phase })
      .where(eq(sessionsTable.id, session.id));
  }

  const updated = await loadSessionDetail(session.id, currentUserId(req));
  if (!updated || !updated.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  res.json(
    AdvanceSessionPhaseResponse.parse(
      serializeSessionDetail(
        updated.session,
        updated.courtCase,
        updated.turns,
        updated.verdict,
      ),
    ),
  );
});

router.get("/sessions/:id/verdict", async (req, res): Promise<void> => {
  const params = GetSessionVerdictParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const [verdict] = await db
    .select()
    .from(verdictsTable)
    .where(eq(verdictsTable.sessionId, params.data.id));

  if (!verdict) {
    res.status(404).json({ error: "Verdict not yet available" });
    return;
  }

  res.json(GetSessionVerdictResponse.parse(verdict));
});

router.get("/objection-grounds", async (req, res): Promise<void> => {
  const query = ListObjectionGroundsQueryParams.safeParse(req.query);
  if (!query.success) {
    res.status(400).json({ error: query.error.message });
    return;
  }

  // An empty array is the right answer for a writ, not an error: every ground
  // the corpus backs is an examination ground and a writ has no witness box.
  res.json(
    ListObjectionGroundsResponse.parse(
      await listObjectionGrounds(query.data.proceedingType),
    ),
  );
});

router.post("/sessions/:id/objection", async (req, res): Promise<void> => {
  const params = RaiseObjectionParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const body = RaiseObjectionBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const detail = await loadSessionDetail(params.data.id, currentUserId(req));
  if (!detail || !detail.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  const { session, courtCase, turns } = detail;

  if (session.status === "completed" || session.phase === "verdict") {
    res.status(400).json({ error: "Session has already concluded" });
    return;
  }

  // Resolved against this session's proceeding rather than the whole catalogue,
  // so a ground that does not exist here cannot be raised by posting its id
  // directly. In a writ that rejects all seven — which is the point, since the
  // UI is not offering any of them either.
  const ground = await findObjectionGround(
    body.data.groundId,
    courtCase.proceedingType,
  );
  if (!ground) {
    res.status(400).json({ error: "Unknown objection ground" });
    return;
  }

  const statement = body.data.statement?.trim() || "Objection, My Lord!";

  const recentTurnsText = turns
    .slice(-5)
    .map(
      (t) =>
        `[${t.speaker}${t.witnessName ? ` (${t.witnessName})` : ""}]: ${t.transcript}`,
    )
    .join("\n");

  // Retrieve neighbouring provisions as well as the one behind the ground:
  // a leading-question objection is decided by reading Art. 137 together with
  // 136 and 138, and the judge should see all three before ruling.
  const related = await searchStatutes(
    `${ground.label}. ${ground.description} ${statement}`,
    { topK: 4, statuteCodes: ["QSO_1984", "CRPC_1898"], rerank: false },
  );

  req.log.info(
    {
      sessionId: session.id,
      groundId: ground.id,
      retrieved: related.results.length,
    },
    "Ruling on objection grounded in retrieved provisions",
  );

  const prompt = `Case Title: ${courtCase.title}
Area of Law: ${courtCase.areaOfLaw}
Current Phase: ${session.phase}

Counsel raised an OBJECTION on the ground of: ${ground.label}
Supporting argument by counsel: "${statement}"

Recent Courtroom Proceedings:
${recentTurnsText || "(No prior transcript available.)"}

THE PROVISION THIS GROUND RESTS ON:
${ground.citation} — ${ground.heading}
${ground.content}

OTHER PROVISIONS RETRIEVED AS RELEVANT:
${related.promptBlock}

Rule on the objection using only the provisions reproduced above. Cite them by
their exact citation strings. Do not cite any article or section that does not
appear above — if the governing provision is not among them, say so plainly
rather than citing from memory.

Respond with strict JSON only, matching this shape:
{
  "ruling": "Sustained" or "Overruled",
  "explanation": string (2-3 sentences explaining the ruling, citing the provisions relied on),
  "impact": string (1 sentence of instruction to counsel or the witness)
}`;

  let parsedRuling: { ruling?: string; explanation?: string; impact?: string };
  try {
    const completion = await openai.chat.completions.create({
      model: process.env.MODEL_TEXT || "gpt-4o",
      max_completion_tokens: 1024,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content:
            "You are an authoritative, learned Pakistani High Court Judge presiding over a moot court. You rule only on the statutory text placed before you.",
        },
        { role: "user", content: prompt },
      ],
    });
    parsedRuling = JSON.parse(
      completion.choices[0]?.message?.content ?? "{}",
    ) as typeof parsedRuling;
  } catch (err) {
    req.log.error({ err }, "Objection ruling failed");
    res.status(500).json({ error: "Failed to rule on objection" });
    return;
  }

  const rulingType =
    parsedRuling.ruling?.toLowerCase() === "sustained"
      ? "SUSTAINED"
      : "OVERRULED";
  const explanation =
    parsedRuling.explanation?.trim() ||
    `The Bench has considered the objection under ${ground.citation}.`;
  const impact =
    parsedRuling.impact?.trim() || "Counsel may proceed with the argument.";

  // The ruling is grounded, but grounding is not a guarantee. Anything the
  // judge cited that is not in the corpus is flagged rather than passed on to
  // the student as law.
  const audit = await auditCitations(`${explanation} ${impact}`);
  if (audit.hallucinated > 0) {
    req.log.warn(
      {
        sessionId: session.id,
        groundId: ground.id,
        fabricated: audit.checks
          .filter((check) => check.status === "not_found")
          .map((check) => check.raw),
      },
      "Judge cited provisions absent from the corpus while ruling on an objection",
    );
  }

  await db.transaction(async (tx) => {
    await tx.insert(turnsTable).values({
      sessionId: session.id,
      phase: session.phase,
      speaker: "student",
      witnessName: null,
      transcript: `[OBJECTION: ${ground.label} — ${ground.citation}] ${statement}`,
    });

    await tx.insert(turnsTable).values({
      sessionId: session.id,
      phase: session.phase,
      speaker: "judge",
      witnessName: null,
      transcript: `[RULING: ${rulingType}] ${explanation} ${impact}`,
    });
  });

  const updated = await loadSessionDetail(session.id, currentUserId(req));
  if (!updated || !updated.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  res.json(
    RaiseObjectionResponse.parse(
      serializeSessionDetail(
        updated.session,
        updated.courtCase,
        updated.turns,
        updated.verdict,
      ),
    ),
  );
});

router.post("/sessions/:id/turn", async (req, res): Promise<void> => {
  const params = SendCourtroomTurnParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const body = SendCourtroomTurnBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const detail = await loadSessionDetail(params.data.id, currentUserId(req));
  if (!detail || !detail.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  const { session, courtCase, turns } = detail;

  if (
    session.status === "completed" ||
    session.phase === "verdict" ||
    !isSessionPhase(session.phase) ||
    !isStudentSide(session.studentSide)
  ) {
    res.status(400).json({ error: "Session has already concluded" });
    return;
  }

  const phase = session.phase;
  const utterance = body.data.utterance.trim();
  if (!utterance) {
    res.status(400).json({ error: "Utterance is empty" });
    return;
  }

  // Active witness: the most recent witness to take the stand in this phase,
  // matching how the voice endpoint decides who is being questioned.
  const activeWitness =
    [...turns]
      .reverse()
      .find((t) => t.speaker === "witness" && t.phase === phase)?.witnessName ??
    null;

  const workingMemory = turns
    .filter((t) => t.phase === phase)
    .map((t) => ({
      speaker: t.speaker,
      witnessName: t.witnessName,
      transcript: t.transcript,
    }));

  // Record the student's turn before reasoning over it, so it is on the record
  // regardless of what the agents do next.
  await db.insert(turnsTable).values({
    sessionId: session.id,
    phase,
    speaker: "student",
    witnessName: null,
    transcript: utterance,
  });

  let result;
  try {
    result = await runCourtroomTurn({
      sessionId: session.id,
      phase,
      studentSide: session.studentSide,
      activeWitness,
      case: courtroomCaseBrief(courtCase),
      utterance,
      workingMemory,
    });
  } catch (err) {
    req.log.error({ err }, "Multi-agent courtroom turn failed");
    res.status(500).json({ error: "Courtroom turn failed" });
    return;
  }

  // Persist each agent event as a turn, in the order the graph produced them,
  // in the same record form the voice turn and the manual objection use.
  if (result.events.length > 0) {
    await db.insert(turnsTable).values(
      result.events.map((event) => ({
        sessionId: session.id,
        phase,
        ...recordEvent(event, result.objection, activeWitness),
      })),
    );
  }

  // Grounding is not a guarantee: anything an agent cited that is not in the
  // corpus is logged rather than passed to the student as settled law.
  if (result.citationAudit.hallucinated > 0) {
    req.log.warn(
      {
        sessionId: session.id,
        fabricated: result.citationAudit.checks
          .filter((check) => check.status === "not_found")
          .map((check) => check.raw),
      },
      "An agent cited provisions absent from the corpus during a turn",
    );
  }

  const updated = await loadSessionDetail(session.id, currentUserId(req));
  if (!updated || !updated.courtCase) {
    res.status(404).json({ error: "Session not found" });
    return;
  }

  res.json(
    SendCourtroomTurnResponse.parse({
      session: serializeSessionDetail(
        updated.session,
        updated.courtCase,
        updated.turns,
        updated.verdict,
      ),
      events: result.events,
      objection: result.objection,
      primarySpeaker: result.primarySpeaker,
      citationAudit: result.citationAudit,
    }),
  );
});

export default router;

