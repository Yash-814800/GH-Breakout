import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { z } from 'zod';
import { cleanText, repoName, sentence } from './format';
import {
  Backtest,
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

const GH_URL = /^https:\/\/github\.com\/[^/=]+\/[^/=]+$/;

/** Map one leaderboard row (or repo page) to the display model. */
export function toRepo(r: LeaderboardRowRaw): Repo {
  const hasName = r.repo_name.includes('/') && !r.repo_name.includes('=');
  const { owner, name } = hasName ? repoName(r.repo_name) : { owner: '', name: `Repo ${r.repo_id}` };
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
