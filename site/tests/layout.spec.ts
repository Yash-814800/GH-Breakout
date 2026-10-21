import { expect, test } from '@playwright/test';
import { ROUTES, settle, stubExternal } from './helpers';

const WIDTHS = [360, 768, 1024, 1440];

for (const width of WIDTHS) {
  test.describe(`layout at ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });

    for (const route of ROUTES) {
      test(`/${route}`, async ({ page }) => {
        await stubExternal(page);
        await page.goto(route);
        await settle(page, route);

        // 1. no page-level horizontal scroll
        const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
        expect(sw, 'page is wider than the viewport').toBeLessThanOrEqual(iw);

        // 2. the web font is loaded
        expect(await page.evaluate(() => document.fonts.check('600 16px "Instrument Sans Variable"'))).toBe(true);

        // 3. exactly one h1 and no skipped heading levels
        const levels = await page.$$eval('h1,h2,h3,h4,h5,h6', (hs) => hs.filter((h) => (h as HTMLElement).offsetParent !== null || getComputedStyle(h).position === 'fixed').map((h) => Number(h.tagName[1])));
        expect(levels.filter((l) => l === 1), 'h1 count').toHaveLength(1);
        for (let i = 1; i < levels.length; i++) expect(levels[i]! - levels[i - 1]!, `heading jump in ${levels.join(',')}`).toBeLessThanOrEqual(1);

        // 4. no text overflow in key components (clamped text is allowed to overflow vertically)
        const overflow = await page.$$eval('[data-qa="repo-title"], [data-qa="pill"], .btn', (els) =>
          els
            .filter((e) => (e as HTMLElement).offsetParent !== null)
            .filter((e) => {
              const el = e as HTMLElement;
              const cs = getComputedStyle(el);
              if (cs.webkitLineClamp && cs.webkitLineClamp !== 'none') return false;
              return el.scrollWidth > el.clientWidth + 1 && cs.overflowX !== 'visible' ? true : el.scrollWidth > el.clientWidth + 1 && cs.whiteSpace === 'nowrap';
            })
            .map((e) => `${e.className}: ${(e.textContent ?? '').trim().slice(0, 40)}`),
        );
        expect(overflow, 'overflowing components').toEqual([]);

        // 5. no overlap inside a repo row: head, signal column and meta row must not intersect
        const overlaps = await page.$$eval('li.row', (rows) => {
          const out: string[] = [];
          const box = (el: Element | null) => {
            if (!el) return null;
            const r = (el as HTMLElement).getBoundingClientRect();
            return r.width === 0 || r.height === 0 ? null : r;
          };
          rows.forEach((row, i) => {
            if ((row as HTMLElement).hidden) return;
            const parts = ['.head', '.sig-cell', '.meta'].map((s) => [s, box(row.querySelector(s))] as const);
            for (let a = 0; a < parts.length; a++) {
              for (let b = a + 1; b < parts.length; b++) {
                const x = parts[a]![1];
                const y = parts[b]![1];
                if (x && y && x.left < y.right - 0.5 && y.left < x.right - 0.5 && x.top < y.bottom - 0.5 && y.top < x.bottom - 0.5) out.push(`row ${i}: ${parts[a]![0]} x ${parts[b]![0]}`);
              }
            }
          });
          return out;
        });
        expect(overlaps, 'overlapping row parts').toEqual([]);

        // 6. touch targets of at least 40 x 40 on phones
        if (width === 360) {
          const small = await page.$$eval('.btn, select, .seg-opt, input[type="date"], .check, .chip, .nav .brand', (els) =>
            els
              .filter((e) => (e as HTMLElement).offsetParent !== null && getComputedStyle(e).visibility !== 'hidden')
              .map((e) => ({ r: (e as HTMLElement).getBoundingClientRect(), n: `${e.tagName}.${(e as HTMLElement).className}`.slice(0, 50) }))
              .filter(({ r, n }) => r.height > 0 && (r.height < 39.5 || (r.width < 39.5 && !n.includes('chip'))) && true)
              .map(({ r, n }) => `${n} ${Math.round(r.width)}x${Math.round(r.height)}`),
          );
          expect(small, 'touch targets under 40px').toEqual([]);
        }
      });
    }
  });
}
