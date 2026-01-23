import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

// https://astro.build/config
export default defineConfig({
  integrations: [tailwind()],
  // Used for canonical URLs + sitemap generation. Set in your deploy environment.
  // Examples:
  //   SITE=https://boringhannover.example
  //   PUBLIC_SITE_URL=https://boringhannover.example
  site: process.env.SITE || process.env.PUBLIC_SITE_URL || 'https://boringhannover.de',
  trailingSlash: 'always',
  output: 'static',
  build: {
    assets: 'assets'
  }
});
