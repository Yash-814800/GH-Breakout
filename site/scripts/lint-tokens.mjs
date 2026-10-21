// Fails when styling bypasses the design tokens (Phase 14 §10.2).
// Scans src/**/*.{astro,ts,css} except styles/tokens.css.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = new URL('../src/', import.meta.url).pathname;
const SKIP = new Set([join(ROOT, 'styles/tokens.css')]);
const PALETTE = 'gray|slate|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose';

const rules = [
  ['hex color', /(^|[^\w&/#-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b(?![-\w])/],
  ['rgb/hsl/oklch literal', /\b(?:rgba?|hsla?|oklch|oklab|hwb)\(\s*[\d.]/],
  ['Tailwind palette class', new RegExp(`\\b(?:text|bg|border|ring|fill|stroke|from|to|via|divide|outline|decoration|shadow)-(?:${PALETTE})-\\d{2,3}\\b`)],
  ['arbitrary pixel font size', /\btext-\[\d+(?:\.\d+)?px\]/],
  ['inline style without a custom property', /\bstyle=(?:"(?!\s*--)[^"{]|'(?!\s*--)[^'{])/],
];

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* walk(p);
    else if (/\.(astro|ts|css)$/.test(name) && !SKIP.has(p)) yield p;
  }
}

let problems = 0;
for (const file of walk(ROOT)) {
  readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
    // <meta name="theme-color"> cannot use CSS variables, so its two --bg values are literals (ADR-031).
    if (line.includes('name="theme-color"')) return;
    for (const [label, re] of rules) {
      if (re.test(line)) {
        problems++;
        console.error(`${relative(process.cwd(), file)}:${i + 1}: ${label}: ${line.trim().slice(0, 120)}`);
      }
    }
  });
}
if (problems) {
  console.error(`\nlint-tokens: ${problems} problem(s). Use the tokens in src/styles/tokens.css.`);
  process.exit(1);
}
console.log('lint-tokens: ok');
