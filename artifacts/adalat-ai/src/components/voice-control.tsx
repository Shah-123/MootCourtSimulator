import { useState, useEffect, useRef } from "react";
import {
  useVoiceRecorder,
  useVoiceStream,
  useSpeechActivity,
  type AppEvent,
} from "@workspace/integrations-openai-ai-react/audio";
import { Button } from "@/components/ui/button";
import { Mic, Square, Loader2, Volume2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { getErrorMessage } from "@/components/api-state";
import {
  LiveCaption,
  speakerLabel,
  type SpeakerCue,
} from "@/components/live-caption";
import type { LiveStage } from "@/components/courtroom/stage-state";
import { useToast } from "@/hooks/use-toast";

interface VoiceRecorderProps {
  sessionId: number;
  onTurnComplete: () => void;
  disabled?: boolean;
  /**
   * Reports what the rostrum is doing so the chamber can light the figure that
   * currently holds the floor. Read-only: this control still owns the state and
   * behaves identically whether or not anyone is listening.
   */
  onStageChange?: (stage: LiveStage) => void;
  /**
   * "dock" drops the caption and the status line, because inside the courtroom
   * the chamber's own subtitle bar is already showing both and two copies of a
   * live caption on one screen is worse than none.
   */
  variant?: "panel" | "dock";
}

function parseSpeakerCue(event: AppEvent): SpeakerCue | null {
  if (event.type !== "speaker") return null;
  const speaker = event.speaker;
  if (
    speaker !== "judge" &&
    speaker !== "opposing_counsel" &&
    speaker !== "witness"
  ) {
    return null;
  }
  return {
    speaker,
    kind: (event.kind as SpeakerCue["kind"]) ?? "bench",
    witnessName:
      typeof event.witnessName === "string" ? event.witnessName : null,
    citation: typeof event.citation === "string" ? event.citation : null,
    ruling:
      event.ruling === "sustained" || event.ruling === "overruled"
        ? event.ruling
        : null,
    grounded: Array.isArray(event.grounded)
      ? (event.grounded as SpeakerCue["grounded"])
      : [],
    fabricated: Array.isArray(event.fabricated)
      ? (event.fabricated as string[])
      : [],
    reasoning: Array.isArray(event.reasoning)
      ? (event.reasoning as SpeakerCue["reasoning"])
      : [],
  };
}

const TICKS = 32;

/**
 * The needle on the recording.
 *
 * Sat in a bordered, tinted well and ran seal → primary → stamp as it rose,
 * which read as a three-band warning: a student speaking loudly enough was
 * shown the same red the record uses for an unverified provision. It is a
 * level, not a verdict, so it is one colour on a bare baseline now.
 */
function LevelRule({ level, live }: { level: number; live: boolean }) {
  const lit = live ? Math.min(TICKS, Math.round((level / 0.22) * TICKS)) : 0;

  return (
    <div
      className="flex h-5 w-full items-end justify-between gap-[3px] border-b border-rule"
      role="presentation"
      aria-hidden="true"
    >
      {Array.from({ length: TICKS }, (_, i) => (
        <span
          key={i}
          className={cn(
            "w-[2px] transition-all duration-75",
            i < lit ? "bg-foreground/70" : "bg-rule",
          )}
          style={{ height: i < lit ? `${35 + (i / TICKS) * 65}%` : "18%" }}
        />
      ))}
    </div>
  );
}

export function VoiceControl({
  sessionId,
  onTurnComplete,
  disabled,
  onStageChange,
  variant = "panel",
}: VoiceRecorderProps) {
  const [streamState, setStreamState] = useState<
    "idle" | "processing" | "playing" | "interrupting"
  >("idle");
  const [cue, setCue] = useState<SpeakerCue | null>(null);
  const [caption, setCaption] = useState("");
  const [note, setNote] = useState<string | null>(null);
  // Already sent by the stream and until now dropped on the floor. The chamber
  // shows it as the student's own subtitle while the court is considering.
  const [userTranscript, setUserTranscript] = useState<string | null>(null);
  const recorder = useVoiceRecorder();
  const interrupter = useVoiceRecorder();
  const { toast } = useToast();

  const baseUrl = import.meta.env.BASE_URL.replace(/\/$/, "");
  const workletUrl = `${baseUrl}/audio-playback-worklet.js`;

  const stream = useVoiceStream({
    workletPath: workletUrl,
    onEvent: (event) => {
      const next = parseSpeakerCue(event);
      if (next) {
        setCue(next);
        setCaption("");
        setNote(null);
        return;
      }
      if (event.type === "note" && typeof event.data === "string") {
        setNote(event.data);
      }
      if (event.type === "user_transcript" && typeof event.data === "string") {
        setUserTranscript(event.data);
      }
    },
    onTranscript: (delta) => setCaption((text) => text + delta),
    onComplete: () => {
      setStreamState("idle");
      onTurnComplete();
    },
    onError: (err) => {
      console.error("Voice stream error:", err);
      setStreamState("idle");
      toast({
        variant: "destructive",
        title: "The spoken response failed",
        description: getErrorMessage(err),
      });
    },
  });

  const bargingRef = useRef(false);
  const listening = streamState === "playing" || streamState === "interrupting";

  const postInterjection = async (blob: Blob) => {
    setStreamState("processing");
    setCue(null);
    setCaption("");
    setUserTranscript(null);
    try {
      await stream.streamVoiceResponse(
        `/api/sessions/${sessionId}/interject`,
        blob,
      );
    } catch (error) {
      setStreamState("idle");
      toast({
        variant: "destructive",
        title: "The objection could not be put to the Bench",
        description: getErrorMessage(error),
      });
    }
  };

  useSpeechActivity(interrupter.stream, {
    enabled: listening,
    onSpeechStart: () => {
      if (bargingRef.current || streamState !== "playing") return;
      bargingRef.current = true;
      stream.stop();
      setStreamState("interrupting");
    },
    onSpeechEnd: () => {
      if (!bargingRef.current) return;
      bargingRef.current = false;
      void interrupter.stopRecording().then((blob) => {
        if (blob.size > 0) void postInterjection(blob);
        else setStreamState("idle");
      });
    },
  });

  useEffect(() => {
    if (streamState !== "playing") return;
    let opened = true;
    interrupter.startRecording().catch(() => {
      opened = false;
    });
    return () => {
      if (opened && !bargingRef.current) void interrupter.stopRecording();
    };
  }, [streamState === "playing"]);

  useEffect(() => {
    if (stream.playbackState === "playing") {
      setStreamState("playing");
    } else if (
      stream.playbackState === "ended" ||
      stream.playbackState === "idle"
    ) {
      if (streamState === "playing") {
        setStreamState("idle");
      }
    }
  }, [stream.playbackState, streamState]);

  const isRecording = recorder.state === "recording";
  const isProcessing = streamState === "processing";
  const isPlaying = streamState === "playing";
  const isInterrupting = streamState === "interrupting";

  const { level } = useSpeechActivity(recorder.stream, {
    enabled: isRecording,
  });

  // What the rostrum is doing, pushed up for the chamber to draw. Recording is
  // the recorder's state rather than the stream's, so it has to be folded in
  // here — the stream knows nothing until the blob is posted.
  const liveState: LiveStage["state"] = isRecording ? "recording" : streamState;

  useEffect(() => {
    onStageChange?.({
      state: liveState,
      cue,
      caption,
      userTranscript,
      note,
    });
  }, [liveState, cue, caption, userTranscript, note, onStageChange]);

  const handleToggleRecord = async () => {
    if (recorder.state === "recording") {
      setStreamState("processing");
      try {
        const blob = await recorder.stopRecording();
        await stream.streamVoiceResponse(
          `/api/sessions/${sessionId}/voice-turns`,
          blob,
        );
      } catch (error) {
        setStreamState("idle");
        toast({
          variant: "destructive",
          title: "The microphone request failed",
          description: getErrorMessage(error),
        });
      }
    } else {
      try {
        setCue(null);
        setCaption("");
        setNote(null);
        setUserTranscript(null);
        await recorder.startRecording();
      } catch (error) {
        toast({
          variant: "destructive",
          title: "Microphone access is required",
          description: getErrorMessage(error),
        });
      }
    }
  };

  const isDock = variant === "dock";

  return (
    <div className={cn(isDock ? "space-y-2" : "space-y-4")}>
      {/* One control, and it says what pressing it does rather than what state
          the machine is in. Stamp while the record is open, because that is
          the one moment the student is on the record and needs to know it. */}
      <Button
        onClick={handleToggleRecord}
        disabled={disabled || isProcessing || isPlaying || isInterrupting}
        className={cn(
          "w-full justify-center rounded-sm text-sm",
          isDock ? "h-11 px-5" : "h-12",
          isRecording &&
            "border-stamp bg-stamp text-stamp-foreground hover:bg-stamp",
          isProcessing && "border-secondary-border bg-secondary text-foreground",
        )}
      >
        {isRecording ? (
          <>
            <Square className="h-4 w-4 fill-current" />
            <span>Sit down and yield</span>
          </>
        ) : isProcessing ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>The court is considering</span>
          </>
        ) : isPlaying || isInterrupting ? (
          <>
            <Volume2 className="h-4 w-4" />
            <span>The floor is theirs — speak to object</span>
          </>
        ) : (
          <>
            <Mic className="h-4 w-4" />
            <span>Take the rostrum</span>
          </>
        )}
      </Button>

      <div className={cn(isDock ? "" : "space-y-2")}>
        <LevelRule level={level} live={isRecording} />
        <div
          className={cn(
            "flex items-baseline justify-between gap-3",
            isDock && "hidden",
          )}
        >
          <span
            className={cn(
              "apparatus",
              isRecording ? "text-stamp" : "text-muted-foreground",
            )}
          >
            {isRecording
              ? "On the record"
              : isProcessing
                ? "Deliberating"
                : isPlaying
                  ? "Speaking"
                  : disabled
                    ? "Hearing concluded"
                    : "Ready"}
          </span>
          <span className="apparatus text-muted-foreground">
            {isPlaying ? "Interruption open" : ""}
          </span>
        </div>
      </div>

      {/* In the chamber these three are drawn by the courtroom's own subtitle
          bar, against the figure that is speaking. Rendering them here as well
          put the same warning on screen twice. */}
      {!isDock && isPlaying && cue && (
        <p className="apparatus truncate border-l-2 border-primary pl-3 text-primary">
          {speakerLabel(cue)} has the floor
        </p>
      )}

      {!isDock && note && (
        <p className="border-l-2 border-rule pl-3 font-serif text-sm leading-relaxed text-muted-foreground">
          {note}
        </p>
      )}

      {!isDock && cue && <LiveCaption cue={cue} text={caption} />}
    </div>
  );
}
