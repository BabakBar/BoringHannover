import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  // Canonical URLs + sitemap; set by the deploy environment.
  site: process.env.SITE || process.env.PUBLIC_SITE_URL,
  // Astro 7 changed the default to 'jsx', which strips the whitespace between
  // adjacent inline elements ("25 Aug" -> "25Aug"). This site renders scraped
  // German text where those spaces are meaningful, so keep HTML rules.
  compressHTML: true,
  vite: {
    define: {
      'import.meta.env.WEB_PROJECT_ROOT': JSON.stringify(fileURLToPath(new URL('.', import.meta.url))),
    },
    plugins: [tailwindcss()],
  },
  build: {
    assets: 'assets'
  }
});
