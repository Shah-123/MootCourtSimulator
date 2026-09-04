import { useLocation } from "wouter";
import {
  useGetSession,
  useAdvanceSessionPhase,
  useCallWitness,
  useListObjectionGrounds,
  useRaiseObjection,
} from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { getGetSessionQueryKey } from "@workspace/api-client-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { VoiceControl } from "@/components/voice-control";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  SessionPhase,
  SessionStatus,
  TurnSpeaker,
} from "@workspace/api-client-react";
import type {
  CourtReasoningStep,
  TurnProvenance,
} from "@workspace/api-client-react";
import { ChevronRight, Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ApiErrorState, getErrorMessage } from "@/components/api-state";
import { CaseBriefArgument } from "@/components/case-brief";
import { CaseName } from "@/components/case-name";
import { useToast } from "@/hooks/use-toast";
import { docket, phaseLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

type Mark = "objection" | "ruling" | "counsel" | "bench" | "witness";

interface ParsedTurn {
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

function parseTurn(turn: {
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

/**
 * Where the hearing has reached.
 *
 * Five filled boxes in a grid read as a wizard, which invites a student to
 * click ahead through them; they are stages of a hearing that has to be
 * argued, not steps in a form. Set as a run of stage names with the current
 * one underlined — the same mark the nav and the tab heads use — and the ones
 * already risen from in muted text.
 */
function PhaseStrip({ phases, currentIndex }: { phases: string[]; currentIndex: number }) {
  return (
    <ol className="flex flex-wrap items-baseline gap-x-5 gap-y-2 border-t border-rule/60 pt-3">
      {phases.map((phase, index) => {
        const isCurrent = index === currentIndex;
        const isPast = index < currentIndex;

        return (
          <li
            key={phase}
            aria-current={isCurrent ? "step" : undefined}
            className={cn(
              "apparatus flex items-baseline gap-1.5 border-b-2 pb-1",
              isCurrent
                ? "border-foreground text-foreground"
                : "border-transparent",
              isPast ? "text-muted-foreground" : "",
              !isCurrent && !isPast ? "text-muted-foreground/45" : "",
            )}
          >
            <span className="tabular-nums">{index + 1}</span>
            <span>{phaseLabel(phase)}</span>
          </li>
        );
      })}
    </ol>
  );
}

export default function SessionPage({ id }: { id: string }) {
  const sessionId = parseInt(id, 10);
  const [, setLocation] = useLocation();
  const queryClient = useQueryClient();
  const scrollRef = useRef<HTMLDivElement>(null);

  const {
    data: session,
    isLoading,
    isError,
    error,
    refetch,
  } = useGetSession(sessionId, {
    query: {
      queryKey: getGetSessionQueryKey(sessionId),
      enabled: Number.isInteger(sessionId) && sessionId > 0,
      refetchInterval: 3000,
    },
  });

  const { data: grounds = [] } = useListObjectionGrounds();
  const verifiedCitations = useMemo(
    () =>
      new Set(grounds.filter((g) => g.verified).map((g) => g.citation.trim())),
    [grounds],
  );

  const advancePhase = useAdvanceSessionPhase();
  const { toast } = useToast();

  useEffect(() => {
    if (scrollRef.current) {
      const scrollContainer = scrollRef.current.querySelector(
        "[data-radix-scroll-area-viewport]",
      );
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }
    }
  }, [session?.turns.length]);

  useEffect(() => {
    if (session?.status === SessionStatus.completed) {
      setLocation(`/sessions/${sessionId}/verdict`);
    }
  }, [session?.status, sessionId, setLocation]);

  if (!Number.isInteger(sessionId) || sessionId <= 0) {
    return (
      <ApiErrorState error={new Error("This courtroom address is invalid.")} />
    );
  }

  if (isError) {
    return <ApiErrorState error={error} onRetry={() => void refetch()} />;
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
        <p className="apparatus text-muted-foreground">The court is rising</p>
        <p className="display-sm mt-3">Convening the chamber</p>
      </div>
    );
  }

  if (!session) return null;

  if (session.status === SessionStatus.completed) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
        <p className="apparatus text-muted-foreground">Hearing concluded</p>
        <p className="display-sm mt-3">The bench is writing its judgment</p>
      </div>
    );
  }

  const handleAdvancePhase = () => {
    const phases = Object.values(SessionPhase);
    const currentIndex = phases.indexOf(session.phase);
    const nextPhase = phases[currentIndex + 1];

    if (nextPhase) {
      advancePhase.mutate(
        { id: sessionId, data: { phase: nextPhase } },
        {
          onSuccess: (data) => {
            queryClient.setQueryData(getGetSessionQueryKey(sessionId), data);
            if (nextPhase === SessionPhase.verdict) {
              setLocation(`/sessions/${sessionId}/verdict`);
            }
          },
          onError: (error) => {
            toast({
              variant: "destructive",
              title: "The phase could not be advanced",
              description: getErrorMessage(error),
            });
          },
        },
      );
    }
  };

  const handleTurnComplete = () => {
    queryClient.invalidateQueries({
      queryKey: getGetSessionQueryKey(sessionId),
    });
  };

  const phases = Object.values(SessionPhase);
  const currentIndex = phases.indexOf(session.phase);

  return (
    <div className="flex min-h-[calc(100vh-12rem)] flex-col gap-6 pb-4">
      <header className="border-b border-rule pb-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <p className="apparatus flex flex-wrap items-center gap-x-2 gap-y-1 text-muted-foreground">
              <span className="tabular-nums">{docket(session.id)}</span>
              <span aria-hidden="true">·</span>
              <span>{session.case.areaOfLaw}</span>
              <span aria-hidden="true">·</span>
              <span>for the {session.studentSide}</span>
            </p>

            <h1 className="display-sm mt-2">
              <CaseName title={session.case.title} />
            </h1>

            <p
              className="mt-2 truncate font-mono text-xs text-muted-foreground"
              title={session.case.applicableLaws}
            >
              {session.case.applicableLaws}
            </p>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <ObjectionDialog sessionId={sessionId} />

            {(session.phase === SessionPhase.witness_examination ||
              session.phase === SessionPhase.cross_examination) && (
              <CallWitnessDialog
                sessionId={sessionId}
                witnesses={session.case.witnesses}
              />
            )}

            <Button
              onClick={handleAdvancePhase}
              disabled={advancePhase.isPending}
            >
              {advancePhase.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : null}
              <span>
                {session.phase === SessionPhase.closing
                  ? "Submit for judgment"
                  : "Next stage"}
              </span>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="mt-4">
          <PhaseStrip phases={phases} currentIndex={currentIndex} />
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-8 lg:grid-cols-[1fr_21rem] xl:grid-cols-[1fr_24rem] lg:gap-10">
        {/* The record of proceedings. */}
        <section className="flex min-h-[28rem] flex-col">
          <h2 className="rule-heading">
            <span>Record of proceedings</span>
            <span className="tabular-nums">
              {session.turns.length}{" "}
              {session.turns.length === 1 ? "entry" : "entries"}
            </span>
          </h2>

          <ScrollArea ref={scrollRef} className="-mx-1 flex-1 px-1">
            {session.turns.length === 0 ? (
              <div className="flex min-h-[22rem] flex-col items-center justify-center px-6 text-center">
                <p className="display-sm">The court is in session.</p>
                <p className="mx-auto mt-3 max-w-md font-serif leading-relaxed text-muted-foreground">
                  The bench is seated and the record is open. Take the rostrum
                  and make your appearance.
                </p>
              </div>
            ) : (
              <ol className="divide-y divide-rule/60">
                {session.turns.map((turn, index) => (
                  <RecordEntry
                    key={turn.id}
                    index={index + 1}
                    turn={parseTurn(turn)}
                    verifiedCitations={verifiedCitations}
                  />
                ))}
              </ol>
            )}
          </ScrollArea>
        </section>

        <aside className="flex flex-col gap-8">
          <div>
            <h2 className="rule-heading">
              <span>The rostrum</span>
            </h2>
            <div className="pt-4">
              <VoiceControl
                sessionId={sessionId}
                onTurnComplete={handleTurnComplete}
              />
            </div>
          </div>

          {/* Was a set of hand-rolled buttons whose initial state ("floor") no
              panel answered to, so the brief opened blank and stayed blank
              until something was clicked. Radix picks the first head by
              default and keeps the arrow keys working. */}
          <Tabs defaultValue="brief" className="flex min-h-0 flex-1 flex-col">
            <TabsList>
              <TabsTrigger value="brief">Brief</TabsTrigger>
              <TabsTrigger value="witnesses">
                Witnesses ({session.case.witnesses?.length ?? 0})
              </TabsTrigger>
              <TabsTrigger value="statutes">Statutes</TabsTrigger>
            </TabsList>

            <TabsContent
              value="brief"
              className="max-h-[22rem] overflow-y-auto pr-1"
            >
              <p className="font-serif leading-relaxed text-foreground/85">
                {session.case.summary}
              </p>
              {session.case.brief && (
                <CaseBriefArgument brief={session.case.brief} />
              )}
            </TabsContent>

            <TabsContent
              value="witnesses"
              className="max-h-[22rem] overflow-y-auto pr-1"
            >
              <ul className="divide-y divide-rule/70">
                {session.case.witnesses?.map((w, idx) => (
                  <li key={idx} className="py-3 first:pt-0">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-serif text-foreground">
                        {w.name}
                      </span>
                      <span className="apparatus shrink-0 text-muted-foreground">
                        {w.role}
                      </span>
                    </div>
                    <p className="mt-1 font-serif text-sm italic leading-relaxed text-foreground/75">
                      “{w.statement}”
                    </p>
                  </li>
                ))}
              </ul>
            </TabsContent>

            <TabsContent
              value="statutes"
              className="max-h-[22rem] overflow-y-auto pr-1"
            >
              <p className="apparatus text-muted-foreground">
                Provisions in play
              </p>
              <p className="mt-2 font-mono text-xs leading-relaxed text-foreground/85">
                {session.case.applicableLaws}
              </p>
              <p className="mt-4 border-t border-rule pt-3 font-serif text-sm leading-relaxed text-muted-foreground">
                Every citation either side makes is checked against the corpus
                before it reaches the record. One that is not in it is marked as
                such.
              </p>
            </TabsContent>
          </Tabs>
        </aside>
      </div>
    </div>
  );
}

/**
 * One paragraph of the record.
 *
 * The provenance rail on the right is the point of the whole layout: every
 * provision an agent leant on is shown beside the words it produced, with its
 * verification state attached. The mark is per provision, not per instrument:
 * one diffed against pakistancode.gov.pk reads Verified in seal green while
 * one still under review reads Unverified in stamp red, even where both come
 * from the same Act — which is exactly what a student needs to see before
 * repeating any of it in a real courtroom.
 *
 * The rail reads the provenance persisted with the turn where there is any.
 * Before that was stored it could only re-derive a single citation from the
 * `[OBJECTION: …]` prefix, so a reload silently dropped every provision the
 * bench and the witness had relied on, and dropped the "not in corpus" mark
 * altogether — the record went quiet at exactly the point it had most to say.
 * Turns written before the column existed still take that older path.
 */
function RecordEntry({
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
        // Counsel and the bench are told apart by the rule and the name, the
        // way a transcript tells them apart.
        turn.mark === "objection" && "pl-4 pr-3",
        turn.mark === "ruling" && "pl-4 pr-3",
      )}
    >
      <div className="grid gap-x-5 gap-y-2 lg:grid-cols-[8.5rem_1fr_7.5rem]">
        <div className="flex items-baseline gap-2 lg:flex-col lg:gap-1">
          <span className="apparatus tabular-nums text-muted-foreground/70">
            ¶{String(index).padStart(2, "0")}
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

/** One provision in the rail, with the corpus's own flag on it. */
function ProvenanceMark({
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

function ReasoningTrace({ steps }: { steps: CourtReasoningStep[] }) {
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

function CallWitnessDialog({
  sessionId,
  witnesses,
}: {
  sessionId: number;
  witnesses: Array<{ name: string; role: string }>;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [witness, setWitness] = useState<string>("");
  const callWitness = useCallWitness();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const handleCall = () => {
    if (!witness) return;
    callWitness.mutate(
      { id: sessionId, data: { witnessName: witness } },
      {
        onSuccess: (data) => {
          queryClient.setQueryData(getGetSessionQueryKey(sessionId), data);
          setIsOpen(false);
          setWitness("");
        },
        onError: (error) => {
          toast({
            variant: "destructive",
            title: "The witness could not be called",
            description: getErrorMessage(error),
          });
        },
      },
    );
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          Call a witness
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="display-sm text-left">
            Call a witness
          </DialogTitle>
          <DialogDescription className="text-left font-serif">
            Sworn witnesses on the case record. The one you call takes the stand
            and answers only from their statement.
          </DialogDescription>
        </DialogHeader>
        <div className="py-2">
          <Select value={witness} onValueChange={setWitness}>
            <SelectTrigger>
              <SelectValue placeholder="Select a witness on record" />
            </SelectTrigger>
            <SelectContent>
              {witnesses.map((w) => (
                <SelectItem key={w.name} value={w.name}>
                  <span className="font-serif">{w.name}</span>
                  <span className="apparatus ml-2 text-muted-foreground">
                    {w.role}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button onClick={handleCall} disabled={!witness || callWitness.isPending}>
            {callWitness.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : null}
            <span>Call to the stand</span>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ObjectionDialog({ sessionId }: { sessionId: number }) {
  const [isOpen, setIsOpen] = useState(false);
  const [groundId, setGroundId] = useState<string>("");
  const [statement, setStatement] = useState<string>("");
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const { data: grounds = [], isLoading: groundsLoading } =
    useListObjectionGrounds();
  const selected = grounds.find((g) => g.id === groundId);

  const { mutateAsync: raiseObjection, isPending } = useRaiseObjection();

  const handleSubmit = async () => {
    if (!groundId) return;
    try {
      await raiseObjection({
        id: sessionId,
        data: { groundId, statement },
      });
      queryClient.invalidateQueries({
        queryKey: getGetSessionQueryKey(sessionId),
      });
      setIsOpen(false);
      setGroundId("");
      setStatement("");
      toast({
        title: "Objection put to the bench",
        description: "The judge is considering the ground you raised.",
      });
    } catch (err) {
      toast({
        variant: "destructive",
        title: "The objection could not be put to the bench",
        description: getErrorMessage(err),
      });
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        {/* The one control on the page that keeps a reserved colour, because
            it is the one that raises an objection. */}
        <Button
          variant="outline"
          size="sm"
          className="border-stamp/50 text-stamp"
        >
          Object
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[540px]">
        <DialogHeader>
          <DialogTitle className="display-sm text-left text-stamp">
            Raise an objection
          </DialogTitle>
          <DialogDescription className="text-left font-serif">
            Every ground below is anchored in the Qanun-e-Shahadat Order 1984 or
            the procedural codes. You cannot object on a ground that is not.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-1">
          <div className="space-y-2">
            <label htmlFor="objection-ground" className="apparatus text-muted-foreground">
              Ground
            </label>
            <Select value={groundId} onValueChange={setGroundId}>
              <SelectTrigger id="objection-ground">
                <SelectValue
                  placeholder={
                    groundsLoading
                      ? "Loading grounds…"
                      : "Choose a ground of objection"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {grounds.map((g) => (
                  <SelectItem key={g.id} value={g.id}>
                    <span className="flex flex-col py-0.5 text-left">
                      <span className="font-serif">
                        {g.label}
                        <span className="ml-2 font-mono text-xs text-muted-foreground">
                          {g.citation}
                        </span>
                      </span>
                      <span className="text-xs leading-snug text-muted-foreground">
                        {g.description}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* The provision itself, with its verification state stated. A
              student about to quote this in a real courtroom is entitled to
              know whether anyone has checked it. */}
          {selected && (
            <figure className="border-l-2 border-rule pl-4">
              <figcaption className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule/70 pb-1.5">
                <span className="font-mono text-xs text-foreground">
                  {selected.citation}
                </span>
                <span
                  className={cn(
                    "apparatus",
                    selected.verified ? "text-seal" : "text-stamp",
                  )}
                  title={
                    selected.verified
                      ? "Diffed word-for-word against its official source."
                      : "This provision's text has not been checked against pakistancode.gov.pk. Do not quote it as authoritative."
                  }
                >
                  {selected.verified ? "✓ Verified" : "⚠ Unverified"}
                </span>
              </figcaption>
              <p className="mt-2 font-serif text-sm leading-relaxed text-foreground/85">
                {selected.content}
              </p>
            </figure>
          )}

          <div className="space-y-2">
            <label
              htmlFor="objection-statement"
              className="apparatus text-muted-foreground"
            >
              What you say to the bench (optional)
            </label>
            <Textarea
              id="objection-statement"
              value={statement}
              onChange={(e) => setStatement(e.target.value)}
              placeholder="My Lord, learned counsel is leading the witness in examination-in-chief, contrary to Article 133 of the Qanun-e-Shahadat…"
              className="min-h-[84px] resize-none rounded-sm font-serif leading-relaxed"
            />
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="ghost" onClick={() => setIsOpen(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!groundId || isPending}
            className="bg-stamp text-stamp-foreground border-stamp"
          >
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            <span>Put it to the bench</span>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
