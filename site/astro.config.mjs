// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

// Defaults match GitHub Pages deployment at https://yash-814800.github.io/GH-Breakout
const site = process.env.SITE_URL || 'https://yash-814800.github.io';
const base = process.env.BASE_PATH || '/GH-Breakout';

// Astro skips files that start with an underscore, so the style guide is injected as a route.
const styleguide = {
  name: 'styleguide-route',
  hooks: {
    'astro:config:setup': ({ injectRoute }) => {
      injectRoute({ pattern: '/_styleguide', entrypoint: './src/styleguide/index.astro' });
    },
  },
};

export default defineConfig({
  site,
  base,
  output: 'static',
  outDir: process.env.OUT_DIR || 'dist',
  trailingSlash: 'always',
  integrations: [styleguide, sitemap({ filter: (page) => !page.includes('/_styleguide/') })],
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
