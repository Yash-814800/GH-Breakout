// Composes one image per theme from the screenshots of every route at 1280 and 375 px.
// Usage: node scripts/contact-sheet.mjs --dir ../reports/design/after
import sharp from 'sharp';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, x, i, all) => (x.startsWith('--') ? [...a, [x.slice(2), all[i + 1]]] : a), []));
const dir = args.dir ?? '../reports/design/after';
const files = readdirSync(dir).filter((f) => /\.(png|jpg)$/.test(f) && !f.startsWith('contact_sheet'));
const CELL = 190; // desktop thumbnail is 2 x CELL wide, the phone one 0.3 x
const HEIGHT = 330; // px height per thumbnail (top of the page)
const PER_ROW = 3;

for (const theme of ['light', 'dark']) {
  const rows = [];
  const routes = [...new Set(files.filter((f) => f.endsWith(`-${theme}.png`) || f.endsWith(`-${theme}.jpg`)).map((f) => f.replace(/-(\d+)-(light|dark)\.(png|jpg)$/, '')))].sort();
  for (const route of routes) {
    for (const w of [1280, 375]) {
      const f = files.find((x) => x.startsWith(`${route}-${w}-${theme}.`));
      if (!f) continue;
      const w2 = w === 1280 ? CELL * 2 : Math.round(CELL * 0.62);
      const img = await sharp(readFileSync(join(dir, f))).resize({ width: w2 }).extract({ left: 0, top: 0, width: w2, height: HEIGHT }).jpeg({ quality: 70 }).toBuffer().catch(async () =>
        sharp(readFileSync(join(dir, f))).resize({ width: w2, height: HEIGHT, fit: 'cover', position: 'top' }).jpeg({ quality: 70 }).toBuffer());
      rows.push({ route, w, img, w2 });
    }
  }
  // PER_ROW routes per row; each cell holds the desktop thumbnail next to the phone one
  const gap = 14;
  const cellW = CELL * 2 + Math.round(CELL * 0.62) + gap;
  const sheetW = PER_ROW * (cellW + gap) + gap;
  const composites = [];
  routes.forEach((route, i) => {
    const col = i % PER_ROW;
    const row = Math.floor(i / PER_ROW);
    let x = gap + col * (cellW + gap);
    const y = gap + row * (HEIGHT + gap);
    for (const r of rows.filter((q) => q.route === route)) {
      composites.push({ input: r.img, left: x, top: y });
      x += r.w2 + gap;
    }
  });
  const y = gap + Math.ceil(routes.length / PER_ROW) * (HEIGHT + gap);
  const bg = theme === 'light' ? { r: 235, g: 236, b: 240 } : { r: 12, g: 13, b: 16 };
  await sharp({ create: { width: sheetW, height: Math.max(y, 100), channels: 3, background: bg } }).composite(composites).jpeg({ quality: 72 }).toFile(join(dir, `contact_sheet_${theme}.jpg`));
  console.log('wrote', `contact_sheet_${theme}.jpg`, routes.length, 'routes');
}
