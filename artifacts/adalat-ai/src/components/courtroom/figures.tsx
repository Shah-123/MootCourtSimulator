import { useId } from "react";

/**
 * The people in the room.
 *
 * Drawn as tonal sculpture rather than as characters: no faces, no expressions,
 * no cartoon proportions. A moot court is a formal room and the figures in it
 * are read by *dress and position* — the bench's robe and bands, an advocate's
 * black coat and white collar, a witness in ordinary clothes standing where the
 * box is. Giving them features would have made the chamber a game; leaving them
 * as lit silhouettes keeps the eye on who is speaking, which is the only thing
 * this drawing has to communicate.
 *
 * Every fill is a chamber token so both themes and the ambient key light reach
 * the figures without a second palette to keep in step.
 */

export type FigureKind = "judge" | "advocate" | "witness" | "clerk";

interface FigureProps {
  kind: FigureKind;
  /** Advocates read left or right so the two counsel do not mirror exactly. */
  facing?: "left" | "right" | "front";
  className?: string;
}

export function Figure({ kind, facing = "front", className }: FigureProps) {
  const uid = useId().replace(/:/g, "");
  const robe = `robe-${uid}`;
  const key = `key-${uid}`;
  const skin = `skin-${uid}`;

  const lean = facing === "left" ? -3 : facing === "right" ? 3 : 0;

  return (
    <svg
      viewBox="0 0 120 150"
      className={className}
      role="presentation"
      aria-hidden="true"
      style={{ overflow: "visible" }}
    >
      <defs>
        <linearGradient id={robe} x1="0" y1="0" x2="0.35" y2="1">
          <stop offset="0%" stopColor="var(--figure-cloth-lit)" />
          <stop offset="55%" stopColor="var(--figure-cloth)" />
          <stop offset="100%" stopColor="var(--figure-cloth-shadow)" />
        </linearGradient>
        <linearGradient id={skin} x1="0.2" y1="0" x2="0.8" y2="1">
          <stop offset="0%" stopColor="var(--figure-skin-lit)" />
          <stop offset="100%" stopColor="var(--figure-skin)" />
        </linearGradient>
        {/* The key light falls from above and in front of the bench, so every
            figure carries the same highlight on the same shoulder. */}
        <radialGradient id={key} cx="0.42" cy="0.12" r="0.85">
          <stop offset="0%" stopColor="var(--chamber-key)" stopOpacity="0.5" />
          <stop offset="100%" stopColor="var(--chamber-key)" stopOpacity="0" />
        </radialGradient>
      </defs>

      <g transform={`rotate(${lean} 60 140)`}>
        {kind === "judge" && <JudgeBody robe={robe} skin={skin} />}
        {kind === "advocate" && <AdvocateBody robe={robe} skin={skin} />}
        {kind === "witness" && <WitnessBody robe={robe} skin={skin} />}
        {kind === "clerk" && <ClerkBody robe={robe} skin={skin} />}
        <rect x="0" y="0" width="120" height="150" fill={`url(#${key})`} />
      </g>
    </svg>
  );
}

/** Black robe, wing collar and white bands — the bench of a superior court. */
function JudgeBody({ robe, skin }: { robe: string; skin: string }) {
  return (
    <g>
      {/* Robe: broad shoulders, sleeves falling to the bench top. */}
      <path
        d="M60 52 C 44 52 33 60 27 74 C 21 89 17 112 15 150 L 105 150 C 103 112 99 89 93 74 C 87 60 76 52 60 52 Z"
        fill={`url(#${robe})`}
      />
      {/* Yoke seam — the fold that tells a robe from a coat. */}
      <path
        d="M32 72 C 42 84 46 108 46 150 M88 72 C 78 84 74 108 74 150"
        stroke="var(--figure-cloth-shadow)"
        strokeWidth="1.4"
        fill="none"
        opacity="0.75"
      />
      {/* Wing collar. */}
      <path
        d="M48 54 L60 76 L72 54 L66 50 L60 60 L54 50 Z"
        fill="var(--figure-linen)"
      />
      {/* The two bands. */}
      <rect x="55.6" y="61" width="3.6" height="13" rx="0.7" fill="var(--figure-linen)" />
      <rect x="60.8" y="61" width="3.6" height="13" rx="0.7" fill="var(--figure-linen)" />
      <path d="M52 50 L60 61 L68 50 Z" fill="var(--figure-cloth-shadow)" opacity="0.5" />
      {/* Neck and head. */}
      <path d="M53 38 h14 v14 h-14 z" fill="var(--figure-skin-shadow)" />
      <ellipse cx="60" cy="27" rx="14.5" ry="16.5" fill={`url(#${skin})`} />
      {/* Hair, close-cropped and grey — the bench is the senior figure here. */}
      <path
        d="M45.6 25 C 45 13 51 6 60 6 C 69 6 75 13 74.4 25 C 71 18 66 14.5 60 14.5 C 54 14.5 49 18 45.6 25 Z"
        fill="var(--figure-hair-grey)"
      />
    </g>
  );
}

/** Black coat, white shirt, black tie — an advocate's court dress. */
function AdvocateBody({ robe, skin }: { robe: string; skin: string }) {
  return (
    <g>
      <path
        d="M60 54 C 47 54 38 60 33 71 C 28 83 25 108 24 150 L 96 150 C 95 108 92 83 87 71 C 82 60 73 54 60 54 Z"
        fill={`url(#${robe})`}
      />
      {/* Shirt front between the lapels. */}
      <path d="M52 55 L60 70 L68 55 L60 51 Z" fill="var(--figure-linen)" />
      {/* Lapels. */}
      <path
        d="M52 55 L60 70 L54 78 L45 62 Z"
        fill="var(--figure-cloth-shadow)"
        opacity="0.85"
      />
      <path
        d="M68 55 L60 70 L66 78 L75 62 Z"
        fill="var(--figure-cloth-shadow)"
        opacity="0.85"
      />
      {/* Tie. */}
      <path d="M60 62 L63 68 L60 82 L57 68 Z" fill="var(--figure-tie)" />
      {/* Sleeve seams. */}
      <path
        d="M35 70 C 41 84 43 112 43 150 M85 70 C 79 84 77 112 77 150"
        stroke="var(--figure-cloth-shadow)"
        strokeWidth="1.2"
        fill="none"
        opacity="0.7"
      />
      <path d="M53 40 h14 v14 h-14 z" fill="var(--figure-skin-shadow)" />
      <ellipse cx="60" cy="29" rx="14" ry="16" fill={`url(#${skin})`} />
      <path
        d="M46 27 C 45.5 15 51 8.5 60 8.5 C 69 8.5 74.5 15 74 27 C 71 20 66 16.5 60 16.5 C 54 16.5 49 20 46 27 Z"
        fill="var(--figure-hair)"
      />
    </g>
  );
}

/** Ordinary clothes. A witness is not an officer of the court. */
function WitnessBody({ robe, skin }: { robe: string; skin: string }) {
  return (
    <g>
      {/* A plain kameez: straight shoulders, no lapel, a soft standing collar. */}
      <path
        d="M60 55 C 48 55 40 61 36 71 C 32 82 30 110 29 150 L 91 150 C 90 110 88 82 84 71 C 80 61 72 55 60 55 Z"
        fill="var(--figure-plain)"
      />
      <path
        d="M60 55 C 48 55 40 61 36 71 C 32 82 30 110 29 150 L 91 150 C 90 110 88 82 84 71 C 80 61 72 55 60 55 Z"
        fill={`url(#${robe})`}
        opacity="0.28"
      />
      {/* Placket down the front. */}
      <path
        d="M60 66 L60 150"
        stroke="var(--figure-plain-shadow)"
        strokeWidth="1.3"
        opacity="0.8"
      />
      {/* Standing collar. */}
      <path
        d="M52 56 L60 66 L68 56 L64 52 L60 57 L56 52 Z"
        fill="var(--figure-plain-shadow)"
      />
      <path d="M53 41 h14 v14 h-14 z" fill="var(--figure-skin-shadow)" />
      <ellipse cx="60" cy="30" rx="14" ry="16" fill={`url(#${skin})`} />
      <path
        d="M46 28 C 45.5 16 51 9.5 60 9.5 C 69 9.5 74.5 16 74 28 C 71 21 66 17.5 60 17.5 C 54 17.5 49 21 46 28 Z"
        fill="var(--figure-hair)"
      />
    </g>
  );
}

/** The stenographer at the well of the court, seated and lower. */
function ClerkBody({ robe, skin }: { robe: string; skin: string }) {
  return (
    <g>
      <path
        d="M60 70 C 49 70 42 76 38 86 C 34 96 32 118 31 150 L 89 150 C 88 118 86 96 82 86 C 78 76 71 70 60 70 Z"
        fill={`url(#${robe})`}
      />
      <path d="M53 57 h14 v13 h-14 z" fill="var(--figure-skin-shadow)" />
      <ellipse cx="60" cy="47" rx="12.5" ry="14.5" fill={`url(#${skin})`} />
      <path
        d="M47.5 45 C 47 34 52 28 60 28 C 68 28 73 34 72.5 45 C 70 39 65.5 36 60 36 C 54.5 36 50 39 47.5 45 Z"
        fill="var(--figure-hair)"
      />
    </g>
  );
}

/**
 * The scales roundel above the bench.
 *
 * Deliberately a generic emblem of justice rather than any real court's arms
 * or the state emblem: this is a teaching simulator, and putting a genuine
 * insignia on it would dress a practice room as an actual court.
 */
export function BenchEmblem({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden="true">
      <circle
        cx="50"
        cy="50"
        r="46"
        fill="none"
        stroke="var(--chamber-brass)"
        strokeWidth="1.6"
        opacity="0.7"
      />
      <circle
        cx="50"
        cy="50"
        r="39"
        fill="none"
        stroke="var(--chamber-brass)"
        strokeWidth="0.8"
        opacity="0.45"
      />
      <g
        stroke="var(--chamber-brass)"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
        opacity="0.85"
      >
        <path d="M50 26 v46" />
        <path d="M30 36 h40" />
        <path d="M38 78 h24" />
        <path d="M30 36 l-8 15 h16 z" />
        <path d="M70 36 l-8 15 h16 z" />
      </g>
      <circle cx="50" cy="26" r="3" fill="var(--chamber-brass)" opacity="0.9" />
    </svg>
  );
}
