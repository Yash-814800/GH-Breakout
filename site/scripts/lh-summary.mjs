// Prints the median Lighthouse scores per URL and form factor from .lighthouseci/ (written by `lhci autorun`).
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const median = (a) => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)];
const files = [];
for (const dir of ['.lighthouseci', '.lighthouseci/desktop', '.lighthouseci/mobile']) {
  if (!existsSync(dir)) continue;
  for (const f of readdirSync(dir)) if (/(^lhr-.*|\.report)\.json$/.test(f)) files.push(join(dir, f));
}
const groups = {};
for (const f of files) {
  const r = JSON.parse(readFileSync(f, 'utf8'));
  const key = `${r.configSettings.formFactor}|${r.finalUrl}`;
  (groups[key] ??= new Map()).set(r.fetchTime, r);
}
for (const [key, runs] of Object.entries(groups).sort()) {
  const [form, url] = key.split('|');
  const list = [...runs.values()];
  const c = (k) => Math.round(median(list.map((r) => r.categories[k].score * 100)));
  const a = (k) => median(list.map((r) => r.audits[k].numericValue));
  console.log(`${form.padEnd(8)} ${url.replace(/^https?:\/\/[^/]+/, '').padEnd(32)} perf ${c('performance')}  a11y ${c('accessibility')}  best-practices ${c('best-practices')}  seo ${c('seo')}  CLS ${a('cumulative-layout-shift').toFixed(3)}  LCP ${(a('largest-contentful-paint') / 1000).toFixed(2)}s  (${list.length} runs)`);
}
