import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const css = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8');
const grab = (re: RegExp) => Object.fromEntries([...css.match(re)![1]!.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((m) => [m[1]!, m[2]!]));
const light = grab(/^:root \{([\s\S]*?)^\}/m);
const dark = grab(/:root\[data-theme='dark'\] \{([\s\S]*?)^\}/m);

const lum = (hex: string) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0]! + 0.7152 * c[1]! + 0.0722 * c[2]!;
};
const ratio = (a: string, b: string) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);

// minimum ratios from the table in the phase file (rounded down slightly for float noise)
const SPEC: [string, string, number, number][] = [
  ['ink', 'bg', 17.6, 15.9],
  ['ink-2', 'bg', 6.8, 8.3],
  ['ink-3', 'bg', 4.9, 6.0],
  ['accent', 'bg', 6.5, 7.2],
  ['on-accent', 'accent', 6.5, 7.2],
  ['rise', 'bg', 5.7, 8.5],
  ['caution', 'bg', 5.5, 8.8],
];

describe('design tokens', () => {
  it('define every color in both themes', () => {
    for (const k of Object.keys(light).filter((k) => !['paper', 'paper-ink'].includes(k))) {
      expect(dark[k], `--${k} missing in dark`).toBeDefined();
    }
  });
  it.each(SPEC)('%s on %s keeps the contrast of the spec', (fg, bg, lightMin, darkMin) => {
    expect(ratio(light[fg]!, light[bg]!)).toBeGreaterThanOrEqual(lightMin);
    expect(ratio(dark[fg]!, dark[bg]!)).toBeGreaterThanOrEqual(darkMin);
  });
  it('keeps --ink-2 on --accent-soft readable (ink-3 is not allowed there)', () => {
    expect(ratio(light['ink-2']!, light['accent-soft']!)).toBeGreaterThanOrEqual(4.5);
    expect(ratio(dark['ink-2']!, dark['accent-soft']!)).toBeGreaterThanOrEqual(4.5);
  });
  it('paper figures keep their caption readable', () => {
    expect(ratio(light['paper-ink']!, light.paper!)).toBeGreaterThanOrEqual(4.5);
  });
});
