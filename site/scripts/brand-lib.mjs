// Shared helpers for brand assets and Open Graph images: tokens, config and the logomark geometry.
import { readFileSync } from 'node:fs';
import { parse } from 'yaml';

const css = readFileSync(new URL('../src/styles/tokens.css', import.meta.url), 'utf8');

/** Reads `--name: #hex` pairs from a block of tokens.css. `light` is the first :root block, `dark` the data-theme="dark" one. */
function block(re) {
  const m = css.match(re);
  if (!m) throw new Error('tokens.css block not found');
  return Object.fromEntries([...m[1].matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{3,8})\s*;/g)].map((x) => [x[1], x[2]]));
}
export const light = block(/^:root \{([\s\S]*?)^\}/m);
export const dark = block(/:root\[data-theme='dark'\] \{([\s\S]*?)^\}/m);

const cfg = parse(readFileSync(new URL('../../config/project.yaml', import.meta.url), 'utf8')).site ?? {};
export const BRAND = cfg.brand_name ?? 'Breakout Radar';
export const TAGLINE = cfg.tagline ?? 'GitHub repos likely to break out in the next 30 days. Updated daily.';

/** The logomark on a 24 x 24 grid: rounded square, three ascending bars (the last taller, like a momentum strip). */
export function markSvg(colors = light, { size = 24, bg = null } = {}) {
  const frame = bg ? `<rect width="24" height="24" fill="${bg}"/>` : '';
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24">${frame}<rect width="24" height="24" rx="6" fill="${colors.accent}"/><rect x="5" y="13" width="3.5" height="6" rx="1" fill="${colors['on-accent']}"/><rect x="10.25" y="10" width="3.5" height="9" rx="1" fill="${colors['on-accent']}"/><rect x="15.5" y="5" width="3.5" height="14" rx="1" fill="${colors['on-accent']}"/></svg>`;
}
