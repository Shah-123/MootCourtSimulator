import { TurnSpeaker } from "@workspace/api-client-react";
import type {
  CourtReasoningStep,
  TurnProvenance,
} from "@workspace/api-client-react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * One paragraph of the record, and the parse that gets there.
 *
 * Lifted out of the session page when the chamber gained a transcript
 * overlay. Two surfaces now show the record — the slide-over inside the
 * courtroom and the written record elsewhere — and they must not be able to
 * disagree about when a provision is marked unverified. Copying this would
 * have let the overlay quietly drop the provenance rail, which is the one
 * thing on the entry a student must not miss.
 */

export type Mark = "objection" | "ruling" | "counsel" | "bench" | "witness";

export interface ParsedTurn {
  mark: Mark;
  speaker: string;
  citation: string | null;
  ground: string | null;
  ruling: "SUSTAINED" | "OVERRULED" | null;
  text: string;
  reasoning: CourtReasoningStep[] | null;
  /**
   * What the utterance actually leant on, read off the record rather than
   * re-derived from the transcript. Null for the student's own words and for
   * anything recorded before provenance was persisted, which is why the rail
   * below still falls back to the citation parsed out of the prefix.
   */
  provenance: TurnProvenance | null;
}

export function parseTurn(turn: {
  speaker: string;
  transcript: string;
  witnessName?: string | null;
  reasoning?: CourtReasoningStep[] | null;
  provenance?: TurnProvenance | null;
}): ParsedTurn {
  const reasoning = turn.reasoning?.length ? turn.reasoning : null;
  const provenance = turn.provenance ?? null;
  const objection = turn.transcript.match(/^\[OBJECTION:\s*(.*?)\]\s*(.*)$/s);
  if (objection) {
    const [ground, citation] = objection[1].split("—").map((s) => s.trim());
    return {
      mark: "objection",
      speaker: "Opposing counsel",
      citation: citation || null,
      ground: ground || "Evidentiary objection",
      ruling: null,
      text: objection[2] ?? "",
      reasoning,
      provenance,
    };
  }

  const ruling = turn.transcript.match(
    /^\[RULING:\s*(SUSTAINED|OVERRULED)\]\s*(.*)$/s,
  );
  if (ruling) {
    return {
      mark: "ruling",
      speaker: "The bench",
      citation: null,
      ground: null,
      ruling: ruling[1] as "SUSTAINED" | "OVERRULED",
      text: ruling[2] ?? "",
      reasoning,
      provenance,
    };
  }

  if (turn.speaker === TurnSpeaker.student) {
    return {
      mark: "counsel",
      speaker: "You",
      citation: null,
      ground: null,
      ruling: null,
      text: turn.transcript,
      reasoning,
      provenance,
    };
  }
  if (turn.speaker === TurnSpeaker.judge) {
    return {
      mark: "bench",
      speaker: "The bench",
      citation: null,
      ground: null,
      ruling: null,
      text: turn.transcript,
      reasoning,
      provenance,
    };
  }
  if (turn.speaker === TurnSpeaker.opposing_counsel) {
    return {
      mark: "counsel",
      speaker: "Opposing counsel",
      citation: null,
      ground: null,
      ruling: null,
      text: turn.transcript,
      reasoning,
      provenance,
    };
  }
  return {
    mark: "witness",
    speaker: turn.witnessName ? `Witness — ${turn.witnessName}` : "Witness",
    citation: null,
    ground: null,
    ruling: null,
    text: turn.transcript,
    reasoning,
    provenance,
  };
}

/** One provision in the rail, with the corpus's own flag on it. */
export function ProvenanceMark({
  citation,
  verified,
  heading,
}: {
  citation: string;
  verified: boolean;
  heading?: string;
}) {
  return (
    <>
      <span
        className="font-mono text-xs text-foreground/80"
        title={heading || undefined}
      >
        {citation}
      </span>
      <span
        className={cn("apparatus", verified ? "text-seal" : "text-stamp")}
        title={
          verified
            ? "Diffed word-for-word against its official source."
            : "This provision's text has not been checked against pakistancode.gov.pk. Do not quote it as authoritative."
        }
      >
        {verified ? "✓ Verified" : "⚠ Unverified"}
      </span>
    </>
  );
}

/**
 * The provenance rail on the right is the point of the whole entry: every
 * provision an agent leant on is shown beside the words it produced, with its
 * verification state attached. The mark is per provision, not per instrument:
 * one diffed against pakistancode.gov.pk reads Verified in seal green while
 * one still under review reads Unverified in stamp red, even where both come
 * from the same Act — which is exactly what a student needs to see before
 * repeating any of it in a real courtroom.
 */
export function RecordEntry({
  index,
  turn,
  verifiedCitations,
}: {
  index: number;
  turn: ParsedTurn;
  verifiedCitations: Set<string>;
}) {
  const isVerified = turn.citation
    ? verifiedCitations.has(turn.citation.trim())
    : false;
  const grounded = turn.provenance?.grounded ?? [];
  const fabricated = turn.provenance?.fabricated ?? [];

  return (
    <li
      data-mark={turn.mark}
      className={cn(
        "record-entry py-4",
        // Only the two marks a student must not miss keep a wash behind them.
        turn.mark === "objection" && "pl-4 pr-3",
        turn.mark === "ruling" && "pl-4 pr-3",
      )}
    >
      <div className="grid gap-x-5 gap-y-2 lg:grid-cols-[8.5rem_1fr_7.5rem]">
        <div className="flex items-baseline gap-2 lg:flex-col lg:gap-1">
          <span className="apparatus tabular-nums text-muted-foreground/70">
            &para;{String(index).padStart(2, "0")}
          </span>
          <span
            className={cn(
              "apparatus",
              turn.mark === "objection" && "text-stamp",
              turn.mark === "ruling" && "text-primary",
              turn.mark === "witness" && "text-seal",
              turn.mark === "counsel" && "text-foreground",
              turn.mark === "bench" && "text-primary",
            )}
          >
            {turn.speaker}
          </span>
        </div>

        <div className="min-w-0 space-y-2">
          {turn.ground && (
            <p className="apparatus text-stamp">Objection — {turn.ground}</p>
          )}

          {turn.ruling && (
            <p>
              <span
                className={
                  turn.ruling === "SUSTAINED"
                    ? "judicial-stamp-sustained"
                    : "judicial-stamp-overruled"
                }
              >
                {turn.ruling}
              </span>
            </p>
          )}

          <p className="font-serif text-[1.0625rem] leading-relaxed text-foreground">
            {turn.text}
          </p>

          {turn.reasoning && <ReasoningTrace steps={turn.reasoning} />}
        </div>

        {/* The provenance rail. Never conditional on how tidy the output
            looks: an unverified provision says so beside the words that
            leant on it, every time. */}
        <div className="flex flex-row flex-wrap items-baseline gap-x-2 gap-y-1 lg:flex-col lg:items-end">
          {grounded.length > 0
            ? grounded.map((provision) => (
                <ProvenanceMark
                  key={provision.citation}
                  citation={provision.citation}
                  verified={provision.verified}
                  heading={provision.heading}
                />
              ))
            : turn.citation && (
                <ProvenanceMark
                  citation={turn.citation}
                  verified={isVerified}
                />
              )}

          {/* A citation the corpus does not recognise at all. Distinct from an
              unverified one: that provision exists and its wording is still
              being confirmed, this one was never in the statute book. */}
          {fabricated.map((citation) => (
            <span
              key={citation}
              className="apparatus text-stamp"
              title={`Not found in the statute corpus: ${citation}`}
            >
              ⚠ not in corpus: {citation}
            </span>
          ))}
        </div>
      </div>
    </li>
  );
}

export function ReasoningTrace({ steps }: { steps: CourtReasoningStep[] }) {
  return (
    <details className="group mt-2 border-l border-rule pl-3">
      <summary className="apparatus inline-flex cursor-pointer list-none items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground">
        <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" />
        <span>
          How the bench got there ({steps.length}{" "}
          {steps.length === 1 ? "step" : "steps"})
        </span>
      </summary>

      <ol className="mt-2.5 space-y-2.5">
        {steps.map((step, index) => (
          <li key={index} className="space-y-0.5">
            <p className="apparatus text-muted-foreground/70 tabular-nums">
              {index + 1}
            </p>
            {step.thought && (
              <p className="font-serif text-sm italic leading-snug text-foreground/85">
                {step.thought}
              </p>
            )}
            {step.action && (
              <p className="break-all font-mono text-xs leading-snug text-primary">
                {step.action}
              </p>
            )}
            {step.observation && (
              <p className="font-serif text-sm leading-snug text-foreground/60">
                {step.observation}
              </p>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}
