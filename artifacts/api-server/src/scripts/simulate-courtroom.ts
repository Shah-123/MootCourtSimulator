/**
 * Drives one student utterance through the multi-agent courtroom graph and
 * prints the full sequence of agent events — the objection opposing counsel
 * chose to raise, the judge's ReAct trace as it reads statute before ruling,
 * and the witness answer if the question survived. Read-only: it simulates a
 * turn without persisting anything, so it is safe to run repeatedly for a demo
 * or as the driver for the evaluation harness.
 *
 *   pnpm run simulate-courtroom <sessionId> "<what counsel says>"
 *   pnpm run simulate-courtroom 8 --phase witness_examination --witness "Constable Imran" \
 *     "You clearly saw my client stab the victim, didn't you?"
 *
 * The multi-agent service (artifacts/ai-service) must be running.
 */
import { eq } from "drizzle-orm";
import {
  db,
  pool,
  casesTable,
  sessionsTable,
  turnsTable,
  type Turn,
} from "@workspace/db";
import {
  getSessionMemory,
  runCourtroomTurn,
  type CourtEvent,
} from "../lib/ai-service";
import {
  courtroomCaseBrief,
  isSessionPhase,
  isStudentSide,
} from "../lib/courtroom";

const args = process.argv.slice(2);

function flag(name: string): string | null {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? (args[i + 1] ?? null) : null;
}

const phaseOverride = flag("phase");
const witnessOverride = flag("witness");
const flagValues = new Set([phaseOverride, witnessOverride].filter(Boolean));
const positional = args.filter(
  (arg) => !arg.startsWith("--") && !flagValues.has(arg),
);
const sessionId = Number(positional[0]);
const utterance = positional.slice(1).join(" ");

if (!Number.isInteger(sessionId) || !utterance) {
  console.error(
    'Usage: pnpm run simulate-courtroom <sessionId> [--phase <phase>] ' +
      '[--witness "<name>"] "<utterance>"',
  );
  process.exit(1);
}

const SPEAKER_LABEL: Record<string, string> = {
  opposing_counsel: "OPPOSING COUNSEL",
  judge: "JUDGE",
  witness: "WITNESS",
};

function printEvent(event: CourtEvent, index: number): void {
  const tag = [event.kind, event.ground, event.citation]
    .filter(Boolean)
    .join(" · ");
  console.log(
    `\n  [${index + 1}] ${SPEAKER_LABEL[event.speaker] ?? event.speaker}` +
      (tag ? `  (${tag})` : ""),
  );

  if (event.reasoning.length > 0) {
    console.log("      ReAct trace:");
    event.reasoning.forEach((step, i) => {
      // Thought first: it is the half of Thought-Action-Observation that says
      // *why* the bench went looking, and printing only the call and its hits
      // hid an empty thought field for as long as it existed.
      if (step.thought) console.log(`        ${i + 1}. ${step.thought}`);
      console.log(`        ${step.thought ? "  " : `${i + 1}. `}${step.action}`);
      console.log(`           → ${step.observation}`);
    });
  }

  console.log(`      "${event.transcript}"`);

  if (event.grounded.length > 0) {
    const cites = event.grounded.map((g) => g.citation).join(", ");
    console.log(`      grounded in: ${cites}`);
  }
}

async function main() {
  const [session] = await db
    .select()
    .from(sessionsTable)
    .where(eq(sessionsTable.id, sessionId));
  if (!session) throw new Error(`Session ${sessionId} not found`);

  const [courtCase] = await db
    .select()
    .from(casesTable)
    .where(eq(casesTable.id, session.caseId));
  if (!courtCase) throw new Error("Case not found for session");

  const turns: Turn[] = await db
    .select()
    .from(turnsTable)
    .where(eq(turnsTable.sessionId, sessionId))
    .orderBy(turnsTable.createdAt);

  const phase = phaseOverride ?? session.phase;
  if (!isSessionPhase(phase)) throw new Error(`Invalid phase: ${phase}`);
  if (!isStudentSide(session.studentSide)) {
    throw new Error(`Invalid student side: ${session.studentSide}`);
  }

  // Active witness: an explicit flag wins; otherwise the most recent witness to
  // take the stand in this phase, matching how the voice endpoint decides.
  const activeWitness =
    witnessOverride ??
    [...turns].reverse().find((t) => t.speaker === "witness" && t.phase === phase)
      ?.witnessName ??
    null;

  const workingMemory = turns
    .filter((t) => t.phase === phase)
    .map((t) => ({
      speaker: t.speaker,
      witnessName: t.witnessName,
      transcript: t.transcript,
    }));

  console.log(
    `\nSESSION ${sessionId} · phase ${phase} · student = ${session.studentSide}` +
      (activeWitness ? ` · witness on stand: ${activeWitness}` : ""),
  );
  // Both tiers of memory, stated before the turn rather than inferred from
  // it. The agents read the earlier-phase recollection through the service,
  // so a turn that ignores what the student conceded two phases ago is only
  // diagnosable if you can see whether the recollection reached them at all.
  // The retired `simulate-turn` script was the only thing that showed it.
  const memory = await getSessionMemory(session.id, phase).catch(() => null);
  console.log(
    `long-term memory: ${
      memory?.summary ? `${memory.studentClaims.length} prior claims` : "none"
    } · working memory: ${workingMemory.length} turns in this phase`,
  );

  console.log(`\nSTUDENT: "${utterance}"`);

  const result = await runCourtroomTurn({
    sessionId: session.id,
    phase,
    studentSide: session.studentSide,
    activeWitness,
    case: courtroomCaseBrief(courtCase),
    utterance,
    workingMemory,
  });

  console.log(
    `\n── ${result.events.length} agent event(s) · supervisor routed to: ` +
      `${result.primarySpeaker ?? "(none)"} ──`,
  );
  result.events.forEach(printEvent);

  const audit = result.citationAudit;
  console.log(
    `\n  citation audit: ${audit.verified}/${audit.total} verified` +
      (audit.accuracy !== null ? ` (${audit.accuracy}%)` : "") +
      `, ${audit.hallucinated} fabricated`,
  );
  if (audit.hallucinated > 0) {
    const bad = audit.checks
      .filter((c) => c.status === "not_found")
      .map((c) => c.raw)
      .join(", ");
    console.log(`  ⚠ an agent cited provisions absent from the corpus: ${bad}`);
  }
  console.log();
}

main()
  .catch((err) => {
    console.error("Simulation failed:", err instanceof Error ? err.message : err);
    process.exitCode = 1;
  })
  .finally(() => pool.end());
