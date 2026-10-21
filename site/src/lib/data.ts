import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { z } from 'zod';
import { cleanText, repoName, sentence } from './format';
import {
  Backtest,
  Digest,
  DigestMeta,
  FeedItem,
  Insights,
  Leaderboard,
  Meta,
  RepoDetail,
  Status,
  TrackRecord,
  type LeaderboardRowRaw,
  type Repo,
} from './types';

/** Build-time data directory: real data in public/data, fixtures in test-data (set DATA_DIR). */
export const DATA_DIR = resolve(process.env.DATA_DIR ?? 'public/data');

function load<T extends z.ZodType>(file: string, schema: T): z.infer<T> {
  const path = join(DATA_DIR, file);
  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(path, 'utf8'));
  } catch (e) {
    throw new Error(`Site data: cannot read ${path}: ${(e as Error).message}`);
  }
  const res = schema.safeParse(raw);
  if (!res.success) {
    const issues = res.error.issues
      .slice(0, 5)
      .map((i) => `  ${file}: ${i.path.join('.') || '(root)'}: ${i.message}`)
      .join('\n');
    throw new Error(`Site data: ${file} does not match the schema:\n${issues}`);
  }
  return res.data;
}

function loadOptional<T extends z.ZodType>(file: string, schema: T): z.infer<T> | null {
  return existsSync(join(DATA_DIR, file)) ? load(file, schema) : null;
}

/** Splits `owner/name`; repos GitHub has no name for (stored as `repo_id=123`) get a neutral label. */
export function nameParts(fullName: string, id: number) {
  const hasName = fullName.includes('/') && !fullName.includes('=');
  const { owner, name } = hasName ? repoName(fullName) : { owner: '', name: `Repo ${id}` };
  return { hasName, owner, name };
}

const GH_URL = /^https:\/\/github\.com\/[^/=]+\/[^/=]+$/;

/** Map one leaderboard row (or repo page) to the display model. */
export function toRepo(r: LeaderboardRowRaw): Repo {
  const { hasName, owner, name } = nameParts(r.repo_name, r.repo_id);
  return {
    rank: r.rank,
    id: r.repo_id,
    fullName: hasName ? r.repo_name : null,
    owner,
    name,
    url: hasName && GH_URL.test(r.html_url) ? r.html_url : hasName ? `https://github.com/${r.repo_name}` : null,
    ownerId: r.owner_id ?? null,
    ownerType: r.owner_type ?? null,
    description: cleanText(r.description, 300),
    language: r.language && r.language !== 'Unknown' ? r.language : null,
    ageDays: r.age_days ?? null,
    starsTotal: r.stars_total_observed ?? null,
    starsSource: r.stars_total_source ?? null,
    // GH Archive counts understate real growth since 2025-05 (ADR-029): trust the API gain first.
    weekGain: r.stars_gain_api ?? (r.stars_total_source === 'gh_archive' ? (r.stars_7d ?? null) : null),
    gainDays: r.stars_gain_api != null ? (r.stars_gain_days ?? null) : null,
    spark: r.spark_stars_28d,
    prob: r.prob,
    why: sentence(r.explanation),
    firstFlagged: r.first_flagged_date ?? null,
    daysOnBoard: r.days_on_board,
    rankChange: r.rank_change,
    suspicion: {
      level: r.suspicion_level ?? 'low',
      score: r.suspicion_score ?? null,
      reasons: r.suspicion_reasons ?? [],
      flagged: r.suspicion_score != null && r.suspicion_score >= 90,
    },
  };
}

export const getMeta = () => load('meta.json', Meta);
export const getStatus = () => load('status.json', Status);
export const getTrackRecord = () => load('track_record.json', TrackRecord);
export const getBacktest = () => load('backtest.json', Backtest);
export const getInsights = () => loadOptional('insights.json', Insights);
export const getLeaderboard = (): Repo[] => load('leaderboard.json', Leaderboard).map(toRepo);

export function getRepoDetails() {
  const dir = join(DATA_DIR, 'repos');
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .sort()
    .map((f) => load(`repos/${f}`, RepoDetail));
}

/** Stale when the last successful run is more than 30 hours before `now`. */
export function isStale(lastSuccess: string | null | undefined, now: Date, limitHours = 30): boolean {
  if (!lastSuccess) return true;
  const t = new Date(lastSuccess).getTime();
  return Number.isNaN(t) || (now.getTime() - t) / 3.6e6 > limitHours;
}

/** Gain in API star counts between the oldest history entry within `window` days of `end` and `end`. */
export function apiGain(
  history: { date: string; stars: number }[] | null | undefined,
  end: string,
  window = 7,
): { gain: number; days: number } | null {
  if (!history || history.length < 2) return null;
  const sorted = [...history].sort((a, b) => a.date.localeCompare(b.date));
  const last = sorted.at(-1)!;
  const endMs = new Date(`${end}T00:00:00Z`).getTime();
  const first = sorted.find((h) => (endMs - new Date(`${h.date}T00:00:00Z`).getTime()) / 864e5 <= window);
  if (!first || first.date === last.date) return null;
  const days = Math.round((new Date(`${last.date}T00:00:00Z`).getTime() - new Date(`${first.date}T00:00:00Z`).getTime()) / 864e5);
  return { gain: Math.max(0, last.stars - first.stars), days };
}

export const getDigestIndex = () => (loadOptional('digests/index.json', z.array(DigestMeta)) ?? []).sort((a, b) => b.week.localeCompare(a.week));
export function getDigests() {
  return getDigestIndex().map((m) => load(`digests/${m.week}.json`, Digest));
}

export const getFeedItems = () => loadOptional('feed_items.json', z.array(FeedItem)) ?? [];
