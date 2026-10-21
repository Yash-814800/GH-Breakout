import type { APIContext } from 'astro';
import { getFeedItems } from '../lib/data';
import { feedEntries, jsonFeed } from '../lib/feeds';
import { BRAND } from '../lib/site';
import { abs } from '../lib/url';

export function GET(context: APIContext) {
  const body = jsonFeed({
    title: `${BRAND}: new on the list`,
    description: 'Repos that enter the daily top of the breakout list for the first time in 30 days. Newest first.',
    homeUrl: abs('/', context.site),
    feedUrl: abs('/feed.json', context.site),
    entries: feedEntries(getFeedItems(), context.site),
  });
  return new Response(JSON.stringify(body, null, 2), { headers: { 'Content-Type': 'application/feed+json; charset=utf-8' } });
}
