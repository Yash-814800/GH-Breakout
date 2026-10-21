import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { getFeedItems } from '../lib/data';
import { feedEntries, rssCustomData } from '../lib/feeds';
import { abs, url } from '../lib/url';
import { BRAND } from '../lib/site';

export function GET(context: APIContext) {
  const entries = feedEntries(getFeedItems(), context.site);
  return rss({
    title: `${BRAND}: new on the list`,
    description: 'Repos that enter the daily top of the breakout list for the first time in 30 days. Newest first.',
    site: new URL(url('/'), context.site),
    trailingSlash: false,
    xmlns: { atom: 'http://www.w3.org/2005/Atom' },
    customData: `<language>en</language><atom:link href="${abs('/feed.xml', context.site)}" rel="self" type="application/rss+xml" />`,
    items: entries.map((e) => ({
      title: e.title,
      pubDate: e.published,
      description: e.description,
      customData: rssCustomData(e),
    })),
  });
}
