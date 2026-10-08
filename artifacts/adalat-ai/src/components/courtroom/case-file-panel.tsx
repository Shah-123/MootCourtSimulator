import type { Case } from "@workspace/api-client-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CaseBriefArgument } from "@/components/case-brief";
import { ChamberPanel } from "./panel";

/**
 * The case file, as counsel would have it open on the table.
 *
 * Same three sections the session page carried in its sidebar — brief,
 * witnesses, provisions — moved into the chamber as an overlay so the room can
 * have the screen. Nothing new is fetched: every field here was already on the
 * session the page had.
 */
export function CaseFilePanel({
  open,
  onClose,
  courtCase,
  witnessOnStand,
}: {
  open: boolean;
  onClose: () => void;
  courtCase: Case;
  witnessOnStand: string | null;
}) {
  return (
    <ChamberPanel
      open={open}
      onClose={onClose}
      side="left"
      title="Case file"
      meta={
        <p className="font-serif text-base leading-snug text-foreground">
          {courtCase.title}
        </p>
      }
    >
      <Tabs defaultValue="brief" className="flex min-h-0 flex-col">
        <TabsList>
          <TabsTrigger value="brief">Brief</TabsTrigger>
          <TabsTrigger value="witnesses">
            Witnesses ({courtCase.witnesses?.length ?? 0})
          </TabsTrigger>
          <TabsTrigger value="statutes">Statutes</TabsTrigger>
        </TabsList>

        <TabsContent value="brief" className="pr-1">
          <p className="font-serif leading-relaxed text-foreground/85">
            {courtCase.summary}
          </p>
          {courtCase.brief && <CaseBriefArgument brief={courtCase.brief} />}
        </TabsContent>

        <TabsContent value="witnesses" className="pr-1">
          <ul className="divide-y divide-rule/70">
            {courtCase.witnesses?.map((w, idx) => (
              <li key={idx} className="py-3 first:pt-0">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-serif text-foreground">{w.name}</span>
                  <span className="apparatus shrink-0 text-muted-foreground">
                    {/* Says which of them is actually in the box, because the
                        list and the room have to agree. */}
                    {w.name === witnessOnStand ? "In the box" : w.role}
                  </span>
                </div>
                <p className="mt-1 font-serif text-sm italic leading-relaxed text-foreground/75">
                  “{w.statement}”
                </p>
              </li>
            ))}
          </ul>
        </TabsContent>

        <TabsContent value="statutes" className="pr-1">
          <p className="apparatus text-muted-foreground">Provisions in play</p>
          <p className="mt-2 font-mono text-xs leading-relaxed text-foreground/85">
            {courtCase.applicableLaws}
          </p>

          {courtCase.citations.length > 0 && (
            <ul className="mt-4 divide-y divide-rule/70 border-t border-rule pt-1">
              {courtCase.citations.map((citation) => (
                <li
                  key={citation.citation}
                  className="flex items-baseline justify-between gap-3 py-2"
                >
                  <span className="min-w-0">
                    <span className="font-mono text-xs text-foreground">
                      {citation.citation}
                    </span>
                    <span className="ml-2 font-serif text-sm text-muted-foreground">
                      {citation.heading}
                    </span>
                  </span>
                  {/* Per provision, never per instrument: two sections of the
                      same Act can differ here and a student is entitled to see
                      which one has actually been checked. */}
                  <span
                    className={
                      citation.verified
                        ? "apparatus shrink-0 text-seal"
                        : "apparatus shrink-0 text-stamp"
                    }
                    title={
                      citation.verified
                        ? "Diffed word-for-word against its official source."
                        : "This provision's text has not been checked against pakistancode.gov.pk. Do not quote it as authoritative."
                    }
                  >
                    {citation.verified ? "✓ Verified" : "⚠ Unverified"}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <p className="mt-4 border-t border-rule pt-3 font-serif text-sm leading-relaxed text-muted-foreground">
            Every citation either side makes is checked against the corpus
            before it reaches the record. One that is not in it is marked as
            such.
          </p>
        </TabsContent>
      </Tabs>
    </ChamberPanel>
  );
}
