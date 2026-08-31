/// <reference path="../.astro/types.d.ts" />

interface ImportMetaEnv {
  /** Hosted email provider form endpoint; when unset the signup form is hidden. */
  readonly PUBLIC_NEWSLETTER_FORM_ACTION?: string;
  /** Public Listmonk double-opt-in list UUID sent as form field `l`. */
  readonly PUBLIC_NEWSLETTER_LIST_UUID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
