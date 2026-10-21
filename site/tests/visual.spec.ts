import { expect, test } from '@playwright/test';
import { ROUTES, settle, stubExternal } from './helpers';

const repo = ROUTES.find((r) => r.startsWith('repo/'))!;
const PAGES: [string, string][] = [
  ['home', ''],
  ['repo', repo],
  ['track-record', 'track-record/'],
  ['styleguide', '_styleguide/'],
];

for (const scheme of ['light', 'dark'] as const) {
  for (const width of [375, 1280]) {
    test.describe(`visual ${scheme} ${width}`, () => {
      test.use({ colorScheme: scheme, viewport: { width, height: 900 }, deviceScaleFactor: 1 });
      for (const [name, route] of PAGES) {
        test(name, async ({ page }) => {
          // fixed clock so "Updated 20 hours ago" and relative text never change
          await page.clock.install({ time: new Date('2026-10-21T08:00:00Z') });
          await stubExternal(page);
          await page.goto(route);
          await settle(page, route);
          await page.clock.resume();
          await expect(page).toHaveScreenshot(`${name}-${width}-${scheme}.png`, { fullPage: false });
        });
      }
    });
  }
}
