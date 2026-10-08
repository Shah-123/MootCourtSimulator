import React from "react";
import { cn } from "@/lib/utils";

interface LogoProps extends React.SVGProps<SVGSVGElement> {
  size?: "sm" | "md" | "lg" | number;
  className?: string;
}

/**
 * Sovereign Scales & Voice Resonance Insignia Mark for CourtSimulator (Adalat AI)
 * Designed for Pakistan Superior Judiciary Moot Chamber.
 */
export function CourtLogoMark({ size = "md", className, ...props }: LogoProps) {
  const pixelSize =
    typeof size === "number"
      ? size
      : size === "sm"
      ? 28
      : size === "lg"
      ? 48
      : 36;

  return (
    <svg
      width={pixelSize}
      height={pixelSize}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("shrink-0 transition-transform duration-200 group-hover:scale-105", className)}
      aria-label="CourtSimulator Insignia"
      {...props}
    >
      <defs>
        <radialGradient id="markBgGrad" cx="50%" cy="30%" r="70%">
          <stop offset="0%" stopColor="#35205A" />
          <stop offset="70%" stopColor="#1B1231" />
          <stop offset="100%" stopColor="#0D091A" />
        </radialGradient>

        <linearGradient id="markGoldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#FDE68A" />
          <stop offset="35%" stopColor="#D4AF37" />
          <stop offset="70%" stopColor="#A17C14" />
          <stop offset="100%" stopColor="#F5D76E" />
        </linearGradient>

        <linearGradient id="markVioletGlow" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#9333EA" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#4C1D95" stopOpacity="0" />
        </linearGradient>

        <filter id="markDropShadow" x="-10%" y="-10%" width="120%" height="120%">
          <feDropShadow dx="0" dy="2" stdDeviation="2" floodColor="#000000" floodOpacity="0.45" />
        </filter>
      </defs>

      {/* Outer Squircle Plaque */}
      <rect width="100" height="100" rx="22" fill="url(#markBgGrad)" />
      <rect
        width="98"
        height="98"
        x="1"
        y="1"
        rx="21"
        stroke="url(#markGoldGrad)"
        strokeWidth="1.2"
        strokeOpacity="0.5"
      />
      <rect
        width="92"
        height="92"
        x="4"
        y="4"
        rx="18"
        stroke="#A855F7"
        strokeWidth="0.8"
        strokeOpacity="0.3"
      />

      {/* Judicial Arch Silhouette */}
      <path d="M 22 84 V 42 A 28 28 0 0 1 78 42 V 84 Z" fill="url(#markVioletGlow)" />
      <path
        d="M 26 83 V 43 A 24 24 0 0 1 74 43 V 83"
        stroke="url(#markGoldGrad)"
        strokeWidth="0.8"
        strokeOpacity="0.3"
        strokeDasharray="2 2"
      />

      {/* Acoustic Voice Waveform Resonance */}
      <g opacity="0.85" filter="url(#markDropShadow)">
        <rect x="34" y="44" width="2.2" height="14" rx="1.1" fill="url(#markGoldGrad)" opacity="0.5" />
        <rect x="39" y="39" width="2.2" height="24" rx="1.1" fill="url(#markGoldGrad)" opacity="0.75" />
        <rect x="44" y="34" width="2.2" height="34" rx="1.1" fill="url(#markGoldGrad)" opacity="0.95" />
        <rect x="54" y="34" width="2.2" height="34" rx="1.1" fill="url(#markGoldGrad)" opacity="0.95" />
        <rect x="59" y="39" width="2.2" height="24" rx="1.1" fill="url(#markGoldGrad)" opacity="0.75" />
        <rect x="64" y="44" width="2.2" height="14" rx="1.1" fill="url(#markGoldGrad)" opacity="0.5" />
      </g>

      {/* Central Pillar Sceptre */}
      <path
        d="M 40 80 H 60 V 78 C 60 76.5 58 76 56 76 H 44 C 42 76 40 76.5 40 78 Z"
        fill="url(#markGoldGrad)"
        filter="url(#markDropShadow)"
      />
      <rect x="49" y="26" width="2.2" height="52" rx="1.1" fill="url(#markGoldGrad)" />

      {/* Finial Star at Apex */}
      <path
        d="M 50 14 L 51.5 18 L 56 18.5 L 52.5 21.5 L 53.5 26 L 50 23.5 L 46.5 26 L 47.5 21.5 L 44 18.5 L 48.5 18 Z"
        fill="url(#markGoldGrad)"
        filter="url(#markDropShadow)"
      />

      {/* Scales Crossbeam (Meezan) */}
      <path
        d="M 24 38 C 36 34.5 45 29 50 29 C 55 29 64 34.5 76 38"
        stroke="url(#markGoldGrad)"
        strokeWidth="2.4"
        strokeLinecap="round"
        fill="none"
        filter="url(#markDropShadow)"
      />
      <circle cx="50" cy="29" r="2.5" fill="#1B1231" stroke="url(#markGoldGrad)" strokeWidth="1.5" />
      <circle cx="24" cy="38" r="1.8" fill="url(#markGoldGrad)" />
      <circle cx="76" cy="38" r="1.8" fill="url(#markGoldGrad)" />

      {/* Left Pan */}
      <g filter="url(#markDropShadow)">
        <line x1="24" y1="38" x2="16" y2="60" stroke="url(#markGoldGrad)" strokeWidth="0.9" strokeOpacity="0.8" />
        <line x1="24" y1="38" x2="32" y2="60" stroke="url(#markGoldGrad)" strokeWidth="0.9" strokeOpacity="0.8" />
        <path d="M 14 60 C 14 68 34 68 34 60 Z" fill="url(#markGoldGrad)" />
        <line x1="13" y1="60" x2="35" y2="60" stroke="url(#markGoldGrad)" strokeWidth="1.2" strokeLinecap="round" />
      </g>

      {/* Right Pan */}
      <g filter="url(#markDropShadow)">
        <line x1="76" y1="38" x2="68" y2="60" stroke="url(#markGoldGrad)" strokeWidth="0.9" strokeOpacity="0.8" />
        <line x1="76" y1="38" x2="84" y2="60" stroke="url(#markGoldGrad)" strokeWidth="0.9" strokeOpacity="0.8" />
        <path d="M 66 60 C 66 68 86 68 86 60 Z" fill="url(#markGoldGrad)" />
        <line x1="65" y1="60" x2="87" y2="60" stroke="url(#markGoldGrad)" strokeWidth="1.2" strokeLinecap="round" />
      </g>
    </svg>
  );
}

/**
 * Full Brand Lockup with Insignia and Court Record Typography
 */
export function CourtLogo({
  size = "md",
  className,
  showSubtext = true,
}: {
  size?: "sm" | "md" | "lg";
  className?: string;
  showSubtext?: boolean;
}) {
  return (
    <div className={cn("group flex items-center gap-3", className)}>
      <CourtLogoMark size={size} />
      <div className="flex flex-col">
        <span className="whitespace-nowrap font-serif text-[1.375rem] font-normal leading-none tracking-[-0.02em] text-foreground">
          CourtSimulator
        </span>
        {showSubtext && (
          <span className="apparatus mt-1 text-[0.75rem] text-muted-foreground tracking-wider">
            Pakistan superior judiciary
          </span>
        )}
      </div>
    </div>
  );
}
