import { pgTable, text, serial, timestamp, jsonb } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const witnessSchema = z.object({
  name: z.string(),
  role: z.string(),
  statement: z.string(),
});

export type Witness = z.infer<typeof witnessSchema>;

/**
 * A provision the case is grounded in, resolved against the statute corpus
 * at generation time. Unlike the free-text `applicableLaws` string, every
 * entry here has been confirmed to exist.
 */
export const statuteCitationSchema = z.object({
  citation: z.string(),
  statuteCode: z.string(),
  heading: z.string(),
  /** Whether the corpus text was diffed against the official source. */
  verified: z.boolean(),
});

export type StatuteCitation = z.infer<typeof statuteCitationSchema>;

/** One numbered fact, lettered ground, or itemised prayer. */
export const briefItemSchema = z.object({
  /** Assigned server-side so labels stay contiguous when an item is dropped. */
  label: z.string(),
  text: z.string(),
});

export type BriefItem = z.infer<typeof briefItemSchema>;

export const casePartySchema = z.object({
  name: z.string(),
  role: z.string(),
  description: z.string(),
});

export type CaseParty = z.infer<typeof casePartySchema>;

/**
 * The pleading behind a case: what is averred, argued, and asked for.
 *
 * `summary` stays the short orientation paragraph; this is the structure a
 * student actually argues from — grounds are the argument, prayer is the relief.
 * The scalar `petitionerName` / `respondentName` columns keep the lead party, so
 * everything reading a case before this existed is unaffected.
 */
export const caseBriefSchema = z.object({
  court: z.string().nullable(),
  caseNumber: z.string().nullable(),
  jurisdictionInvoked: z.string().nullable(),
  petitioners: z.array(casePartySchema),
  respondents: z.array(casePartySchema),
  facts: z.array(briefItemSchema),
  grounds: z.array(briefItemSchema),
  prayer: z.array(briefItemSchema),
});

export type CaseBriefDetail = z.infer<typeof caseBriefSchema>;

export const casesTable = pgTable("cases", {
  id: serial("id").primaryKey(),
  title: text("title").notNull(),
  areaOfLaw: text("area_of_law").notNull(),
  difficulty: text("difficulty").notNull(),
  /**
   * How the matter is heard, which decides the phases a session on this case
   * runs through and whether evidentiary objections apply at all.
   *
   * Defaulted to "trial" rather than made nullable: every case that predates
   * proceeding types is a trial, and that is a fact about them, not missing
   * information. A null here would force every reader to invent the same
   * fallback, and one of them would eventually invent a different one.
   */
  proceedingType: text("proceeding_type").notNull().default("trial"),
  summary: text("summary").notNull(),
  applicableLaws: text("applicable_laws").notNull(),
  petitionerName: text("petitioner_name").notNull(),
  petitionerRole: text("petitioner_role").notNull(),
  respondentName: text("respondent_name").notNull(),
  respondentRole: text("respondent_role").notNull(),
  witnesses: jsonb("witnesses").$type<Witness[]>().notNull().default([]),
  /**
   * Provisions resolved against the statute corpus. `applicableLaws` stays as
   * the human-readable string the UI shows; this is the machine-checked list
   * behind it.
   */
  citations: jsonb("citations")
    .$type<StatuteCitation[]>()
    .notNull()
    .default([]),
  /**
   * Nullable with no default, deliberately. Library cases and every case
   * generated before the brief existed genuinely have none, and `null` is the
   * honest value for them — an empty-object default would claim a pleading that
   * was never drafted. The agents' `case_context()` keys its unchanged-output
   * path off exactly this being null.
   */
  brief: jsonb("brief").$type<CaseBriefDetail | null>(),
  source: text("source").notNull().default("library"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const insertCaseSchema = createInsertSchema(casesTable).omit({
  id: true,
  createdAt: true,
});
export type InsertCase = z.infer<typeof insertCaseSchema>;
export type Case = typeof casesTable.$inferSelect;
