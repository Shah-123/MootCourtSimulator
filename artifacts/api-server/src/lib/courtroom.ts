import type { Case, ReasoningStep, TurnProvenance } from "@workspace/db";
import type { CourtEvent, CourtObjection } from "./ai-service";

export type SessionPhase =
  | "opening"
  | "witness_examination"
  | "cross_examination"
  | "closing"
  | "verdict";

export type StudentSide = "petitioner" | "respondent";

export type TurnSpeaker = "student" | "judge" | "opposing_counsel" | "witness";

export const PHASE_ORDER: SessionPhase[] = [
  "opening",
  "witness_examination",
  "cross_examination",
  "closing",
  "verdict",
];

export function isSessionPhase(value: string): value is SessionPhase {
  return PHASE_ORDER.includes(value as SessionPhase);
}

export function isStudentSide(value: string): value is StudentSide {
  return value === "petitioner" || value === "respondent";
}

export function isValidPhaseTransition(
  current: SessionPhase,
  next: SessionPhase,
): boolean {
  const currentIndex = PHASE_ORDER.indexOf(current);
  const nextIndex = PHASE_ORDER.indexOf(next);
  return nextIndex === currentIndex + 1;
}

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
  /**
   * The provisions this utterance leant on, and anything the audit could not
   * find. The same argument as `reasoning`, about the other half of the claim:
   * the live stream already carried it, so a reload used to be the only thing
   * standing between a student and the provenance of what they had just heard.
   */
  provenance: TurnProvenance | null;
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
  // What the audit could not find in the corpus, attributed to this agent.
  // Passed in rather than recomputed: the caller has already audited this
  // utterance to decide whether to warn about it, and auditing it twice
  // invites the record and the log to disagree about the same words.
  fabricated: string[] = [],
): RecordedEvent {
  const witnessName = event.speaker === "witness" ? activeWitness : null;
  // Empty is stored as null rather than [], so "no trace" is one value in the
  // record instead of two the UI would each have to test for.
  const reasoning = event.reasoning?.length ? event.reasoning : null;
  const grounded = event.grounded ?? [];
  const provenance =
    grounded.length || fabricated.length ? { grounded, fabricated } : null;

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
      provenance,
    };
  }

  if (event.kind === "ruling" && event.ruling) {
    return {
      speaker: event.speaker,
      witnessName,
      transcript: `[RULING: ${event.ruling.toUpperCase()}] ${event.transcript.replace(RULING_PREFIX, "")}`,
      reasoning,
      provenance,
    };
  }

  return {
    speaker: event.speaker,
    witnessName,
    transcript: event.transcript,
    reasoning,
    provenance,
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
