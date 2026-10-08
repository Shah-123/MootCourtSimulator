import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { LiveCaption, speakerLabel } from "@/components/live-caption";
import type { LiveStage, StageState } from "./stage-state";

/**
 * What the court is saying, under the room that is saying it.
 *
 * While a turn is streaming this is `LiveCaption` verbatim — the same component
 * the sidebar used — because it is what carries the ⚠ unverified and ⚠ not-in-
 * corpus warnings beside the words as they are spoken. Speech cannot carry a
 * badge; this bar is where the badge goes, and it is the reason the caption was
 * not redrawn as a bare film subtitle when the courtroom got one.
 *
 * Between turns it falls back to the last line on the record, so the bar is not
 * empty in a room that has been arguing for ten minutes.
 */
export function SubtitleBar({
  stage,
  live,
}: {
  stage: StageState;
  live: LiveStage;
}) {
  const reduce = useReducedMotion();
  const hasLive = Boolean(live.cue);
  const showing = hasLive || Boolean(stage.captionText) || Boolean(live.note);

  return (
    <div className="chamber-subtitle" aria-live="polite">
      <AnimatePresence mode="wait">
        {showing && (
          <motion.div
            key={live.cue ? speakerLabel(live.cue) : (stage.captionSpeaker ?? "record")}
            className="chamber-subtitle-card"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
            transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
          >
            {live.cue ? (
              <LiveCaption cue={live.cue} text={live.caption} />
            ) : (
              <div className="record-entry py-2 pr-2">
                {stage.captionSpeaker && (
                  <p className="apparatus text-muted-foreground">
                    {stage.captionSpeaker}
                  </p>
                )}
                <p className="mt-1 line-clamp-3 font-serif text-sm leading-relaxed text-foreground/85">
                  {stage.captionText}
                </p>
              </div>
            )}

            {live.note && (
              <p className="mt-2 border-l-2 border-rule pl-3 font-serif text-sm leading-relaxed text-muted-foreground">
                {live.note}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
