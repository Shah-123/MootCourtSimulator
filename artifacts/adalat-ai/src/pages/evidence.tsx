import {
  CORPUS,
  CORPUS_CHECKED_ON,
  FINDINGS,
  MEASURED_ON,
  SECTIONS,
  type Freshness,
  type Section,
} from "@/data/evidence";
import { cn } from "@/lib/utils";

/**
 * What has actually been measured, and by which command.
 *
 * The page every claim in this project has to survive, so it is set as a
 * report of findings: the figure, the command that produced it, and the caveat
 * where there is one. It was a stack of gradient-filled cards with an icon in a
 * tinted square per section, which made a page of measurements look like a
 * marketing sheet — the one impression this particular page cannot afford.
 */
export default function EvidencePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-12 pb-20">
      <header className="masthead-rule pb-7">
        <p className="apparatus flex flex-wrap items-center gap-x-2 gap-y-1 text-muted-foreground">
          <span>Evidence</span>
          <span aria-hidden="true">·</span>
          <span>Measured {MEASURED_ON}</span>
        </p>

        <h1 className="display mt-4">What has been measured</h1>

        <p className="standfirst mt-5">
          Every figure below comes from a golden set and a command you can run
          again. Where a number is noisy across runs, the caveat says so rather
          than quoting the best one.
        </p>
      </header>

      {/* The corpus. The one figure on this page that is about the law rather
          than about the system reading it. */}
      <section>
        <h2 className="rule-heading">
          <span>The statutory corpus</span>
          <Command>{CORPUS.command}</Command>
        </h2>

        <p className="mt-6 font-serif text-[2rem] leading-tight tracking-[-0.018em] text-foreground">
          <span className="tabular-nums text-seal">{CORPUS.confirmed}</span>
          <span className="text-muted-foreground"> of </span>
          <span className="tabular-nums">{CORPUS.total}</span> provisions diffed
          word-for-word against their official source
        </p>

        <div className="mt-6 grid grid-cols-2 divide-y divide-rule border-y border-rule sm:grid-cols-4 sm:divide-x sm:divide-y-0">
          {CORPUS.statutes.map((statute) => (
            <div key={statute.code} className="px-0 py-4 sm:px-5 sm:first:pl-0">
              <p className="apparatus text-muted-foreground">{statute.code}</p>
              <p className="mt-1.5 font-serif text-2xl leading-none tabular-nums text-foreground">
                {statute.confirmed}
                <span className="text-sm text-muted-foreground">
                  /{statute.total}
                </span>
              </p>
            </div>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-baseline justify-between gap-3">
          <FreshnessMark
            freshness={CORPUS.freshness}
            checkedOn={CORPUS_CHECKED_ON}
            measuredTitle={`Counted against per-provision flags in the statute files as they stand, ${CORPUS_CHECKED_ON}.`}
          />
        </div>

        {/* The note runs at length rather than being rounded to a tick.
            Nothing is outstanding now, but how the last article closed — and
            which article the same run caught going the other way — is the
            answer to "how do you know your law is right?". */}
        <p className="mt-4 border-l-2 border-rule pl-4 font-serif leading-relaxed text-muted-foreground">
          {CORPUS.note}
        </p>
      </section>

      <section className="space-y-10">
        <h2 className="rule-heading">
          <span>What the harnesses return</span>
          <span className="tabular-nums">{SECTIONS.length}</span>
        </h2>

        {SECTIONS.map((section) => (
          <EvidenceSection key={section.id} section={section} />
        ))}
      </section>

      <section>
        <h2 className="rule-heading">
          <span>What the measurements changed</span>
        </h2>

        <ol className="divide-y divide-rule/70">
          {FINDINGS.map((finding, index) => (
            <li
              key={finding.title}
              className="grid gap-x-5 gap-y-1 py-5 sm:grid-cols-[2.5rem_1fr]"
            >
              <span className="apparatus pt-1 tabular-nums text-muted-foreground">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <h3 className="font-serif text-lg font-normal leading-snug text-foreground">
                  {finding.title}
                </h3>
                <p className="mt-1.5 font-serif leading-relaxed text-muted-foreground">
                  {finding.body}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

/** The command behind a figure, set as the command it is. */
function Command({ children }: { children: React.ReactNode }) {
  return (
    <code className="font-mono text-[0.6875rem] normal-case tracking-normal text-muted-foreground">
      {children}
    </code>
  );
}

/**
 * Whether the figure beside it was re-run against the current code.
 *
 * Both states were stamped, seal for measured and vermilion for a recorded
 * baseline, which borrowed the objection colour to say "this number is a
 * little older" — vermilion is reserved for a provision nobody has checked.
 * The caution stays on the baseline as a ⚠, because a figure that was not
 * re-run for this build is exactly the sort of thing a panel should be told
 * before it is quoted; only the colour is given back.
 */
function FreshnessMark({
  freshness,
  checkedOn,
  measuredTitle,
}: {
  freshness: Freshness;
  checkedOn?: string;
  measuredTitle?: string;
}) {
  const isMeasured = freshness === "measured";

  return (
    <span
      className={cn("apparatus", isMeasured ? "text-seal" : "text-muted-foreground")}
      title={
        isMeasured
          ? (measuredTitle ?? "Re-run against current code.")
          : "Recorded metric — not re-run for this build."
      }
    >
      {isMeasured
        ? `✓ Re-run${checkedOn ? ` ${checkedOn}` : ""}`
        : "⚠ Recorded baseline — not re-run for this build"}
    </span>
  );
}

function EvidenceSection({ section }: { section: Section }) {
  return (
    <article className="border-t border-rule pt-6 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="font-serif text-xl font-normal leading-snug text-foreground">
          {section.title}
        </h3>
        <Command>{section.command}</Command>
      </div>

      {/* The question the harness was built to answer, in the words it would
          be asked in a viva. */}
      <p className="mt-2 max-w-2xl font-serif italic leading-relaxed text-muted-foreground">
        {section.question}
      </p>

      <dl className="mt-5 grid grid-cols-2 divide-y divide-rule border-y border-rule sm:grid-cols-4 sm:divide-x sm:divide-y-0">
        {section.metrics.map((metric) => (
          <div key={metric.label} className="px-0 py-4 sm:px-5 sm:first:pl-0">
            <dt className="apparatus text-muted-foreground">{metric.label}</dt>
            <dd className="mt-1.5 font-serif text-2xl leading-none tabular-nums text-foreground">
              {metric.value}
            </dd>
            {metric.note && (
              <dd className="mt-1.5 text-xs leading-snug text-muted-foreground">
                {metric.note}
              </dd>
            )}
          </div>
        ))}
      </dl>

      <div className="mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-2">
        <FreshnessMark freshness={section.freshness} />
      </div>

      {/* A caveat keeps the stamp rule: it is the page saying do not quote
          this number on its own, which is the same warning the record gives
          for an unchecked provision. */}
      {section.caveat && (
        <p className="mt-4 border-l-2 border-stamp pl-4 font-serif leading-relaxed text-foreground/85">
          <span className="apparatus mr-2 text-stamp">Caveat</span>
          {section.caveat}
        </p>
      )}
    </article>
  );
}
