/**
 * A cause list counts its matters in words. Digits are for citations,
 * paragraph numbers and marks — which is the distinction the apparatus
 * already makes everywhere else in the record, and the reason "3 matters"
 * looks wrong on a sheet that sets "¶03" and "s. 302" two lines below it.
 *
 * Past ten the word is longer than the number and stops helping, so the
 * numeral takes over.
 */
const COUNTS = [
  'No',
  'One',
  'Two',
  'Three',
  'Four',
  'Five',
  'Six',
  'Seven',
  'Eight',
  'Nine',
  'Ten',
];

export function counted(n: number): string {
  return n >= 0 && n <= 10 ? COUNTS[n] : String(n);
}

/** `counted`, lowercased for mid-sentence use. "No" stays capitalised nowhere. */
export function countedLower(n: number): string {
  return counted(n).toLowerCase();
}

/** Docket number as it is stamped on every sheet of the record. */
export function docket(id: number): string {
  return `AD-${id.toString().padStart(4, '0')}`;
}

/**
 * The five stages of the hearing, named as a Pakistani court names them.
 *
 * Shared because the appearances list was printing the raw enum with its
 * underscores swapped for spaces — "witness examination" beside the
 * courtroom's "Examination-in-Chief" for the same stage of the same session.
 */
const PHASE_LABELS: Record<string, string> = {
  opening: 'Opening submissions',
  witness_examination: 'Examination-in-chief',
  cross_examination: 'Cross-examination',
  // A writ is heard on the record: counsel answers the petition, then the
  // bench puts its own questions to counsel.
  submissions: 'Submissions in reply',
  bench_questions: 'Questions from the bench',
  closing: 'Closing arguments',
  verdict: 'Judgment',
};

export function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase] ?? phase.replace(/_/g, ' ');
}
