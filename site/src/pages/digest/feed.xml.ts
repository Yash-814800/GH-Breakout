import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { getDigests } from '../../lib/data';
import { digestEntries, rssCustomData } from '../../lib/feeds';
import { abs, url } from '../../lib/url';
import { BRAND } from '../../lib/site';

export function GET(context: APIContext) {
  const entries = digestEntries(getDigests(), context.site);
  return rss({
    title: `${BRAND}: weekly digest`,
    description: 'One issue a week: who joined the list, who moved most, and which past predictions hit or missed.',
    site: new URL(url('/'), context.site),
    trailingSlash: false,
    xmlns: { atom: 'http://www.w3.org/2005/Atom' },
    customData: `<language>en</language><atom:link href="${abs('/digest/feed.xml', context.site)}" rel="self" type="application/rss+xml" />`,
    items: entries.map((e) => ({
      title: e.title,
      pubDate: e.published,
      description: e.description,
      customData: rssCustomData(e),
    })),
  });
}
