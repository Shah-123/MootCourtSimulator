import { useEffect, useRef } from "react";
import type { Turn } from "@workspace/api-client-react";
import { ChamberPanel } from "./panel";
import { RecordEntry, parseTurn } from "./record";

/**
 * The record of proceedings, inside the courtroom.
 *
 * Renders `RecordEntry` rather than a courtroom-flavoured copy of it, so the
 * provenance rail — the citation and its ✓ Verified / ⚠ Unverified mark — is
 * literally the same component the written record uses. An overlay that quietly
 * dropped that rail would look tidier and be the one regression in this redesign
 * that actually matters.
 */
export function TranscriptPanel({
  open,
  onClose,
  turns,
  verifiedCitations,
}: {
  open: boolean;
  onClose: () => void;
  turns: Turn[];
  verifiedCitations: Set<string>;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    endRef.current?.scrollIntoView({ block: "end" });
  }, [open, turns.length]);

  return (
    <ChamberPanel
      open={open}
      onClose={onClose}
      side="right"
      title="Record of proceedings"
      meta={
        <p className="apparatus tabular-nums text-muted-foreground/70">
          {turns.length} {turns.length === 1 ? "entry" : "entries"}
        </p>
      }
    >
      {turns.length === 0 ? (
        <div className="flex min-h-[14rem] flex-col items-center justify-center px-4 text-center">
          <p className="display-sm">The record is open.</p>
          <p className="mt-3 font-serif leading-relaxed text-muted-foreground">
            Nothing has been said yet. Take the rostrum and make your
            appearance.
          </p>
        </div>
      ) : (
        <>
          <ol className="divide-y divide-rule/60">
            {turns.map((turn, index) => (
              <RecordEntry
                key={turn.id}
                index={index + 1}
                turn={parseTurn(turn)}
                verifiedCitations={verifiedCitations}
              />
            ))}
          </ol>
          <div ref={endRef} />
        </>
      )}
    </ChamberPanel>
  );
}
