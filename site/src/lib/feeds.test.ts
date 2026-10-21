import { describe, expect, it } from 'vitest';
import { digestEntries, feedDescription, feedEntries, feedTitle, jsonFeed, rssCustomData } from './feeds';
import type { DigestData, FeedItemData } from './types';

const item = (o: Partial<FeedItemData> = {}): FeedItemData => ({
  guid: '42:2026-10-20',
  repo_id: 42,
  repo_name: 'acme/rocket',
  date: '2026-10-20',
  rank: 3,
  prob: 0.34,
  explanation: 'Flagged because 60 stars yesterday',
  age_days: 13,
  stars_7d: 182,
  stars_total: 192,
  suspicion_note: null,
  ...o,
});

describe('feeds', () => {
  it('titles follow "owner/name — 34% breakout probability"', () => {
    expect(feedTitle(item())).toBe('acme/rocket — 34% breakout probability');
    expect(feedTitle(item({ repo_name: 'repo_id=42' }))).toBe('Repo 42 — 34% breakout probability');
  });
  it('descriptions carry the explanation, age, stars and the suspicion note', () => {
    const d = feedDescription(item({ suspicion_note: 'Unusual star pattern: x.' }));
    expect(d).toBe('Flagged because 60 stars yesterday. 13 days old, +182 stars in the last 7 days. Unusual star pattern: x.');
    expect(feedDescription(item({ explanation: null, age_days: null, stars_7d: null, stars_total: null }))).toContain('rank 3');
  });
  it('entries link to the repo page and keep the stable guid', () => {
    const [e] = feedEntries([item()], 'https://example.org');
    expect(e!.link).toBe('https://example.org/repo/42/');
    expect(e!.guid).toBe('42:2026-10-20');
    expect(e!.published.toISOString()).toBe('2026-10-20T00:00:00.000Z');
  });
  it('escapes the custom XML', () => {
    const [e] = feedEntries([item({ guid: 'a&b:1' })], 'https://example.org');
    expect(rssCustomData(e!)).toContain('<guid isPermaLink="false">a&amp;b:1</guid>');
  });
  it('builds a JSON Feed 1.1 document', () => {
    const f = jsonFeed({ title: 't', description: 'd', homeUrl: 'h', feedUrl: 'f', entries: feedEntries([item()], 'https://example.org') });
    expect(f.version).toBe('https://jsonfeed.org/version/1.1');
    expect(f.items[0]).toMatchObject({ id: '42:2026-10-20', url: 'https://example.org/repo/42/', title: expect.any(String), content_text: expect.any(String) });
  });
  it('digest entries are newest first', () => {
    const d = (week: string, end: string) => ({ week, start: end, end, summary: week, new_on_board: [], movers: [], matured: [], notes: [] }) as DigestData;
    const e = digestEntries([d('2026-W41', '2026-10-11'), d('2026-W42', '2026-10-18')], 'https://example.org');
    expect(e.map((x) => x.guid)).toEqual(['digest:2026-W42', 'digest:2026-W41']);
  });
});

import { badgeMarkdown } from './badge';
describe('badge snippet', () => {
  it('encodes the endpoint url and links to the repo page', () => {
    const md = badgeMarkdown(42, 'https://example.org');
    expect(md).toBe(
      '[![breakout radar](https://img.shields.io/endpoint?url=https%3A%2F%2Fexample.org%2Fbadges%2F42.json)](https://example.org/repo/42/)',
    );
  });
});
