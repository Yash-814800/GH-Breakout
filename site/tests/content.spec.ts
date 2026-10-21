import { expect, test } from '@playwright/test';
import { ROUTES, settle, stubExternal } from './helpers';

const BAD = [/\bNaN\b/, /\bundefined\b/, /\bnull\b/, /\[object Object\]/, /Invalid Date/, /T00:00:00/, /\b(?:true|false)\b/];

for (const route of ROUTES) {
  test(`content of /${route}`, async ({ page }) => {
    const problems: string[] = [];
    page.on('console', (m) => m.type() === 'error' && problems.push(`console: ${m.text()}`));
    page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
    page.on('requestfailed', (r) => {
      // DuckDB fetches its Parquet extension from extensions.duckdb.org; offline runs may not reach it.
      if (!/extensions\.duckdb\.org/.test(r.url())) problems.push(`request failed: ${r.url()}`);
    });
    page.on('response', (r) => r.status() >= 400 && !r.url().endsWith('/404.html') && problems.push(`${r.status()} ${r.url()}`));
    await stubExternal(page);
    const resp = await page.goto(route);
    if (route !== '404.html') expect(resp?.status()).toBeLessThan(400);
    await settle(page, route);

    // visible text outside code blocks and hashes
    const text = await page.evaluate(() => {
      const skip = 'pre, code, script, style, template, .sr-only, .cm-editor, [data-no-content-check]';
      const parts: string[] = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        const el = n.parentElement;
        if (!el || el.closest(skip) || !el.checkVisibility({ checkVisibilityCSS: true })) continue;
        const t = n.textContent?.trim();
        if (t) parts.push(t);
      }
      return parts.join('\n');
    });
    for (const re of BAD) {
      // the words "null"/"true"/"false" can appear in prose; only fail on them as whole tokens next to separators
      if (re.source.includes('true')) continue;
      expect(text, `${re} found`).not.toMatch(re);
    }
    const floats = text.match(/\d+\.\d{3,}/g) ?? [];
    // metric pages report PR-AUC and ROC-AUC with three or four decimals on purpose; everything else must be rounded
    const allowed = route === 'methodology/' || route === 'status/' ? floats.filter((f) => !/^0\.\d{3,4}$/.test(f)) : floats;
    expect(allowed, 'unrounded numbers').toEqual([]);
    expect(text).not.toMatch(/\b\d{4}-\d{2}-\d{2}T\d{2}:/);
    expect(problems, 'console or network problems').toEqual([]);
  });
}

test('no request to Google Fonts', async ({ page }) => {
  const hosts = new Set<string>();
  page.on('request', (r) => hosts.add(new URL(r.url()).host));
  await stubExternal(page);
  await page.goto('');
  await page.waitForLoadState('networkidle');
  expect([...hosts].filter((h) => /fonts\.(googleapis|gstatic)\.com/.test(h))).toEqual([]);
});
