import type { Case, ReasoningStep } from "@workspace/db";
import type { CourtEvent, CourtObjection } from "./ai-service";

export type SessionPhase =
  | "opening"
  | "witness_examination"
  | "cross_examination"
  | "submissions"
  | "bench_questions"
  | "closing"
  | "verdict";

export type ProceedingType = "trial" | "writ";

export type StudentSide = "petitioner" | "respondent";

export type TurnSpeaker = "student" | "judge" | "opposing_counsel" | "witness";

/**
 * The phases each proceeding runs through, in order.
 *
 * This replaced a single `PHASE_ORDER`, which encoded the assumption that
 * every matter is heard the way a criminal trial is. It is not: an Article 199
 * writ is decided on affidavits and argument, so `witness_examination` and
 * `cross_examination` have nothing to run in one, and offering them taught a
 * procedure that does not exist.
 *
 * Express owns this rather than the AI service because advancing a phase is
 * session bookkeeping, not reasoning. The AI service holds the complementary
 * half — who speaks *within* a phase — and the two do not overlap, so there is
 * nothing here for the other side to drift from.
 */
export const PROCEEDING_PHASES: Record<ProceedingType, SessionPhase[]> = {
  trial: [
    "opening",
    "witness_examination",
    "cross_examination",
    "closing",
    "verdict",
  ],
  // No witness box, so no examination phases. `submissions` is the respondent
  // answering the petition; `bench_questions` is the court putting its own
  // questions to counsel, which in a writ is where the matter is actually
  // decided.
  writ: ["opening", "submissions", "bench_questions", "closing", "verdict"],
};

/**
 * Proceedings whose phases include a witness box.
 *
 * Derived rather than declared: a proceeding has witnesses exactly when it has
 * a phase in which someone could be examined, and stating that twice is how the
 * two would eventually disagree.
 */
export function proceedingHasWitnessBox(proceedingType: string): boolean {
  return PROCEEDING_PHASES[proceedingTypeOf(proceedingType)].some(
    (phase) => phase === "witness_examination" || phase === "cross_examination",
  );
}

const ALL_PHASES: SessionPhase[] = Object.values(PROCEEDING_PHASES).flat();

export function isSessionPhase(value: string): value is SessionPhase {
  return ALL_PHASES.includes(value as SessionPhase);
}

export function isProceedingType(value: string): value is ProceedingType {
  return value === "trial" || value === "writ";
}

/**
 * Reads a stored `proceedingType`, falling back to a trial.
 *
 * The column is defaulted, not nullable, so this fallback only fires on a value
 * written by something outside this codebase. Treating that as a trial keeps a
 * malformed row playable instead of 500ing a student mid-session.
 */
export function proceedingTypeOf(value: string): ProceedingType {
  return isProceedingType(value) ? value : "trial";
}

export function phasesFor(proceedingType: string): SessionPhase[] {
  return PROCEEDING_PHASES[proceedingTypeOf(proceedingType)];
}

export function isStudentSide(value: string): value is StudentSide {
  return value === "petitioner" || value === "respondent";
}

/**
 * Whether `next` is the phase that follows `current` in this proceeding.
 *
 * Takes the proceeding rather than consulting one global order: `closing`
 * follows `cross_examination` in a trial and `bench_questions` in a writ, and
 * both are the only legal move from where they stand.
 */
export function isValidPhaseTransition(
  proceedingType: string,
  current: SessionPhase,
  next: SessionPhase,
): boolean {
  const phases = phasesFor(proceedingType);
  const currentIndex = phases.indexOf(current);
  const nextIndex = phases.indexOf(next);
  // indexOf returns -1 for a phase belonging to some other proceeding, and
  // -1 + 1 === 0 would make it a legal opening move. Reject explicitly.
  if (currentIndex === -1 || nextIndex === -1) return false;
  return nextIndex === currentIndex + 1;
}

export function oppositeSide(side: StudentSide): StudentSide {
  return side === "petitioner" ? "respondent" : "petitioner";
}

// `determineRespondingPersona` lived here: a phase→persona rule that decided
// who answers the student. It went with `simulate-turn`, its only caller. It was
// a second copy of the graph's `_route_primary`, and a copy of a routing rule is
// exactly the thing that agrees with the original right up until someone edits
// one of them. The AI service decides who speaks; Express persists what it said.

/**
 * The slice of the case record the courtroom agents receive.
 *
 * Four call sites need this payload — the text turn, the voice turn, an
 * interjection, and the simulate script — and each used to build it by hand. A
 * field added to three of the four is a silent divergence between the text and
 * voice courtrooms, which is exactly what the AI service already guards against
 * by defining `run_turn` in terms of `run_turn_stream`. This is the same guard,
 * one step earlier, on the request.
 */
export function courtroomCaseBrief(courtCase: Case) {
  return {
    title: courtCase.title,
    areaOfLaw: courtCase.areaOfLaw,
    // The agents need this to know whether a witness box exists at all, and
    // which grounds opposing counsel may object on. Without it a writ would be
    // screened for hearsay.
    proceedingType: courtCase.proceedingType,
    summary: courtCase.summary,
    applicableLaws: courtCase.applicableLaws,
    petitionerName: courtCase.petitionerName,
    petitionerRole: courtCase.petitionerRole,
    respondentName: courtCase.respondentName,
    respondentRole: courtCase.respondentRole,
    witnesses: courtCase.witnesses.map((w) => ({
      name: w.name,
      role: w.role,
      statement: w.statement,
    })),
    // Null for library cases and anything generated before the brief existed.
    // The agents render an absent brief identically to the old context string.
    brief: courtCase.brief,
  };
}

/**
 * The proper nouns this case is about, as a spelling hint for transcription.
 *
 * Whisper has no prior for Pakistani names and renders them phonetically —
 * "Mr. Nabi" came back as "Mr. Nobby", which then reaches the agents as the
 * name of a witness who does not exist. Handing it the parties and witnesses
 * off the case file fixes the spelling of exactly the words a moot court says
 * most often.
 *
 * This is a vocabulary hint for the transcriber, not a prompt for a reasoning
 * model, and the names come from the case record rather than from anything the
 * student said.
 */
export function transcriptionHint(courtCase: Case): string {
  const names = [
    courtCase.petitionerName,
    courtCase.respondentName,
    ...courtCase.witnesses.map((w) => w.name),
  ].filter(Boolean);

  return (
    "A Pakistani moot court hearing. Names and terms used: " +
    `${names.join(", ")}. ` +
    "Qanun-e-Shahadat Order, Pakistan Penal Code, Code of Criminal Procedure, " +
    "My Lord, learned counsel, objection, sustained, overruled."
  );
}

/** A graph event rendered for persistence as a turn. */
export interface RecordedEvent {
  speaker: TurnSpeaker;
  witnessName: string | null;
  transcript: string;
  /**
   * The bench's ReAct trace, kept with the ruling it produced.
   *
   * The graph returns this on every ruling, but it used to live only in the
   * turn response, so reloading the page left a ruling with no visible basis.
   * Persisting it means the record can always show what the judge read before
   * it ruled — which is the difference between a ruling that is grounded and
   * one that is merely asserted to be.
   */
  reasoning: ReasoningStep[] | null;
}

const RULING_PREFIX = /^\[(SUSTAINED|OVERRULED)\]\s*/i;

/**
 * Renders one agent event into the courtroom record.
 *
 * The `[OBJECTION: …]` / `[RULING: …]` prefixes are not decoration — the
 * session transcript parses them to render an objection and a ruling
 * distinctly, and the manually-raised objection route has always written them.
 * Routing both the text turn and the voice turn through here means the graph's
 * objections appear in the record the same way a student's own do, instead of
 * as an unlabelled line of dialogue.
 *
 * Only the graph's own machine prefix is rewritten. Nothing else in the
 * transcript is stripped: an agent that carried through the unverified-text
 * marker keeps it.
 */
export function recordEvent(
  event: CourtEvent,
  objection: CourtObjection | null,
  activeWitness: string | null,
): RecordedEvent {
  const witnessName = event.speaker === "witness" ? activeWitness : null;
  // Empty is stored as null rather than [], so "no trace" is one value in the
  // record instead of two the UI would each have to test for.
  const reasoning = event.reasoning?.length ? event.reasoning : null;

  if (event.kind === "objection") {
    // The event carries the ground *id*; the objection carries the label the
    // record shows ("Leading Question" rather than "leading_question").
    const ground = [objection?.label ?? event.ground, event.citation]
      .filter(Boolean)
      .join(" — ");
    return {
      speaker: event.speaker,
      witnessName,
      transcript: `[OBJECTION: ${ground || "Evidentiary Objection"}] ${event.transcript}`,
      reasoning,
    };
  }

  if (event.kind === "ruling" && event.ruling) {
    return {
      speaker: event.speaker,
      witnessName,
      transcript: `[RULING: ${event.ruling.toUpperCase()}] ${event.transcript.replace(RULING_PREFIX, "")}`,
      reasoning,
    };
  }

  return {
    speaker: event.speaker,
    witnessName,
    transcript: event.transcript,
    reasoning,
  };
}

/**
 * The same event as spoken words.
 *
 * A judge says "Sustained." — reading the graph's `[SUSTAINED]` marker aloud
 * bracket and all would sound like a machine. Only that one known prefix is
 * rewritten; no general stripping happens here, because a blanket
 * bracket-removal would also swallow the unverified-text marker.
 */
export function speechText(event: CourtEvent): string {
  if (event.kind === "ruling" && event.ruling) {
    const spokenRuling = event.ruling === "sustained" ? "Sustained." : "Overruled.";
    return `${spokenRuling} ${event.transcript.replace(RULING_PREFIX, "")}`.trim();
  }
  return event.transcript.trim();
}

/**
 * Builds the system prompt that grounds the AI in its current role: judge,
 * opposing counsel, or a specific witness, for a specific Pakistani-law case.
 */
export function buildSystemPrompt(
  courtCase: Case,
  studentSide: StudentSide,
  phase: SessionPhase,
  persona: TurnSpeaker,
  witnessName: string | null,
): string {
  const studentParty =
    studentSide === "petitioner"
      ? courtCase.petitionerName
      : courtCase.respondentName;
  const studentRole =
    studentSide === "petitioner"
      ? courtCase.petitionerRole
      : courtCase.respondentRole;
  const opposingSide = oppositeSide(studentSide);
  const opposingParty =
    opposingSide === "petitioner"
      ? courtCase.petitionerName
      : courtCase.respondentName;
  const opposingRole =
    opposingSide === "petitioner"
      ? courtCase.petitionerRole
      : courtCase.respondentRole;

  const caseContext = `
Case: "${courtCase.title}" (${courtCase.areaOfLaw} matter under Pakistani law, difficulty: ${courtCase.difficulty})
Summary: ${courtCase.summary}
Applicable laws: ${courtCase.applicableLaws}
Petitioner: ${courtCase.petitionerName} (${courtCase.petitionerRole})
Respondent: ${courtCase.respondentName} (${courtCase.respondentRole})
The student is arguing as the ${studentSide.toUpperCase()} -- ${studentParty}, ${studentRole}.
Current courtroom phase: ${phase.replace("_", " ")}.
`.trim();

  if (persona === "judge") {
    return `You are a stern but fair judge presiding over a Pakistani court, moderating a moot-court practice session. ${caseContext}

Speak as the judge would in a Pakistani courtroom: measured, formal, addressing the student as "counsel" or "learned counsel". Respond briefly (2-4 sentences) to what the student just said -- acknowledge their point, probe with a pointed question about their legal reasoning or evidence, or direct them procedurally (e.g. to call a witness, or proceed to the next stage) when appropriate. Do not resolve the case yourself and do not give the student legal advice. Stay strictly in character as the judge.`;
  }

  if (persona === "opposing_counsel") {
    return `You are opposing counsel representing ${opposingParty} (${opposingRole}) in a Pakistani court, cross-examining or rebutting the student who represents ${studentParty} (${studentRole}). ${caseContext}

Speak as sharp, professional opposing counsel: challenge the student's argument, raise counterpoints grounded in the applicable laws, or pose a pointed cross-examination question. Keep responses brief (2-4 sentences) and combative but professional. Stay strictly in character.

Say it in simple English, because your listener is a law student who is usually not a native speaker. One idea per sentence, under about 20 words. Use the everyday word, not the formal one: "before" not "prior to", "this" not "the aforesaid", "even though" not "notwithstanding", "bring evidence" not "adduce evidence", "enough" not "sufficient", "so" not "therefore". No Latin and no archaic words (inter alia, prima facie, hereinbefore, whilst, "it is submitted that"). Say your point first, then the reason. Keep "My Lord" and "learned counsel" as they are, and quote any statute in its own words before explaining it simply.`;
  }

  const witness = courtCase.witnesses.find((w) => w.name === witnessName);
  const witnessStatement = witness?.statement ?? "";
  const witnessRole = witness?.role ?? "witness";

  return `You are ${witnessName}, a ${witnessRole} testifying as a witness in a Pakistani court. ${caseContext}

Your known testimony/statement: "${witnessStatement}"

Answer the student's question as this witness would: consistently with your statement, in first person, briefly (2-4 sentences), showing appropriate nervousness or confidence depending on the question. Do not break character or acknowledge you are an AI.`;
}
