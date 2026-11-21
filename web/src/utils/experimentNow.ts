// EXPERIMENT (occasions v2): the dev server honours ?now= so the no-JS HTML
// matches the browser's shifted clock. Production builds ignore it.
export function experimentNow(url: URL): Date {
  if (!import.meta.env.DEV) return new Date();
  const wanted = url.searchParams.get('now');
  const parsed = wanted ? new Date(wanted) : null;
  return parsed && !Number.isNaN(parsed.getTime()) ? parsed : new Date();
}
