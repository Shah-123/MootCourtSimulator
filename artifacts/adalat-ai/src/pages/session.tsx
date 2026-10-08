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
import { Textarea } from "@/components/ui/textarea";
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
  type ProceedingType,
} from "@workspace/api-client-react";
import {
  ChevronRight,
  FileText,
  Loader2,
  Pause,
  PenLine,
  Play,
  ScrollText,
  UserPlus,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiErrorState, getErrorMessage } from "@/components/api-state";
import { CaseName } from "@/components/case-name";
import { Chamber } from "@/components/courtroom/chamber";
import { CaseFilePanel } from "@/components/courtroom/case-file-panel";
import { AddressComposer } from "@/components/courtroom/composer";
import {
  EMPTY_LIVE,
  deriveStage,
  witnessPhase,
  type LiveStage,
} from "@/components/courtroom/stage-state";
import { SubtitleBar } from "@/components/courtroom/subtitle";
import { TranscriptPanel } from "@/components/courtroom/transcript-panel";
import { useToast } from "@/hooks/use-toast";
import { docket, phaseLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import "@/components/courtroom/chamber.css";

/**
 * The hearing, as a room rather than as a page.
 *
 * The screen is the courtroom; everything else is an overlay on top of it. That
 * inverts what this page used to be — a two-column reading layout with the
 * record on the left and the controls on the right — and the reason is that a
 * student arguing out loud is not reading. They need to know, at a glance and
 * while speaking, who has the floor and whether the witness they called is
 * actually in the box. A transcript answers both questions in prose, several
 * seconds late. A lit figure answers them immediately.
 *
 * Nothing about the hearing itself moved. The same five mutations run
 * (advance-phase, call-witness, objection, voice-turns, turn), the record is
 * the same component, and the state the room draws is derived from turns the
 * API already returned — see `stage-state.ts`.
 */

/** Where the hearing has reached, as a compact run of stage names. */
function PhaseStrip({
  phases,
  currentIndex,
}: {
  phases: string[];
  currentIndex: number;
}) {
  return (
    <ol className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
      {phases.map((phase, index) => {
        const isCurrent = index === currentIndex;
        const isPast = index < currentIndex;

        return (
          <li
            key={phase}
            aria-current={isCurrent ? "step" : undefined}
            className={cn(
              "apparatus flex items-baseline gap-1.5 border-b-2 pb-0.5",
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

/** A control on the dock: an icon over a word, sized for a touch target. */
function DockButton({
  icon,
  label,
  onClick,
  disabled,
  tone,
  active,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  tone?: "stamp" | "default";
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={cn(
        "chamber-dock-button",
        tone === "stamp" && "chamber-dock-button--stamp",
        active && "chamber-dock-button--active",
      )}
    >
      <span aria-hidden="true">{icon}</span>
      <span className="chamber-dock-label">{label}</span>
    </button>
  );
}

export default function SessionPage({ id }: { id: string }) {
  const sessionId = parseInt(id, 10);
  const [, setLocation] = useLocation();
  const queryClient = useQueryClient();

  const [live, setLive] = useState<LiveStage>(EMPTY_LIVE);
  const [panel, setPanel] = useState<"record" | "file" | null>(null);
  const [composerOpen, setComposerOpen] = useState(false);
  /**
   * A recess suspends the 3s poll and the room's ambient motion. It is a view
   * control and nothing more — the hearing on the server is exactly where it
   * was — so it is labelled as pausing the *live view* rather than the court.
   */
  const [paused, setPaused] = useState(false);

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
      refetchInterval: paused ? false : 3000,
    },
  });

  // Deliberately unfiltered. This list is the lookup behind the verification
  // badge — whether the *corpus* vouched for a provision — which is a question
  // about the statute book, not about what may be objected to in this
  // proceeding. Scoping it to the proceeding put a ⚠ on every citation in a
  // writ, where the catalogue is empty by design. ObjectionDialog runs its own
  // scoped query for the grounds a student may actually raise.
  const { data: grounds = [] } = useListObjectionGrounds();
  const verifiedCitations = useMemo(
    () =>
      new Set(grounds.filter((g) => g.verified).map((g) => g.citation.trim())),
    [grounds],
  );

  const advancePhase = useAdvanceSessionPhase();
  const { toast } = useToast();

  // Stable, so the voice control's reporting effect cannot loop.
  const handleStageChange = useCallback((next: LiveStage) => setLive(next), []);

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
    // The session's own sequence, served by the API. Listing the SessionPhase
    // enum was only ever right while every case was a trial: a writ runs
    // submissions and bench questions where a trial examines witnesses.
    const currentIndex = session.phases.indexOf(session.phase);
    const nextPhase = session.phases[currentIndex + 1];

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

  const phases = session.phases;
  const currentIndex = phases.indexOf(session.phase);
  // A matter heard on the record has no witness box, and the API refuses to
  // seat one. Hiding the control keeps the UI from offering a procedure this
  // proceeding does not have.
  const hasWitnessBox =
    phases.includes(SessionPhase.witness_examination) ||
    phases.includes(SessionPhase.cross_examination);
  const stage = deriveStage(session, live);
  const canCallWitness = hasWitnessBox && witnessPhase(session.phase);
  const nextStageLabel =
    session.phase === SessionPhase.closing
      ? "Submit for judgment"
      : "Next stage";

  return (
    <div className="chamber-shell">
      {/* ---- The head of the cause, over the room --------------------- */}
      <header className="chamber-hud">
        <div className="min-w-0">
          <p className="apparatus flex flex-wrap items-center gap-x-2 gap-y-1 text-muted-foreground">
            <span className="tabular-nums">{docket(session.id)}</span>
            <span aria-hidden="true">·</span>
            <span>{session.case.areaOfLaw}</span>
            <span aria-hidden="true">·</span>
            <span>for the {session.studentSide}</span>
          </p>

          <h1 className="mt-1 truncate font-serif text-lg leading-tight text-foreground sm:text-xl">
            <CaseName title={session.case.title} />
          </h1>
        </div>

        <div className="chamber-hud-right">
          <div className="hidden xl:block">
            <PhaseStrip phases={phases} currentIndex={currentIndex} />
          </div>

          <div className="flex shrink-0 items-center gap-1">
            <DockButton
              icon={<FileText className="h-4 w-4" />}
              label="Case file"
              active={panel === "file"}
              onClick={() => setPanel(panel === "file" ? null : "file")}
            />
            <DockButton
              icon={<ScrollText className="h-4 w-4" />}
              label="Record"
              active={panel === "record"}
              onClick={() => setPanel(panel === "record" ? null : "record")}
            />
            <DockButton
              icon={
                paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />
              }
              label={paused ? "Resume" : "Recess"}
              active={paused}
              onClick={() => setPaused((value) => !value)}
            />
          </div>
        </div>
      </header>

      {/* ---- The room ------------------------------------------------- */}
      <div className="chamber-stage">
        <Chamber
          stage={stage}
          studentSide={session.studentSide}
          phase={session.phase}
          paused={paused}
        />

        {paused && (
          <p className="chamber-recess apparatus">
            In recess — the live view is paused
          </p>
        )}
      </div>

      {/* ---- What is being said --------------------------------------- */}
      <SubtitleBar stage={stage} live={live} />

      {/* ---- The rostrum ---------------------------------------------- */}
      <div className="chamber-dock">
        <div className="chamber-dock-rostrum">
          <VoiceControl
            sessionId={sessionId}
            onTurnComplete={handleTurnComplete}
            onStageChange={handleStageChange}
            variant="dock"
          />
        </div>

        <div className="chamber-dock-actions">
          <DockButton
            icon={<PenLine className="h-4 w-4" />}
            label="Address"
            onClick={() => setComposerOpen(true)}
          />

          {/* Hides itself when the proceeding engages no grounds. */}
          <ObjectionDialog
            sessionId={sessionId}
            proceedingType={session.case.proceedingType}
          />

          {canCallWitness && (
            <CallWitnessDialog
              sessionId={sessionId}
              witnesses={session.case.witnesses}
            />
          )}

          {/* The words drop out on a phone to keep the dock on two rows, so
              the label has to live on the control as well — without it this
              is a bare chevron that advances the hearing, which is the one
              action on the dock nobody should press by accident. */}
          <Button
            onClick={handleAdvancePhase}
            disabled={advancePhase.isPending}
            size="sm"
            aria-label={nextStageLabel}
            title={nextStageLabel}
            className="h-11 shrink-0 rounded-sm"
          >
            {advancePhase.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : null}
            <span className="hidden sm:inline">{nextStageLabel}</span>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* ---- Overlays -------------------------------------------------- */}
      <CaseFilePanel
        open={panel === "file"}
        onClose={() => setPanel(null)}
        courtCase={session.case}
        witnessOnStand={stage.witnessOnStand}
      />

      <TranscriptPanel
        open={panel === "record"}
        onClose={() => setPanel(null)}
        turns={session.turns}
        verifiedCitations={verifiedCitations}
      />

      <AddressComposer
        sessionId={sessionId}
        open={composerOpen}
        onOpenChange={setComposerOpen}
        witnessOnStand={stage.witnessOnStand}
      />
    </div>
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
          // The room does the announcing — the witness walks to the box — but
          // a student who was looking at the dock rather than the bench gets
          // told in words as well.
          toast({
            title: `${witness} is called`,
            description: "The witness is taking the stand.",
          });
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
        <button type="button" className="chamber-dock-button">
          <span aria-hidden="true">
            <UserPlus className="h-4 w-4" />
          </span>
          <span className="chamber-dock-label">Call witness</span>
        </button>
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
          <Button
            onClick={handleCall}
            disabled={!witness || callWitness.isPending}
          >
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

function ObjectionDialog({
  sessionId,
  proceedingType,
}: {
  sessionId: number;
  proceedingType: ProceedingType;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [groundId, setGroundId] = useState<string>("");
  const [statement, setStatement] = useState<string>("");
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const { data: grounds = [], isLoading: groundsLoading } =
    useListObjectionGrounds({ proceedingType });
  const selected = grounds.find((g) => g.id === groundId);

  const { mutateAsync: raiseObjection, isPending } = useRaiseObjection();

  // Every ground is an evidentiary examination ground, so a matter heard on
  // the record engages none of them and the control does not belong on the
  // page at all. Offering it and refusing the objection would teach the
  // student that the ground exists here and was merely rejected.
  if (!groundsLoading && grounds.length === 0) return null;

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
        <button
          type="button"
          className="chamber-dock-button chamber-dock-button--stamp"
        >
          <span aria-hidden="true" className="font-mono text-base leading-none">
            §
          </span>
          <span className="chamber-dock-label">Object</span>
        </button>
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
            <label
              htmlFor="objection-ground"
              className="apparatus text-muted-foreground"
            >
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
          <Button
            variant="ghost"
            onClick={() => setIsOpen(false)}
            disabled={isPending}
          >
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
