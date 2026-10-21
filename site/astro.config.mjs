// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

// Defaults match GitHub Pages deployment at https://yash-814800.github.io/GH-Breakout
const site = process.env.SITE_URL || 'https://yash-814800.github.io';
const base = process.env.BASE_PATH || '/GH-Breakout';

export default defineConfig({
  site,
  base,
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap({ filter: (page) => !page.includes('/_styleguide/') })],
  vite: {
    plugins: [tailwindcss()],
    worker: {
      format: 'es',
    },
    optimizeDeps: {
      exclude: ['@duckdb/duckdb-wasm'],
    },
  },
});
