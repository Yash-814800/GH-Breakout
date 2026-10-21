// Full-page screenshots of every route at four widths in light and dark.
// Usage: node scripts/screenshot.mjs --out ../reports/design/before [--port 4321] [--routes /,/track-record/]
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdirSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const out = args.out ?? '../reports/design/after';
const port = Number(args.port ?? 4399);
const base = process.env.BASE_PATH ?? '/GH-Breakout';
const widths = (args.widths ?? '375,768,1280,1440').split(',').map(Number);
const themes = (args.themes ?? 'light,dark').split(',');

const repoDir = process.env.DATA_DIR ?? 'public/data/repos';
const firstRepo = readdirSync(repoDir).filter((f) => f.endsWith('.json')).sort()[0]?.replace('.json', '');
const routes = args.routes
  ? args.routes.split(',')
  : ['/', `/repo/${firstRepo}/`, '/track-record/', '/backtest/', '/explore/', '/methodology/', '/status/', '/about/', '/insights/'];

mkdirSync(out, { recursive: true });
const server = spawn('npx', ['astro', 'preview', '--port', String(port), '--host', '127.0.0.1'], { stdio: 'ignore' });
const origin = `http://127.0.0.1:${port}`;
for (let i = 0; i < 60; i++) {
  try { if ((await fetch(origin + base + '/')).ok) break; } catch {}
  await new Promise((r) => setTimeout(r, 500));
}

const browser = await chromium.launch();
try {
  for (const theme of themes) {
    for (const width of widths) {
      const ctx = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1, colorScheme: theme });
      for (const route of routes) {
        const page = await ctx.newPage();
        await page.route(/avatars\.githubusercontent\.com/, (r) => r.abort());
        await page.goto(origin + base + route, { waitUntil: 'networkidle' }).catch(() => {});
        await page.evaluate(() => document.fonts.ready);
        const slug = route === '/' ? 'home' : route.replace(/^\/|\/$/g, '').replace(/\//g, '_');
        const jpeg = args.format === 'jpeg';
        await page.screenshot({ path: join(out, `${slug}-${width}-${theme}.${jpeg ? 'jpg' : 'png'}`), fullPage: true, ...(jpeg ? { type: 'jpeg', quality: 80 } : {}) });
        await page.close();
      }
      await ctx.close();
    }
  }
} finally {
  await browser.close();
  server.kill();
}
console.log('done', out);
