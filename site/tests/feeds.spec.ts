import { expect, test } from '@playwright/test';

// Phase 12.1: the feeds are valid, carry the required fields and are advertised in every page head.

type Parsed = { channel: Record<string, string>; items: Record<string, string>[]; parseError: boolean };

async function parseRss(page: import('@playwright/test').Page, xml: string): Promise<Parsed> {
  return page.evaluate((text) => {
    const doc = new DOMParser().parseFromString(text, 'application/xml');
    const parseError = doc.querySelector('parsererror') !== null;
    const get = (el: Element, tag: string) => el.getElementsByTagName(tag)[0]?.textContent ?? '';
    const ch = doc.getElementsByTagName('channel')[0]!;
    return {
      parseError,
      channel: { title: get(ch, 'title'), link: get(ch, 'link'), description: get(ch, 'description'), root: doc.documentElement.tagName, version: doc.documentElement.getAttribute('version') ?? '' },
      items: [...doc.getElementsByTagName('item')].map((i) => ({
        title: get(i, 'title'),
        link: get(i, 'link'),
        guid: get(i, 'guid'),
        guidPermaLink: i.getElementsByTagName('guid')[0]?.getAttribute('isPermaLink') ?? '',
        pubDate: get(i, 'pubDate'),
        description: get(i, 'description'),
      })),
    };
  }, xml);
}

test('feed.xml is valid RSS 2.0 with the required fields', async ({ page, request }) => {
  await page.goto('about/');
  const res = await request.get('feed.xml');
  expect(res.ok()).toBe(true);
  const f = await parseRss(page, await res.text());
  expect(f.parseError).toBe(false);
  expect(f.channel).toMatchObject({ root: 'rss', version: '2.0' });
  expect(f.channel.title && f.channel.link && f.channel.description).toBeTruthy();
  expect(f.items.length).toBeGreaterThan(0);
  expect(f.items.length).toBeLessThanOrEqual(100);
  const guids = new Set<string>();
  for (const i of f.items) {
    expect(i.title, 'title shape').toMatch(/ — (<1%|>99%|\d+%) breakout probability$/);
    expect(i.link).toMatch(/\/GH-Breakout\/repo\/\d+\/$/);
    expect(i.guid).toMatch(/^\d+:\d{4}-\d{2}-\d{2}$/);
    expect(i.guidPermaLink).toBe('false');
    expect(Number.isNaN(Date.parse(i.pubDate))).toBe(false);
    expect(i.description.length).toBeGreaterThan(10);
    expect(guids.has(i.guid), `duplicate guid ${i.guid}`).toBe(false);
    guids.add(i.guid);
  }
  const dates = f.items.map((i) => Date.parse(i.pubDate));
  expect(dates, 'newest first').toEqual([...dates].sort((a, b) => b - a));
});

test('feed.json is valid JSON Feed 1.1', async ({ request }) => {
  const res = await request.get('feed.json');
  expect(res.ok()).toBe(true);
  const j = await res.json();
  expect(j.version).toBe('https://jsonfeed.org/version/1.1');
  expect(j.title).toBeTruthy();
  expect(j.items.length).toBeGreaterThan(0);
  for (const i of j.items) {
    expect(i.id).toMatch(/^\d+:\d{4}-\d{2}-\d{2}$/);
    expect(i.url).toMatch(/\/repo\/\d+\/$/);
    expect(i.content_text || i.content_html).toBeTruthy();
    expect(Number.isNaN(Date.parse(i.date_published))).toBe(false);
  }
});

test('digest feed lists the digests, newest first', async ({ page, request }) => {
  await page.goto('about/');
  const res = await request.get('digest/feed.xml');
  expect(res.ok()).toBe(true);
  const f = await parseRss(page, await res.text());
  expect(f.parseError).toBe(false);
  expect(f.items.length).toBeGreaterThan(0);
  for (const i of f.items) expect(i.link).toMatch(/\/digest\/\d{4}-W\d{2}\/$/);
  const weeks = f.items.map((i) => i.link);
  expect(weeks).toEqual([...weeks].sort().reverse());
});

test('every page advertises the feeds', async ({ page }) => {
  for (const path of ['', 'about/', 'digest/']) {
    await page.goto(path);
    const hrefs = await page.locator('link[rel="alternate"]').evaluateAll((els) => els.map((e) => e.getAttribute('href')));
    expect(hrefs.some((h) => h?.endsWith('/feed.xml') && !h.includes('digest'))).toBe(true);
    expect(hrefs.some((h) => h?.endsWith('/feed.json'))).toBe(true);
    expect(hrefs.some((h) => h?.endsWith('/digest/feed.xml'))).toBe(true);
  }
});

test('repo pages show a copyable badge snippet', async ({ page }) => {
  await page.goto('repo/1407951147/');
  const md = await page.locator('#badge-md').textContent();
  expect(md).toMatch(/^\[!\[breakout radar\]\(https:\/\/img\.shields\.io\/endpoint\?url=https%3A%2F%2F.+%2Fbadges%2F1407951147\.json\)\]\(https:\/\/.+\/repo\/1407951147\/\)$/);
  await expect(page.getByRole('button', { name: 'Copy badge Markdown' })).toBeVisible();
});
