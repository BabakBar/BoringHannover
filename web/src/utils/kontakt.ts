/** Contact form: query prefill, validation and error copy. */

const KINDS = ['korrektur', 'vorschlag', 'kontakt'] as const;
export type Kind = (typeof KINDS)[number];
/** The fields a visitor types; anything else the endpoint reports has no place to show. */
export type FieldName = 'message' | 'email' | 'name';

export const CONTACT_EMAIL = 'kontakt@boringhannover.de';
export const ENDPOINT = '/_forms/submit';

// The Worker enforces the same limits; matching them here only saves a round trip.
export const LIMITS = { email: 254, message: 5000, name: 120, context: 500, page: 500 } as const;
const MIN_MESSAGE = 2;
const EMAIL = /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/;
const CONTROL = /[\u0000-\u001f\u007f]+/g;

export interface Prefill {
  kind: Kind;
  context: string;
  page: string;
}

/** Only a path on this site is accepted as the page a report refers to. */
function sitePath(value: string): string {
  return value.startsWith('/') && !value.startsWith('//') && !/[\u0000-\u001f\u007f]/.test(value) ? value : '';
}

export function prefillFromQuery(search: string): Prefill {
  const params = new URLSearchParams(search);
  const art = params.get('art');
  return {
    kind: KINDS.includes(art as Kind) ? (art as Kind) : 'kontakt',
    context: (params.get('bezug') ?? '').replace(CONTROL, ' ').trim().slice(0, LIMITS.context),
    page: sitePath((params.get('seite') ?? '').trim()).slice(0, LIMITS.page),
  };
}

/** Deep link used by the "Report a mistake" entry points. */
export function correctionHref(title: string, path: string): string {
  const params = new URLSearchParams({ art: 'korrektur', bezug: title, seite: path });
  return `/kontakt/?${params}`;
}

/** When the form cannot send, the e-mail fallback carries what was typed. */
export function fallbackMailto(message: string, context: string): string {
  const params = new URLSearchParams();
  if (context) params.set('subject', context);
  if (message.trim()) params.set('body', message.trim());
  // Mail clients read '+' literally; URLSearchParams writes spaces as '+'.
  const query = params.toString().replace(/\+/g, '%20');
  return `mailto:${CONTACT_EMAIL}${query ? `?${query}` : ''}`;
}

const LABEL: Record<FieldName, string> = { email: 'email address', message: 'message', name: 'name' };

function errorMessage(field: FieldName, error: string): string {
  switch (error) {
    case 'required':
      return `Please enter your ${LABEL[field]}.`;
    case 'too_long':
      return `Your ${LABEL[field]} is too long (max ${LIMITS[field]} characters).`;
    case 'too_short':
      return `Please write at least ${MIN_MESSAGE} characters.`;
    case 'invalid':
      return field === 'email'
        ? "That doesn't look like a valid email address, e.g. name@example.com."
        : `Your ${LABEL[field]} isn't valid.`;
    default:
      return `We couldn't check your ${LABEL[field]}.`;
  }
}

/** Server-reported field errors, limited to fields this form shows. */
export function mapFieldErrors(fields: Record<string, string> | undefined): Partial<Record<FieldName, string>> {
  const mapped: Partial<Record<FieldName, string>> = {};
  for (const [field, error] of Object.entries(fields ?? {})) {
    if (Object.hasOwn(LABEL, field)) mapped[field as FieldName] = errorMessage(field as FieldName, error);
  }
  return mapped;
}

/** Same rules as the Worker, so obvious mistakes never leave the browser. */
export function validateLocally(emailInput: string, messageInput: string, nameInput: string): Partial<Record<FieldName, string>> {
  const errors: Record<string, string> = {};
  const email = emailInput.trim();
  const message = messageInput.trim();
  if (!email) errors.email = 'required';
  else if (email.length > LIMITS.email) errors.email = 'too_long';
  else if (!EMAIL.test(email)) errors.email = 'invalid';
  if (!message) errors.message = 'required';
  else if (message.length < MIN_MESSAGE) errors.message = 'too_short';
  else if (message.length > LIMITS.message) errors.message = 'too_long';
  if (nameInput.trim().length > LIMITS.name) errors.name = 'too_long';
  return mapFieldErrors(errors);
}

export type Outcome =
  | { type: 'sent' }
  | { type: 'invalid'; fields: Partial<Record<FieldName, string>> }
  | { type: 'challenge' }
  | { type: 'unavailable' };

/** The endpoint's documented statuses; anything else is treated as unavailable. */
export function interpretResponse(status: number, body: { ok?: boolean; error?: string; fields?: Record<string, string> } | null): Outcome {
  if (status === 200 && body?.ok) return { type: 'sent' };
  if (status === 422 && body?.error === 'invalid') return { type: 'invalid', fields: mapFieldErrors(body.fields) };
  if (status === 403 && body?.error === 'challenge') return { type: 'challenge' };
  return { type: 'unavailable' };
}

/** The Umami payload carries the kind only, never anything the visitor typed. */
export function sentEvent(kind: Kind): { name: string; data: { kind: Kind } } {
  return { name: 'contact-sent', data: { kind } };
}
