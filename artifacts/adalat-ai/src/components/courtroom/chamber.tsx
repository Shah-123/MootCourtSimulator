import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { StudentSide } from "@workspace/api-client-react";
import type { SessionPhase } from "@workspace/api-client-react";
import { cn } from "@/lib/utils";
import { phaseLabel } from "@/lib/format";
import { BenchEmblem, Figure } from "./figures";
import type { StageRole, StageState } from "./stage-state";

/**
 * The chamber.
 *
 * A 2.5D room rather than a 3D one, and that is a decision rather than a
 * shortcut. Everything the picture has to say — who is on their feet, whether
 * the box is occupied, how the bench just ruled — is said by lighting a
 * station and by moving a figure into a seat. A real engine (three.js, R3F)
 * would have bought free camera movement that nothing here uses, at the cost
 * of a WebGL context sitting alongside a live audio graph and a streaming
 * fetch on a student's laptop. Depth is done with layered planes, one shared
 * key light, and per-station scale/blur/brightness; only the desks and the
 * counsel tables take a real 3D transform, because a flat desktop is the one
 * thing that reads as a diagram instead of a room.
 *
 * The room never invents a state. Every prop here is derived in
 * `stage-state.ts` from turns the API returned or events the voice stream
 * sent.
 */

interface ChamberProps {
  stage: StageState;
  studentSide: StudentSide;
  phase: SessionPhase;
  /** Suspends ambient motion; the student has called a recess. */
  paused: boolean;
}

/** Four bars under whoever holds the floor. Reuses the record's wave keyframes. */
function SpeakingMeter({ tone }: { tone: "brass" | "stamp" | "seal" }) {
  return (
    <span
      className="flex h-3 items-end gap-[2px]"
      role="presentation"
      aria-hidden="true"
    >
      {[1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className={cn(
            "w-[2px] rounded-full",
            `animate-wave-${i}`,
            tone === "brass" && "bg-[var(--chamber-brass)]",
            tone === "stamp" && "bg-stamp",
            tone === "seal" && "bg-seal",
          )}
          style={{ height: "40%" }}
        />
      ))}
    </span>
  );
}

/** The engraved plate on the front of a desk. */
function NamePlate({
  title,
  subtitle,
  lit,
  speaking,
  tone = "brass",
}: {
  title: string;
  subtitle?: string;
  lit: boolean;
  speaking: boolean;
  tone?: "brass" | "stamp" | "seal";
}) {
  return (
    <div
      className={cn(
        "chamber-plate flex items-center justify-center gap-2 transition-all duration-300",
        lit && "chamber-plate--lit",
      )}
    >
      <span className="flex min-w-0 flex-col items-center leading-none">
        <span className="chamber-plate-title truncate">{title}</span>
        {subtitle && (
          <span className="chamber-plate-sub truncate">{subtitle}</span>
        )}
      </span>
      {speaking && <SpeakingMeter tone={tone} />}
    </div>
  );
}

/**
 * One place a person stands or sits.
 *
 * `depth` is the only thing that decides how far away a station reads: it
 * drives scale, atmospheric haze and how much of the key light reaches it, so
 * the bench at the back and the counsel table at the front cannot drift out of
 * agreement with each other.
 */
function Station({
  depth,
  active,
  children,
  className,
  style,
}: {
  depth: number;
  active: boolean;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <div
      className={cn("chamber-station", active && "chamber-station--active", className)}
      style={{ ["--depth" as string]: depth, ...style }}
    >
      {children}
    </div>
  );
}

export function Chamber({ stage, studentSide, phase, paused }: ChamberProps) {
  const reduce = useReducedMotion();
  const still = paused || Boolean(reduce);

  const studentLeft = studentSide === StudentSide.petitioner;
  const leftRole: StageRole = studentLeft ? "student" : "opposing";
  const rightRole: StageRole = studentLeft ? "opposing" : "student";

  const isActive = (role: StageRole) => stage.activeRole === role;
  const speaking = (role: StageRole) =>
    isActive(role) && stage.activity === "speaking";

  // The ruling flash fires once per ruling, not for as long as a ruling is the
  // latest one on the record — otherwise the room would sit washed green for
  // the rest of the hearing. The first key observed is deliberately swallowed:
  // opening a session that already contains a ruling should not stamp the room
  // as though the bench had just spoken.
  const [flash, setFlash] = useState<"sustained" | "overruled" | null>(null);
  const seenRuling = useRef<string | null | undefined>(undefined);

  // Deliberately two effects. Raising the stamp and taking it down again used
  // to be one, and its cleanup cancelled the timer whenever anything else in
  // the deps moved — the guard then swallowed the re-run, so the stamp stayed
  // across the room for the rest of the hearing. Splitting them means the
  // timer's lifetime is owned by `flash` alone and cannot be cancelled by a
  // ruling that has already been seen.
  useEffect(() => {
    const key = stage.rulingKey;
    if (seenRuling.current === key) return;
    const first = seenRuling.current === undefined;
    seenRuling.current = key;
    if (first || !key || !stage.lastRuling) return;
    setFlash(stage.lastRuling);
  }, [stage.rulingKey, stage.lastRuling]);

  useEffect(() => {
    if (!flash) return;
    const timer = window.setTimeout(() => setFlash(null), 1400);
    return () => window.clearTimeout(timer);
  }, [flash]);

  const spring = still
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 90, damping: 20, mass: 0.9 };

  return (
    <div
      className="chamber"
      data-paused={paused ? "" : undefined}
      role="img"
      aria-label={chamberDescription(stage, studentSide, phase)}
    >
      {/* ---- The room ------------------------------------------------- */}
      <div className="chamber-wall" />
      <div className="chamber-cornice" />
      <div className="chamber-floor" />

      {/* One key light over the bench, and the haze it hangs in. */}
      <div className={cn("chamber-shaft", still && "chamber-shaft--still")} />
      <div className="chamber-haze" />

      {/* ---- Gallery, behind the well of the court --------------------- */}
      <div className="chamber-gallery" aria-hidden="true">
        {[0, 1, 2].map((row) => (
          <div key={row} className="chamber-gallery-row" data-row={row} />
        ))}
      </div>

      {/* ---- The bench ------------------------------------------------ */}
      <BenchEmblem className="chamber-emblem" />

      <Station depth={0.16} active={isActive("judge")} className="chamber-bench-station">
        <motion.div
          className="chamber-figure chamber-figure--judge"
          animate={
            still
              ? undefined
              : speaking("judge")
                ? { y: [0, -2.5, 0] }
                : { y: 0 }
          }
          transition={{
            duration: 2.4,
            repeat: speaking("judge") ? Infinity : 0,
            ease: "easeInOut",
          }}
        >
          <Figure kind="judge" />
        </motion.div>

        {/* The dais front, drawn over the figure so the judge sits behind it. */}
        <div className="chamber-bench">
          <div className="chamber-bench-top">
            <span className="chamber-desk-papers" />
            <span className="chamber-gavel" />
            <span className="chamber-mic" />
          </div>
          <div className="chamber-bench-face">
            <NamePlate
              title="The Bench"
              subtitle="Presiding"
              lit={isActive("judge")}
              speaking={speaking("judge")}
            />
          </div>
        </div>

        {/* Thinking is the bench reading statute, and it takes seconds a
            student can feel. Saying nothing at all there reads as a hang. */}
        <AnimatePresence>
          {stage.activity === "thinking" && (
            <motion.div
              className="chamber-thinking"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.24 }}
            >
              <span className="chamber-thinking-dot" />
              <span className="chamber-thinking-dot" />
              <span className="chamber-thinking-dot" />
              <span className="apparatus">The court is considering</span>
            </motion.div>
          )}
        </AnimatePresence>
      </Station>

      {/* ---- The witness box ------------------------------------------ */}
      <Station depth={0.34} active={isActive("witness")} className="chamber-box-station">
        <div className="chamber-box">
          <AnimatePresence mode="wait">
            {stage.witnessOnStand ? (
              <motion.div
                key={stage.witnessOnStand}
                className="chamber-figure chamber-figure--witness"
                // Called to the stand: the witness walks in from the side of
                // the court rather than materialising in the box.
                initial={
                  still
                    ? { opacity: 1, x: 0 }
                    : { opacity: 0, x: 78, y: 10, scale: 0.94 }
                }
                animate={{ opacity: 1, x: 0, y: 0, scale: 1 }}
                exit={
                  still
                    ? { opacity: 0 }
                    : { opacity: 0, x: 54, transition: { duration: 0.28 } }
                }
                transition={spring}
              >
                <motion.div
                  animate={
                    still
                      ? undefined
                      : speaking("witness")
                        ? { y: [0, -2, 0] }
                        : { y: 0 }
                  }
                  transition={{
                    duration: 2.1,
                    repeat: speaking("witness") ? Infinity : 0,
                    ease: "easeInOut",
                  }}
                >
                  <Figure kind="witness" facing="left" />
                </motion.div>
              </motion.div>
            ) : null}
          </AnimatePresence>

          <div className="chamber-box-rail">
            <NamePlate
              title={stage.witnessOnStand ?? "Witness box"}
              subtitle={stage.witnessOnStand ? "Sworn" : "Vacant"}
              lit={isActive("witness")}
              speaking={speaking("witness")}
              tone="seal"
            />
          </div>
        </div>
      </Station>

      {/* ---- The clerk, in the well ----------------------------------- */}
      <Station depth={0.44} active={false} className="chamber-clerk-station">
        <div className="chamber-figure chamber-figure--clerk">
          <Figure kind="clerk" />
        </div>
        <div className="chamber-clerk-desk" />
      </Station>

      {/* ---- Counsel, either side of the well ------------------------- */}
      <CounselStation
        side="left"
        role={leftRole}
        label="For the petitioner"
        occupant={leftRole === "student" ? "You" : "Opposing counsel"}
        active={isActive(leftRole)}
        speaking={speaking(leftRole)}
        objecting={leftRole === "opposing" && stage.objectionPending}
        still={still}
      />
      <CounselStation
        side="right"
        role={rightRole}
        label="For the respondent"
        occupant={rightRole === "student" ? "You" : "Opposing counsel"}
        active={isActive(rightRole)}
        speaking={speaking(rightRole)}
        objecting={rightRole === "opposing" && stage.objectionPending}
        still={still}
      />

      {/* ---- Foreground: the rail the gallery sits behind -------------- */}
      <div className="chamber-foreground" aria-hidden="true" />
      <div className="chamber-vignette" aria-hidden="true" />

      {/* ---- The bench's disposition, stamped across the room ---------- */}
      <AnimatePresence>
        {flash && (
          <motion.div
            key={flash}
            className={cn(
              "chamber-ruling",
              flash === "sustained"
                ? "chamber-ruling--sustained"
                : "chamber-ruling--overruled",
            )}
            initial={still ? { opacity: 1 } : { opacity: 0, scale: 1.35 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.45 } }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          >
            <span className="chamber-ruling-word">{flash}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- Where the hearing has reached ---------------------------- */}
      <p className="chamber-phase apparatus">{phaseLabel(phase)}</p>
    </div>
  );
}

function CounselStation({
  side,
  role,
  label,
  occupant,
  active,
  speaking,
  objecting,
  still,
}: {
  side: "left" | "right";
  role: StageRole;
  label: string;
  occupant: string;
  active: boolean;
  speaking: boolean;
  objecting: boolean;
  still: boolean;
}) {
  return (
    <Station
      depth={0.72}
      active={active}
      className={cn(
        "chamber-counsel-station",
        side === "left"
          ? "chamber-counsel-station--left"
          : "chamber-counsel-station--right",
        objecting && "chamber-counsel-station--objecting",
      )}
    >
      <motion.div
        className="chamber-figure chamber-figure--counsel"
        // On their feet: counsel with the floor stands, the other stays seated
        // behind their table. It is the clearest signal in a real courtroom
        // and it costs one transform.
        animate={
          still
            ? undefined
            : active
              ? { y: -14, scale: 1.03 }
              : { y: 8, scale: 0.97 }
        }
        transition={{ type: "spring", stiffness: 110, damping: 18 }}
      >
        <motion.div
          animate={still ? undefined : speaking ? { y: [0, -2, 0] } : { y: 0 }}
          transition={{
            duration: 2.2,
            repeat: speaking ? Infinity : 0,
            ease: "easeInOut",
          }}
        >
          <Figure
            kind="advocate"
            facing={side === "left" ? "right" : "left"}
          />
        </motion.div>
      </motion.div>

      <div className="chamber-table">
        <div className="chamber-table-top">
          <span className="chamber-desk-papers" />
          <span className="chamber-desk-brief" />
        </div>
        <div className="chamber-table-face">
          <NamePlate
            title={label}
            subtitle={occupant}
            lit={active}
            speaking={speaking}
            tone={role === "opposing" && objecting ? "stamp" : "brass"}
          />
        </div>
      </div>
    </Station>
  );
}

/**
 * The room, in words.
 *
 * The chamber is decoration for a screen reader unless it says what it shows,
 * and a student using one still has to know who is on their feet and whether
 * the box is occupied. Announced politely by the caller, not by this string.
 */
function chamberDescription(
  stage: StageState,
  studentSide: StudentSide,
  phase: SessionPhase,
): string {
  const who =
    stage.activeRole === "judge"
      ? "the bench is speaking"
      : stage.activeRole === "opposing"
        ? "opposing counsel is speaking"
        : stage.activeRole === "student"
          ? "you have the floor"
          : stage.activeRole === "witness"
            ? stage.witnessOnStand
              ? `the witness ${stage.witnessOnStand} is answering`
              : "the witness is answering"
            : stage.activity === "thinking"
              ? "the court is considering"
              : "the court is waiting";

  const box = stage.witnessOnStand
    ? `${stage.witnessOnStand} is in the witness box`
    : "the witness box is empty";

  return `Courtroom. ${phaseLabel(phase)}. You appear for the ${studentSide}. ${who}; ${box}.`;
}
