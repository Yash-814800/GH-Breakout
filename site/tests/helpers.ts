import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import type { Page } from '@playwright/test';

// Fixture data by default; the daily deploy sets QA_DATA_DIR=public/data to check the real data before publishing.
const dataDir = join(process.cwd(), process.env.QA_DATA_DIR ?? 'test-data');
const board = JSON.parse(readFileSync(join(dataDir, 'leaderboard.json'), 'utf8')) as { repo_id: number }[];
const digestIndex = join(dataDir, 'digests/index.json');
const digests = existsSync(digestIndex) ? (JSON.parse(readFileSync(digestIndex, 'utf8')) as { week: string }[]) : [];
const detailIds = new Set(readdirSync(join(dataDir, 'repos')).map((f) => f.replace('.json', '')));

/** Every route that exists in the fixture build. Repo pages: the six edge-case repos plus one ordinary one. */
export const ROUTES: string[] = [
  '',
  ...board
    .slice(0, 7)
    .map((r) => String(r.repo_id))
    .filter((id) => detailIds.has(id))
    .map((id) => `repo/${id}/`),
  'track-record/',
  'backtest/',
  'explore/',
  'methodology/',
  'status/',
  'about/',
  'insights/',
  'digest/',
  'blog/',
  'blog/building-gh-breakout/',
  'blog/duckdb-vs-clickhouse/',
  ...digests.slice(0, 1).map((d) => `digest/${d.week}/`),
  '_styleguide/',
  '404.html',
];

export const PNG_1PX = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
);

/** Avatars come from avatars.githubusercontent.com; tests answer them locally so runs are offline-safe. */
export async function stubExternal(page: Page) {
  await page.route(/avatars\.githubusercontent\.com/, (r) => r.fulfill({ contentType: 'image/png', body: PNG_1PX }));
}

/** Waits until fonts and client-side rendering (charts, DuckDB lists) have settled. */
export async function settle(page: Page, route: string) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.evaluate(() => document.fonts.ready);
  if (route.startsWith('backtest')) {
    await page.waitForSelector('#list li, #fail:not([hidden])', { timeout: 60_000 }).catch(() => {});
  }
  if (route.startsWith('explore')) {
    await page.waitForFunction(() => !(document.getElementById('run') as HTMLButtonElement | null)?.disabled || !!document.querySelector('#error:not([hidden])'), null, { timeout: 60_000 }).catch(() => {});
  }
  if (/^(repo|track-record|status|insights)/.test(route) || route === '_styleguide/') {
    await page.waitForSelector('[data-chart] svg, figure svg, svg', { timeout: 10_000 }).catch(() => {});
  }
}
