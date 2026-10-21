// Writes src/lib/languages.json ({ "Python": "<color>" }) from the linguist-languages package.
// Language colors are data (GitHub's own), not UI tokens, so they live outside tokens.css.
import * as ns from 'linguist-languages';
const languages = ns.default ?? ns;
import { writeFileSync } from 'node:fs';

const out = Object.fromEntries(
  Object.entries(languages)
    .filter(([, v]) => v.color)
    .map(([k, v]) => [k, v.color])
    .sort(([a], [b]) => a.localeCompare(b)),
);
writeFileSync(new URL('../src/lib/languages.json', import.meta.url), JSON.stringify(out) + '\n');
console.log('languages:', Object.keys(out).length);
