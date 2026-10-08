import { SessionPhase, TurnSpeaker } from "@workspace/api-client-react";
import type { SessionDetail, Turn } from "@workspace/api-client-react";
import type { SpeakerCue } from "@/components/live-caption";

/**
 * Who is on their feet, and what the chamber should therefore look like.
 *
 * Everything here is *derived* — from turns the API already returned and from
 * events the voice stream already sends. Nothing in this file asks the server
 * a new question, and nothing invents a state the courtroom does not really
 * have. A figure lights up because a turn exists or because a `speaker` event
 * arrived, never because the scene would look better with someone lit.
 *
 * The one rule worth stating: the witness is derived exactly the way the
 * server derives it (routes/sessions.ts) — the most recent witness turn *in
 * the current phase*. Reimplementing it differently would put someone in the
 * box that the graph does not think is there, which is the one drift that
 * would make the picture lie about the hearing.
 */

export type StageRole = "judge" | "opposing" | "student" | "witness";

/** What the active figure is doing. Drives the figure's animation only. */
export type StageActivity = "idle" | "speaking" | "thinking" | "listening";

/** What the voice control is doing. Reported up by `VoiceControl`. */
export interface LiveStage {
  state: "idle" | "recording" | "processing" | "playing" | "interrupting";
  cue: SpeakerCue | null;
  caption: string;
  /** The student's own words, as transcribed, for the current turn. */
  userTranscript: string | null;
  /** A note from the bench when a spoken interjection drew no objection. */
  note: string | null;
}

export const EMPTY_LIVE: LiveStage = {
  state: "idle",
  cue: null,
  caption: "",
  userTranscript: null,
  note: null,
};

export interface StageState {
  /** The figure to light. Null when the court is simply waiting. */
  activeRole: StageRole | null;
  activity: StageActivity;
  /** The witness in the box, or null when the box is empty. */
  witnessOnStand: string | null;
  /** The bench's most recent disposition, for the ruling flash. */
  lastRuling: "sustained" | "overruled" | null;
  /**
   * Identity of that disposition, so the flash can fire once per ruling.
   *
   * The value alone is not enough. One student utterance can produce an
   * objection, a ruling *and* the witness's answer in a single batch, so by the
   * time the poll returns, the ruling is no longer the last turn — and two
   * SUSTAINED rulings in a row are two events with one value. Keying on the
   * turn id fires exactly once per ruling either way.
   */
  rulingKey: string | null;
  /** True while an objection is the last thing said and no ruling has landed. */
  objectionPending: boolean;
  /** The line to show as the courtroom subtitle. */
  captionText: string;
  /** Who that line belongs to. */
  captionSpeaker: string | null;
}

function cueRole(cue: SpeakerCue): StageRole {
  if (cue.speaker === "judge") return "judge";
  if (cue.speaker === "witness") return "witness";
  return "opposing";
}

function turnRole(turn: Turn): StageRole {
  if (turn.speaker === TurnSpeaker.judge) return "judge";
  if (turn.speaker === TurnSpeaker.witness) return "witness";
  if (turn.speaker === TurnSpeaker.student) return "student";
  return "opposing";
}

/**
 * The witness the graph considers to be in the box.
 *
 * Mirrors the server: the most recent witness turn in the *current* phase.
 * Advancing from examination-in-chief to cross therefore empties the box,
 * which is correct — the graph stops routing to a witness at the same moment.
 */
export function activeWitnessOf(
  turns: Turn[],
  phase: SessionPhase,
): string | null {
  return (
    [...turns]
      .reverse()
      .find((t) => t.speaker === TurnSpeaker.witness && t.phase === phase)
      ?.witnessName ?? null
  );
}

/** True only in the two phases where a witness may be called at all. */
export function witnessPhase(phase: SessionPhase): boolean {
  return (
    phase === SessionPhase.witness_examination ||
    phase === SessionPhase.cross_examination
  );
}

function rulingOf(turn: Turn | undefined): "sustained" | "overruled" | null {
  if (!turn) return null;
  const match = turn.transcript.match(/^\[RULING:\s*(SUSTAINED|OVERRULED)\]/);
  if (!match) return null;
  return match[1] === "SUSTAINED" ? "sustained" : "overruled";
}

/** The bench's latest disposition anywhere on the record, and which turn it was. */
function latestRuling(turns: Turn[]): {
  ruling: "sustained" | "overruled" | null;
  key: string | null;
} {
  for (let i = turns.length - 1; i >= 0; i -= 1) {
    const ruling = rulingOf(turns[i]);
    if (ruling) return { ruling, key: String(turns[i].id) };
  }
  return { ruling: null, key: null };
}

function isObjection(turn: Turn | undefined): boolean {
  return turn ? /^\[OBJECTION:/.test(turn.transcript) : false;
}

/** Strips the record's machine marks so a line reads as speech on screen. */
export function spokenText(transcript: string): string {
  return transcript
    .replace(/^\[OBJECTION:[^\]]*\]\s*/, "")
    .replace(/^\[RULING:\s*(?:SUSTAINED|OVERRULED)\]\s*/, "")
    .trim();
}

export function deriveStage(
  session: SessionDetail,
  live: LiveStage,
): StageState {
  const turns = session.turns;
  // Only what has been said in the *current* stage lights the room. Reading
  // the last turn on the record regardless of phase meant that advancing to
  // cross-examination left the witness from examination-in-chief lit while the
  // box beside them was correctly drawn empty — the picture contradicting
  // itself at exactly the moment the student changed footing. A new stage
  // opens with the floor to nobody, which is also what the graph thinks.
  const last = [...turns].reverse().find((t) => t.phase === session.phase);
  const witnessOnStand = activeWitnessOf(turns, session.phase);

  // While the stream is running it is the truth: it is ahead of the polled
  // session by a whole turn, and it is what the student can hear.
  if (live.state === "recording") {
    return {
      activeRole: "student",
      activity: "speaking",
      witnessOnStand,
      lastRuling: null,
      rulingKey: null,
      objectionPending: false,
      captionText: "",
      captionSpeaker: "You have the floor",
    };
  }

  if (live.state === "processing") {
    return {
      activeRole: null,
      activity: "thinking",
      witnessOnStand,
      lastRuling: null,
      rulingKey: null,
      objectionPending: false,
      captionText: live.userTranscript ?? "",
      captionSpeaker: live.userTranscript ? "You" : null,
    };
  }

  if ((live.state === "playing" || live.state === "interrupting") && live.cue) {
    const cue = live.cue;
    return {
      activeRole: cueRole(cue),
      activity: live.state === "interrupting" ? "listening" : "speaking",
      // A witness named on the live cue is in the box even before the turn
      // has been polled back into `session.turns`.
      witnessOnStand: cue.witnessName ?? witnessOnStand,
      lastRuling: cue.kind === "ruling" ? cue.ruling : null,
      // Live, a ruling arrives as its own event, so null → value is already
      // one transition per ruling and no id is needed.
      rulingKey: cue.kind === "ruling" ? "live" : null,
      objectionPending: cue.kind === "objection",
      captionText: live.caption,
      captionSpeaker: null,
    };
  }

  // Nothing live: the chamber rests on the last thing that was actually said.
  const ruling = latestRuling(turns);
  return {
    activeRole: last ? turnRole(last) : null,
    activity: "idle",
    witnessOnStand,
    lastRuling: ruling.ruling,
    rulingKey: ruling.key,
    objectionPending: isObjection(last),
    captionText: last ? spokenText(last.transcript) : "",
    captionSpeaker: null,
  };
}
