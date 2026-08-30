/// <reference path="../.astro/types.d.ts" />

interface ImportMetaEnv {
  /** Hosted email provider form endpoint; when unset the signup form is hidden. */
  readonly PUBLIC_NEWSLETTER_FORM_ACTION?: string;
  /** Optional provider list/tag identifier sent as a hidden form field. */
  readonly PUBLIC_NEWSLETTER_FORM_LIST_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
