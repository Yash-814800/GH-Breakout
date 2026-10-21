import { abs } from './url';

/** The shields.io endpoint badge for a repo, as a Markdown snippet linking back to its page. */
export function badgeMarkdown(repoId: number, site: URL | string | undefined): string {
  const badgeJson = abs(`/badges/${repoId}.json`, site);
  const img = `https://img.shields.io/endpoint?url=${encodeURIComponent(badgeJson)}`;
  return `[![breakout radar](${img})](${abs(`/repo/${repoId}/`, site)})`;
}
