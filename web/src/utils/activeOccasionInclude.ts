// Production nginx uses the same request-time cutoff as the detail route.
// Astro previews fall back to the build-time selection and ignore these comments.
export function activeOccasionStart(slug: string): string {
  return `<!--# if expr="$active_occasion_slugs = /:${slug}:/" -->`;
}

export const activeOccasionEnd = '<!--# endif -->';
