import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * A slide-over that does not take the room away.
 *
 * Deliberately *not* a Radix Dialog. A modal would dim and inert the chamber,
 * and the two panels a student opens most — the record and the case file — are
 * exactly the ones they want open *while* the bench is speaking. So this is
 * non-modal: no focus trap, no scrim over the scene, Escape still closes, and
 * the courtroom keeps animating behind it. The cost is that it cannot be used
 * for anything requiring a decision before the hearing continues; the objection
 * and call-witness dialogs stay Radix modals for that reason.
 */
export function ChamberPanel({
  open,
  onClose,
  side,
  title,
  meta,
  children,
}: {
  open: boolean;
  onClose: () => void;
  side: "left" | "right";
  title: string;
  meta?: ReactNode;
  children: ReactNode;
}) {
  const reduce = useReducedMotion();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Moving focus into the panel is what makes it reachable by keyboard at all;
  // without it a student tabbing from the dock lands behind the courtroom.
  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open]);

  const offset = side === "left" ? -32 : 32;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          ref={panelRef}
          tabIndex={-1}
          role="dialog"
          aria-modal="false"
          aria-label={title}
          className={cn(
            "chamber-panel",
            side === "left" ? "chamber-panel--left" : "chamber-panel--right",
          )}
          initial={reduce ? { opacity: 0 } : { opacity: 0, x: offset }}
          animate={{ opacity: 1, x: 0 }}
          exit={reduce ? { opacity: 0 } : { opacity: 0, x: offset }}
          transition={{ duration: 0.26, ease: [0.16, 1, 0.3, 1] }}
        >
          <header className="flex items-start justify-between gap-3 border-b border-rule px-4 py-3">
            <div className="min-w-0">
              <h2 className="apparatus text-muted-foreground">{title}</h2>
              {meta && <div className="mt-1">{meta}</div>}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label={`Close ${title}`}
              className="-mr-1 shrink-0 cursor-pointer rounded-sm p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            {children}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
