import { nameParts } from './data';
import { age, count, delta, isoWeekLabel, pct, sentence } from './format';
import type { DigestData, FeedItemData } from './types';
import { abs } from './url';

export interface FeedEntry {
  guid: string;
  title: string;
  link: string;
  published: Date;
  description: string;
  repoId?: number;
}

/** `owner/name — 34% breakout probability`; repos GitHub has no name for get a neutral label. */
export function feedTitle(i: Pick<FeedItemData, 'repo_name' | 'repo_id' | 'prob'>): string {
  const { hasName } = nameParts(i.repo_name, i.repo_id);
  return `${hasName ? i.repo_name : `Repo ${i.repo_id}`} — ${pct(i.prob)} breakout probability`;
}

/** Explanation sentence, then age, stars in the last 7 days, and the unusual-pattern note if any. */
export function feedDescription(i: FeedItemData): string {
  const parts: string[] = [];
  const why = sentence(i.explanation);
  if (why) parts.push(why);
  const facts: string[] = [];
  if (i.age_days != null) facts.push(age(i.age_days));
  if (i.stars_7d != null) facts.push(`${delta(i.stars_7d)} stars in the last 7 days`);
  else if (i.stars_total != null) facts.push(`${count(i.stars_total)} stars`);
  if (facts.length) parts.push(`${facts.join(', ')}.`);
  if (i.suspicion_note) parts.push(i.suspicion_note);
  return parts.join(' ') || `Entered the top of today's list at rank ${i.rank}.`;
}

export function feedEntries(items: FeedItemData[], site: URL | string | undefined): FeedEntry[] {
  return items.map((i) => ({
    guid: i.guid,
    title: feedTitle(i),
    link: abs(`/repo/${i.repo_id}/`, site),
    published: new Date(`${i.date}T00:00:00Z`),
    description: feedDescription(i),
    repoId: i.repo_id,
  }));
}

export function digestEntries(digests: DigestData[], site: URL | string | undefined): FeedEntry[] {
  return [...digests]
    .sort((a, b) => b.week.localeCompare(a.week))
    .map((d) => ({
      guid: `digest:${d.week}`,
      title: `Weekly digest, ${isoWeekLabel(d.start)}`,
      link: abs(`/digest/${d.week}/`, site),
      published: new Date(`${d.end}T00:00:00Z`),
      description: d.summary,
    }));
}

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** Item XML that @astrojs/rss cannot express: a stable non-URL GUID next to the link. */
export const rssCustomData = (e: FeedEntry) =>
  `<link>${esc(e.link)}</link><guid isPermaLink="false">${esc(e.guid)}</guid>`;

/** JSON Feed 1.1 document. */
export function jsonFeed(opts: {
  title: string;
  description: string;
  homeUrl: string;
  feedUrl: string;
  entries: FeedEntry[];
}) {
  return {
    version: 'https://jsonfeed.org/version/1.1',
    title: opts.title,
    description: opts.description,
    home_page_url: opts.homeUrl,
    feed_url: opts.feedUrl,
    language: 'en',
    items: opts.entries.map((e) => ({
      id: e.guid,
      url: e.link,
      title: e.title,
      content_text: e.description,
      date_published: e.published.toISOString(),
    })),
  };
}
