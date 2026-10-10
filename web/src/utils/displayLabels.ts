// Small reader-facing label helpers. Source data keeps its German values;
// these only change how a few opaque tokens read on the English site.

/** German listings use "24:00" for midnight at the end of the listed day. */
export function formatEventTime(time: string): string {
  return time === '24:00' ? 'midnight' : time;
}

/** "FSK12" -> "FSK 12+": keeps the German rating, makes the age limit obvious. */
export function formatFskRating(rating: string): string {
  const match = /^FSK\s*(\d{1,2})$/i.exec(rating.trim());
  return match ? `FSK ${match[1]}+` : rating;
}

export interface AdmissionLabel {
  english: string;
  /** Keep the source term beside the English, e.g. a token named at the gate. */
  keepOriginal: boolean;
}

// Reviewed hannover.de entry labels (#54). An unlisted label stays German as
// published; it is never guessed or machine-translated here.
const ADMISSION_LABELS: Array<
  [RegExp, (match: RegExpExecArray) => string, boolean]
> = [
  [/^Erwachsene$/i, () => 'Adults', false],
  [/^Kinder$/i, () => 'Children', false],
  [
    /^Kinder \(?bis (\d{1,2}) Jahren?\)?$/i,
    (match) => `Children up to age ${match[1]}`,
    false,
  ],
  // Tiergartenfest: children who hand in acorns and chestnuts for the animals
  // get a Baumscheibe (tree slice) that works as a free ticket.
  [
    /^Mit Baumscheibe \(für Eichel- und Kastaniensammler\*innen\)$/i,
    () => 'With a tree slice, for acorn and chestnut collectors',
    true,
  ],
];

/** English for a reviewed German entry label, or null to keep it as listed. */
export function explainAdmissionLabel(label: string): AdmissionLabel | null {
  const text = label.trim();
  for (const [pattern, english, keepOriginal] of ADMISSION_LABELS) {
    const match = pattern.exec(text);
    if (match) return { english: english(match), keepOriginal };
  }
  return null;
}
