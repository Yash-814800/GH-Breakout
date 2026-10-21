import { z } from 'zod';

/**
 * Zod mirrors of site/schemas/*.json. Objects are loose (unknown keys kept) so the exporter can grow
 * without breaking the build; only the fields the UI reads are typed.
 */
const num = z.number().nullish();
const str = z.string().nullish();

export const LeaderboardRow = z.looseObject({
  rank: z.number().int().min(1),
  repo_id: z.number().int(),
  repo_name: z.string(),
  html_url: z.string(),
  description: str,
  owner_id: z.number().int().nullish(),
  owner_type: z.enum(['User', 'Organization']).nullish(),
  language: str,
  age_days: num,
  stars_total_observed: num,
  stars_total_source: z.enum(['github_api', 'gh_archive']).nullish(),
  stars_7d: num,
  stars_gain_api: num,
  stars_gain_days: num,
  spark_stars_28d: z.array(z.number()),
  prob: z.number().min(0).max(1),
  explanation: str,
  first_flagged_date: str,
  days_on_board: z.number().int(),
  rank_change: z.enum(['new', 'up', 'down', 'same']),
  suspicion_score: num,
  suspicion_level: z.enum(['low', 'medium', 'high']).nullish(),
  suspicion_reasons: z.array(z.string()).nullish(),
  b1_rank: num,
});
export type LeaderboardRowRaw = z.infer<typeof LeaderboardRow>;
export const Leaderboard = z.array(LeaderboardRow);

export const Shap = z.looseObject({
  feature: z.string(),
  value: z.unknown().optional(),
  contribution: z.number(),
  sentence: str,
});

export const RepoDetail = z.looseObject({
  repo_id: z.number().int(),
  repo_name: z.string(),
  html_url: z.string(),
  description: str,
  metadata: z
    .looseObject({
      name_with_owner: str,
      primary_language: str,
      owner_type: str,
      owner_id: z.number().int().nullish(),
      owner_login: str,
      created_at: str,
      license_spdx: str,
      topics: z.array(z.string()).nullish(),
      homepage_url: str,
    })
    .default({}),
  daily_stars: z.array(z.object({ date: z.string(), stars: z.number() })),
  stars_total: num,
  stars_total_source: str,
  star_count_history: z.array(z.object({ date: z.string(), stars: z.number() })).nullish(),
  prediction_history: z.array(
    z.looseObject({ date: z.string(), rank: z.number(), prob: z.number(), b1_rank: num }),
  ),
  latest_shap: z.array(Shap),
  explanation: str,
  realized_outcome: z
    .looseObject({
      matured: z.boolean().nullish(),
      horizon_date: str,
      gain_30d: num,
      hit: z.boolean().nullish(),
      label: z.boolean().nullish(),
    })
    .nullish(),
  trending_appearances: z.array(z.looseObject({ date: z.string(), rank: z.number(), source: str })),
  hn_stories: z.array(
    z.looseObject({ title: z.string(), url: z.string(), hn_url: str, created_at: str, points: num, num_comments: num }),
  ),
  cohort_retention: z.unknown().optional(),
  similar_repos: z.unknown().optional(),
  suspicion_breakdown: z
    .looseObject({
      score: num,
      level: str,
      reasons: z.array(z.string()).nullish(),
      signals: z.record(z.string(), z.number()).nullish(),
      medians: z.record(z.string(), z.number()).nullish(),
    })
    .nullish(),
});
export type RepoDetailRaw = z.infer<typeof RepoDetail>;

const MaturedPick = z.looseObject({
  rank: z.number(),
  repo_id: z.number(),
  repo_name: z.string(),
  prob: z.number(),
  gain_30d: num,
  hit: z.boolean(),
  label: z.boolean().nullish(),
});
export const TrackRecord = z.looseObject({
  matured_snapshots: z.array(
    z.looseObject({
      snapshot_date: z.string(),
      top25: z.array(MaturedPick),
      precision_at_10: z.number(),
      precision_at_25: z.number(),
      precision_at_50: z.number(),
      b1_precision_at_25: num,
    }),
  ),
  summary: z.looseObject({
    n_live_days: z.number(),
    n_matured_days: z.number(),
    top25_hit_rate: z.number(),
    base_rate: z.number(),
    b1_hit_rate: z.number(),
    median_lead_time_days: num,
  }),
  calibration: z.array(
    z.object({ bin_start: z.number(), bin_end: z.number(), predicted_avg: z.number(), realized_avg: z.number(), count: z.number() }),
  ),
  ledger: z.looseObject({
    first_date: str,
    last_date: str,
    total_rows: z.number(),
    last_hash: z.string(),
    genesis_hash: str,
    verified: z.boolean(),
  }),
});
export type TrackRecordData = z.infer<typeof TrackRecord>;

export const Backtest = z.looseObject({
  historical_dates: z.array(z.string()),
  date_summaries: z.array(
    z.looseObject({
      snapshot_date: z.string(),
      n_candidates: z.number(),
      precision_at_10: z.number(),
      precision_at_25: z.number(),
      precision_at_50: z.number(),
    }),
  ),
  is_simulated_disclaimer: str,
});
export type BacktestData = z.infer<typeof Backtest>;

export const Status = z.looseObject({
  snapshot_date: z.string(),
  published_at: z.string(),
  n_leaderboard: z.number(),
  data_through_date: str,
  step_durations: z.record(z.string(), z.number()).nullish(),
  rows_ingested_last_14d: z.array(z.record(z.string(), z.unknown())),
  missing_hours: z.array(z.string()),
  dbt_summary: z.looseObject({ tests_passing: num, status: str }).nullish(),
  model: z
    .looseObject({ version: str, promoted_at: str, cv_pooled_pr_auc: num, holdout_pr_auc: num })
    .nullish(),
  drift: z.record(z.string(), z.unknown()).nullish(),
  heartbeat: z
    .looseObject({
      last_success_at: str,
      snapshot_date: str,
      model_version: str,
      n_candidates: num,
      runtime_seconds: num,
      status: str,
    })
    .nullish(),
});
export type StatusData = z.infer<typeof Status>;

export const Meta = z.looseObject({
  build_time: z.string(),
  model_version: z.string(),
  data_through: z.string(),
  counts: z.record(z.string(), z.number()),
});
export type MetaData = z.infer<typeof Meta>;

export const Insights = z.looseObject({
  title: z.string(),
  description: str,
  generated_at: str,
  stories: z.array(
    z.looseObject({
      id: z.string(),
      title: z.string(),
      summary: z.string(),
      chart_type: z.string(),
      chart_data: z.array(z.record(z.string(), z.unknown())),
      sql: z.string(),
    }),
  ),
});
export type InsightsData = z.infer<typeof Insights>;

/** Display model shared by RepoRow and the repo page, built in lib/data.ts. */
export interface Repo {
  rank: number;
  id: number;
  /** Full `owner/name` when known; null for repos GitHub has no name for. */
  fullName: string | null;
  owner: string;
  name: string;
  url: string | null;
  ownerId: number | null;
  ownerType: 'User' | 'Organization' | null;
  description: string | null;
  language: string | null;
  ageDays: number | null;
  starsTotal: number | null;
  starsSource: 'github_api' | 'gh_archive' | null;
  /** Stars gained over the last `gainDays` days (null when unknown). */
  weekGain: number | null;
  gainDays: number | null;
  spark: number[];
  prob: number;
  why: string | null;
  firstFlagged: string | null;
  daysOnBoard: number;
  rankChange: 'new' | 'up' | 'down' | 'same';
  suspicion: { level: 'low' | 'medium' | 'high'; score: number | null; reasons: string[]; flagged: boolean };
}

/** Phase 11 sections of a repo page. Parsed leniently: a section that fails to parse is omitted. */
export const CohortRetention = z.looseObject({
  cohorts: z.array(
    z.looseObject({
      cohort_week: z.string(),
      n_stargazers: z.number(),
      share_fork_30d: num,
      share_issue_30d: num,
      share_pull_request_30d: num,
      share_comment_30d: num,
      share_any_30d: num,
    }),
  ),
  summary: z.looseObject({ avg_interaction_rate: num, n_mature_cohorts: num }).nullish(),
  reference_comparison: str,
  reference_band: z.looseObject({ any_median: num, any_q1: num, any_q3: num }).nullish(),
});
export type CohortRetentionData = z.infer<typeof CohortRetention>;

export const SimilarRepos = z.array(
  z.looseObject({
    repo_id: z.number(),
    repo_name: z.string(),
    overlap: z.number(),
    cosine: z.number(),
    language: str,
    html_url: z.string(),
  }),
);

/**
 * Weekly digest (Phase 12). Provisional shape, chosen here so the layout exists before the data does:
 * `digests/index.json` is an array of DigestMeta, `digests/<week>.json` is a Digest.
 */
export const DigestMeta = z.looseObject({ week: z.string(), start: z.string(), end: z.string(), summary: z.string() });
const DigestRepo = z.looseObject({
  repo_id: z.number(),
  repo_name: z.string(),
  prob: z.number().nullish(),
  explanation: str,
  language: str,
  age_days: num,
  stars_total: num,
  owner_id: z.number().nullish(),
  owner_type: z.enum(['User', 'Organization']).nullish(),
  from_rank: num,
  to_rank: num,
  hit: z.boolean().nullish(),
  gain_30d: num,
  predicted_on: str,
});
export const Digest = DigestMeta.extend({
  new_on_board: z.array(DigestRepo),
  movers: z.array(DigestRepo),
  matured: z.array(DigestRepo),
  notes: z.array(z.string()),
});
export type DigestData = z.infer<typeof Digest>;
export type DigestRepoData = z.infer<typeof DigestRepo>;
