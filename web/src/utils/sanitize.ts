/**
 * URL sanitization utilities for the frontend.
 *
 * Provides defense-in-depth against XSS via malicious URLs that may
 * slip through backend validation. Blocks javascript:, data:, and
 * other dangerous URI schemes.
 */

/**
 * Sanitize a URL to prevent javascript: and data: injection attacks.
 *
 * This function validates that URLs use safe protocols (http/https only).
 * Any other protocol is rejected and replaced with '#'.
 *
 * @param url - The URL to sanitize (may be undefined)
 * @returns Safe URL string, or '#' if the URL is invalid/dangerous
 *
 * @example
 * sanitizeUrl('https://example.com/event')  // 'https://example.com/event'
 * sanitizeUrl('javascript:alert("xss")')    // '#'
 * sanitizeUrl('data:text/html,...')         // '#'
 * sanitizeUrl(undefined)                     // '#'
 */
export function sanitizeUrl(url?: string): string {
  // Handle null/undefined/empty
  if (!url) {
    return '#';
  }

  const trimmed = url.trim();
  if (trimmed.length === 0) {
    return '#';
  }

  // Normalize for case-insensitive protocol check
  const lower = trimmed.toLowerCase();

  // Block dangerous protocols (XSS vectors)
  const dangerousProtocols = [
    'javascript:',
    'data:',
    'vbscript:',
    'file:',
    'about:',
    'blob:',
  ];

  for (const proto of dangerousProtocols) {
    if (lower.startsWith(proto)) {
      return '#';
    }
  }

  // Only allow http and https
  if (!lower.startsWith('http://') && !lower.startsWith('https://')) {
    return '#';
  }

  return trimmed;
}
