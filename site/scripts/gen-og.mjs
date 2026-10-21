// Open Graph images (1200 x 630): public/og/default.png and public/og/<repo_id>.png for every repo page.
// Unchanged images are skipped by hashing their inputs (cache in node_modules/.cache/og.json).
// Uses satori + resvg with the static Instrument Sans (.woff); satori cannot read woff2 or variable axes.
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, unlinkSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import satori from 'satori';
import { Resvg } from '@resvg/resvg-js';
import { BRAND, TAGLINE, light, markSvg } from './brand-lib.mjs';

const dataDir = resolve(process.env.DATA_DIR ?? 'public/data');
const outDir = new URL('../public/og/', import.meta.url).pathname;
const cachePath = new URL('../node_modules/.cache/og.json', import.meta.url).pathname;
mkdirSync(outDir, { recursive: true });
mkdirSync(join(cachePath, '..'), { recursive: true });
// Bump when the card layout changes so cached images are redrawn.
const TEMPLATE_VERSION = 5;
const cache = existsSync(cachePath) ? JSON.parse(readFileSync(cachePath, 'utf8')) : {};

const font = (w) => readFileSync(new URL(`../node_modules/@fontsource/instrument-sans/files/instrument-sans-latin-${w}-normal.woff`, import.meta.url));
const fonts = [
  { name: 'Instrument Sans', data: font(400), weight: 400, style: 'normal' },
  { name: 'Instrument Sans', data: font(600), weight: 600, style: 'normal' },
];
const markUri = `data:image/svg+xml;base64,${Buffer.from(markSvg(light, { size: 32 })).toString('base64')}`;

const h = (type, style, children) => ({ type, props: { style: { display: 'flex', ...style }, children } });
const text = (style, s) => h('div', style, s);
const brandRow = () =>
  h('div', { alignItems: 'center', gap: 14 }, [
    { type: 'img', props: { src: markUri, width: 40, height: 40 } },
    text({ fontSize: 28, fontWeight: 600, color: light.ink, letterSpacing: -0.3 }, BRAND),
  ]);

const fmtDate = (iso) => new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
const pct = (p) => (p < 0.01 ? '<1%' : p > 0.99 ? '>99%' : `${Math.round(p * 100)}%`);

function frame(children) {
  return h('div', { boxSizing: 'border-box', width: 1200, height: 630, background: light.bg, padding: 64, flexDirection: 'column', justifyContent: 'space-between', fontFamily: 'Instrument Sans' }, children);
}

function defaultCard() {
  return frame([
    brandRow(),
    h('div', { flexDirection: 'column', gap: 20 }, [
      text({ fontSize: 76, fontWeight: 600, color: light.ink, letterSpacing: -2, lineHeight: 1.05, maxWidth: 980 }, 'Repos likely to break out'),
      text({ fontSize: 30, color: light['ink-2'], maxWidth: 1060, lineHeight: 1.35 }, TAGLINE),
    ]),
    text({ fontSize: 22, color: light['ink-3'] }, ' '),
  ]);
}

function strip(values) {
  const max = Math.max(1, ...values);
  return h('div', { alignItems: 'flex-end', gap: 5, height: 120, width: 640 }, values.map((v, i) => ({
    type: 'div',
    props: { style: { display: 'flex', flex: 1, height: Math.max(2, Math.round((120 * v) / max)), background: i >= values.length - 7 ? light.accent : light['ink-3'], opacity: i >= values.length - 7 ? 1 : 0.35, borderRadius: 3 } },
  })));
}

function repoCard(r, prob, day, spark) {
  const full = r.repo_name.includes('/') && !r.repo_name.includes('=') ? r.repo_name : `Repo ${r.repo_id}`;
  const i = full.indexOf('/');
  const owner = i > 0 ? full.slice(0, i + 1) : '';
  const name = i > 0 ? full.slice(i + 1) : full;
  const size = full.length > 34 ? 46 : 60;
  return frame([
    brandRow(),
    h('div', { width: 1072, justifyContent: 'space-between', alignItems: 'flex-end' }, [
      h('div', { flexDirection: 'column', gap: 28, width: 690 }, [
        h('div', { flexWrap: 'wrap', fontSize: size, letterSpacing: -1.2, lineHeight: 1.1 }, [
          text({ color: light['ink-2'], fontWeight: 400 }, owner),
          text({ color: light.ink, fontWeight: 600 }, name),
        ]),
        spark.length ? strip(spark) : text({ height: 120 }, ' '),
      ]),
      h('div', { flexDirection: 'column', alignItems: 'flex-end', gap: 6, width: 360 }, [
        text({ fontSize: 140, fontWeight: 600, letterSpacing: -5, color: light.ink, lineHeight: 1 }, prob == null ? '' : pct(prob)),
        text({ fontSize: 26, color: light['ink-2'] }, 'breakout chance'),
      ]),
    ]),
    text({ fontSize: 24, color: light['ink-3'] }, fmtDate(day)),
  ]);
}

async function render(key, tree, inputs) {
  const hash = createHash('sha256').update(JSON.stringify([TEMPLATE_VERSION, inputs])).digest('hex');
  const file = join(outDir, `${key}.png`);
  if (cache[key] === hash && existsSync(file)) return false;
  const svg = await satori(tree, { width: 1200, height: 630, fonts });
  if (process.env.OG_DEBUG) writeFileSync(file.replace('.png', '.svg'), svg);
  writeFileSync(file, new Resvg(svg, { fitTo: { mode: 'width', value: 1200 } }).render().asPng());
  cache[key] = hash;
  return true;
}

let made = 0;
const wanted = new Set(['default']);
if (await render('default', defaultCard(), [BRAND, TAGLINE])) made++;

const read = (f) => JSON.parse(readFileSync(join(dataDir, f), 'utf8'));
const meta = read('meta.json');
const board = new Map(read('leaderboard.json').map((r) => [r.repo_id, r]));
const repoDir = join(dataDir, 'repos');
for (const f of existsSync(repoDir) ? readdirSync(repoDir).filter((x) => x.endsWith('.json')) : []) {
  const d = JSON.parse(readFileSync(join(repoDir, f), 'utf8'));
  wanted.add(String(d.repo_id));
  const row = board.get(d.repo_id);
  const preds = [...(d.prediction_history ?? [])].sort((a, b) => a.date.localeCompare(b.date));
  const prob = preds.at(-1)?.prob ?? row?.prob ?? null;
  const spark = row?.spark_stars_28d?.some((v) => v > 0) ? row.spark_stars_28d : (d.daily_stars ?? []).slice(-28).map((x) => x.stars);
  const spkNz = spark.some((v) => v > 0) ? spark : [];
  if (await render(String(d.repo_id), repoCard(d, prob, meta.data_through, spkNz), [d.repo_name, prob, meta.data_through, spkNz, BRAND])) made++;
}
// drop images of repos that no longer have a page
for (const f of readdirSync(outDir)) if (f.endsWith('.png') && !wanted.has(f.replace('.png', ''))) unlinkSync(join(outDir, f));
writeFileSync(cachePath, JSON.stringify(cache));
console.log(`og: ${made} image(s) written, ${Object.keys(cache).length} total in ${outDir}`);
