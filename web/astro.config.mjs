import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  // Used for canonical URLs + sitemap generation. Set in your deploy environment.
  // Examples:
  //   SITE=https://boringhannover.example
  //   PUBLIC_SITE_URL=https://boringhannover.example
  site: process.env.SITE || process.env.PUBLIC_SITE_URL,
  output: 'static',
  // Astro 7 changed the default to 'jsx', which strips the whitespace between
  // adjacent inline elements ("25 Aug" -> "25Aug"). This site renders scraped
  // German text where those spaces are meaningful, so keep HTML rules.
  compressHTML: true,
  vite: {
    plugins: [tailwindcss()],
  },
  build: {
    assets: 'assets'
  }
});
