// @ts-check
import { defineConfig } from 'astro/config';

// Defaults match GitHub Pages deployment at https://yash-814800.github.io/GH-Breakout
const site = process.env.SITE_URL || 'https://yash-814800.github.io';
const base = process.env.BASE_PATH || '/GH-Breakout';

export default defineConfig({
  site,
  base,
  output: 'static',
  vite: {
    worker: {
      format: 'es',
    },
    optimizeDeps: {
      exclude: ['@duckdb/duckdb-wasm'],
    },
  },
});
