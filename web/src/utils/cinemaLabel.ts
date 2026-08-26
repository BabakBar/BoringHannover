const CINEMA_LABELS: Readonly<Record<string, string>> = {
  'Astor Grand Cinema': 'Astor',
  'Apollokino Hannover': 'Apollo',
};

export function getCinemaLabel(
  venue: string | null | undefined,
): string | null {
  if (!venue) return null;
  return CINEMA_LABELS[venue] ?? venue;
}
