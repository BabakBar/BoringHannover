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
