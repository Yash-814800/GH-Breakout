// Patches site/test-data with the edge cases of Phase 14 §10.4 (idempotent).
// Usage: node scripts/make-fixtures.mjs
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';

const path = new URL('../test-data/leaderboard.json', import.meta.url);
const rows = JSON.parse(readFileSync(path, 'utf8'));
const zero = Array(28).fill(0);
const spike = zero.map((_, i) => (i === 24 ? 640 : i > 24 ? 12 : 0));
const steady = Array.from({ length: 28 }, (_, i) => 3 + Math.round(i * 1.6));
const ramp = Array.from({ length: 28 }, (_, i) => (i < 21 ? 2 + (i % 3) : 20 + (i - 21) * 25));

const edits = [
  {
    repo_name: 'some-org/an-extremely-long-repository-name-without-any-breaks-at-all',
    html_url: 'https://github.com/some-org/an-extremely-long-repository-name-without-any-breaks-at-all',
    owner_id: 9919, owner_type: 'Organization', prob: 0.34, stars_total_observed: 12345, stars_total_source: 'github_api',
    stars_gain_api: 412, stars_gain_days: 7, spark_stars_28d: ramp, rank_change: 'up', suspicion_score: 96.2,
    suspicion_level: 'medium', suspicion_reasons: ['Many recent stars came from accounts under 30 days old'],
    description: 'A repository whose name has no natural break points, used to check wrapping.', days_on_board: 4,
  },
  {
    repo_name: 'quiet-dev/no-description', html_url: 'https://github.com/quiet-dev/no-description', owner_id: null, owner_type: null,
    description: null, prob: 0.004, stars_total_observed: 0, stars_total_source: 'github_api', stars_gain_api: 0, stars_gain_days: 7,
    spark_stars_28d: zero, rank_change: 'same', days_on_board: 9, explanation: null,
  },
  {
    repo_name: 'wordy/four-hundred-characters', html_url: 'https://github.com/wordy/four-hundred-characters', owner_id: 1024, owner_type: 'User',
    description: 'This description is deliberately very long so that the two-line clamp has to cut it. '.repeat(5).trim(),
    prob: 0.07, stars_total_observed: 7, stars_total_source: 'github_api', stars_gain_api: 7, stars_gain_days: 7, spark_stars_28d: spike,
    rank_change: 'new', days_on_board: 1,
  },
  {
    repo_name: 'zhongwen/agent-tools', html_url: 'https://github.com/zhongwen/agent-tools', owner_id: 2048, owner_type: 'User',
    description: '让你的智能体一键连接数百个工具的开源框架，支持本地与云端部署，并提供完整的中文文档与示例。',
    prob: 0.51, stars_total_observed: 999, stars_total_source: 'github_api', stars_gain_api: 120, stars_gain_days: 7, spark_stars_28d: steady,
    rank_change: 'down', days_on_board: 3,
  },
  {
    repo_name: 'rtl-lab/arabic-notes', html_url: 'https://github.com/rtl-lab/arabic-notes', owner_id: 4096, owner_type: 'Organization',
    description: 'مكتبة مفتوحة المصدر لتحليل النصوص العربية ومعالجتها بسرعة وكفاءة عالية',
    prob: 0.97, stars_total_observed: 1000, stars_total_source: 'github_api', stars_gain_api: 300, stars_gain_days: 7, spark_stars_28d: steady,
    rank_change: 'up', days_on_board: 2,
  },
  {
    repo_name: 'emoji-fan/sparkly', html_url: 'https://github.com/emoji-fan/sparkly', owner_id: 8192, owner_type: 'User',
    description: ':sparkles: Sparkly CLI :rocket: with [docs](https://example.com/docs) and 🎉 emoji',
    prob: 0.12, stars_total_observed: 1250000, stars_total_source: 'github_api', stars_gain_api: 12300, stars_gain_days: 7, spark_stars_28d: ramp,
    rank_change: 'same', days_on_board: 12,
  },
];
edits.forEach((e, i) => Object.assign(rows[i], e));
// every other row gets an owner id (user/org alternating) so avatars have something to request
rows.forEach((r, i) => {
  if (i >= edits.length && r.owner_id == null) {
    r.owner_id = 100000 + i * 7919;
    r.owner_type = i % 4 === 0 ? 'Organization' : 'User';
  }
});
writeFileSync(path, JSON.stringify(rows, null, 2) + '\n');
console.log('patched', edits.length, 'edge rows of', rows.length);

// ---- repo detail pages: match the edge-case rows and give the first one every optional section ----
import { existsSync } from 'node:fs';
const detailPath = (id) => new URL(`../test-data/repos/${id}.json`, import.meta.url);
const day = (n) => new Date(Date.UTC(2026, 9, 20 - n)).toISOString().slice(0, 10);
edits.forEach((e, i) => {
  const id = rows[i].repo_id;
  if (!existsSync(detailPath(id))) return;
  const d = JSON.parse(readFileSync(detailPath(id), 'utf8'));
  d.repo_name = e.repo_name;
  d.html_url = e.html_url;
  d.description = e.description;
  d.metadata = { ...d.metadata, name_with_owner: e.repo_name, owner_id: e.owner_id, owner_type: e.owner_type };
  d.stars_total = e.stars_total_observed;
  d.stars_total_source = 'github_api';
  if (i === 0) {
    d.metadata = { ...d.metadata, primary_language: 'Python', created_at: '2026-10-07T09:12:00Z', license_spdx: 'MIT', topics: ['agents'] };
    d.daily_stars = ramp.map((v, k) => ({ date: day(27 - k), stars: v }));
    d.star_count_history = Array.from({ length: 6 }, (_, k) => ({ date: day(5 - k), stars: 9000 + k * 560 }));
    d.prediction_history = [
      { date: day(3), rank: 18, prob: 0.12, raw_score: 0.2, b1_rank: 40 },
      { date: day(2), rank: 9, prob: 0.2, raw_score: 0.3, b1_rank: 22 },
      { date: day(1), rank: 6, prob: 0.29, raw_score: 0.4, b1_rank: 12 },
      { date: day(0), rank: 4, prob: 0.34, raw_score: 0.5, b1_rank: 7 },
    ];
    d.latest_shap = [
      { feature: 'stars_3d', value: 182, contribution: 0.62, sentence: '182 stars in the last 3 days' },
      { feature: 'actor_days_14d', value: 0.72, contribution: 0.41, sentence: '72% of recent stars come from experienced accounts' },
      { feature: 'issue_response', value: 3, contribution: 0.2, sentence: 'Issues get a first response in about 3 hours' },
      { feature: 'age_days', value: 332, contribution: -0.12, sentence: 'The repo is 332 days old' },
      { feature: 'pushes_14d', value: 2, contribution: -0.34, sentence: 'Few recent pushes' },
    ];
    d.explanation = 'Flagged because 182 stars in the last 3 days and 72% of recent stars come from experienced accounts. Held back by: few recent pushes';
    d.hn_stories = [{ title: 'Show HN: Harness, a long-named repository for testing', url: 'https://example.com/a', hn_url: 'https://news.ycombinator.com/item?id=1', created_at: '2026-10-18T10:00:00Z', points: 412, num_comments: 120 }];
    d.trending_appearances = [{ date: day(2), rank: 7, source: 'hf_top_projects' }, { date: day(1), rank: 5, source: 'hf_top_projects' }];
    d.suspicion_breakdown = {
      score: 96.2, level: 'medium', reasons: ['38% of new stars are from accounts younger than 30 days'],
      signals: { s_new_accounts: 0.38, s_inactive: 0.31, s_bulk: 0.04, s_burst: 0.4, s_no_engagement: 0.7 },
      medians: { s_new_accounts: 0.15, s_inactive: 0.2, s_bulk: 0, s_burst: 0.35, s_no_engagement: 0.5 },
    };
    d.cohort_retention = {
      cohorts: [0, 1, 2, 3].map((k) => ({ cohort_week: day(35 + k * 7), n_stargazers: 120 - k * 20, share_fork_30d: 0.06 - k * 0.01, share_issue_30d: 0.03, share_pull_request_30d: 0.012, share_comment_30d: 0.08 - k * 0.02, share_any_30d: 0.11 })),
      summary: { avg_interaction_rate: 0.11, n_mature_cohorts: 4 },
      reference_comparison: '30-day interaction rate is 11.0% (within the historical breakout IQR of 3.0%–12.0%, median 5.0%).',
      reference_band: { any_median: 0.05, any_q1: 0.03, any_q3: 0.12 },
    };
    d.similar_repos = [
      { repo_id: 1, repo_name: 'langchain-ai/langgraph', overlap: 41, cosine: 0.21, language: 'Python', html_url: 'https://github.com/langchain-ai/langgraph' },
      { repo_id: 2, repo_name: 'crewAIInc/crewAI', overlap: 33, cosine: 0.17, language: 'Python', html_url: 'https://github.com/crewAIInc/crewAI' },
    ];
  }
  if (i === 2) {
    d.realized_outcome = { matured: true, horizon_date: day(-30), gain_30d: 2340, hit: true, label: true };
  }
  writeFileSync(detailPath(id), JSON.stringify(d, null, 2) + '\n');
});
console.log('patched detail pages');

// ---- track record: committed fixture has 3 matured days; `--track-days N --out FILE` writes another size ----
function trackRecord(nDays) {
  const base = JSON.parse(readFileSync(new URL('../test-data/track_record.json', import.meta.url), 'utf8'));
  const names = rows.slice(0, 25);
  const days = Array.from({ length: nDays }, (_, d) => {
    const iso = new Date(Date.UTC(2026, 8, 19) - (nDays - 1 - d) * 864e5).toISOString().slice(0, 10);
    const top25 = names.map((r, k) => {
      const hit = (k * 7 + d * 3) % 9 === 0;
      return { rank: k + 1, repo_id: r.repo_id, repo_name: r.repo_name, prob: r.prob, gain_30d: hit ? 400 + k * 20 : 12 + ((k * d) % 60), hit, label: hit };
    });
    const p25 = top25.filter((p) => p.hit).length / 25;
    return { snapshot_date: iso, top25, precision_at_10: p25, precision_at_25: p25, precision_at_50: p25, b1_precision_at_25: Math.max(0, p25 - 0.08) };
  });
  base.matured_snapshots = days;
  const hit = days.reduce((a, d) => a + d.precision_at_25, 0) / Math.max(1, days.length);
  base.summary = { ...base.summary, n_live_days: nDays + 30, n_matured_days: nDays, top25_hit_rate: Number(hit.toFixed(4)), headline: nDays ? `Since ${new Date(days[0].snapshot_date + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })}, ${Math.round(hit * 100)}% of our top-25 picks broke out within 30 days, against 0.5% for all candidates.` : base.summary.headline };
  base.calibration = base.calibration.map((c, i) => ({ ...c, predicted_avg: c.bin_start + 0.05, realized_avg: Math.max(0, c.bin_start + 0.05 - 0.02 * (i % 3)), count: nDays ? 20 + i * 15 : 0 }));
  return base;
}
const arg = (k) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : null; };
if (arg('--track-days')) {
  writeFileSync(arg('--out'), JSON.stringify(trackRecord(Number(arg('--track-days'))), null, 2) + '\n');
  console.log('wrote track record with', arg('--track-days'), 'days');
} else {
  writeFileSync(new URL('../test-data/track_record.json', import.meta.url), JSON.stringify(trackRecord(3), null, 2) + '\n');
  console.log('track record fixture: 3 matured days');
}

// ---- status: steps, drift and ingest rows so the page renders every section ----
{
  const p = new URL('../test-data/status.json', import.meta.url);
  const st = JSON.parse(readFileSync(p, 'utf8'));
  st.step_durations = { ingest: 61.2, 'build features': 84.5, score: 12.1, freeze: 3.4, 'export site data': 40.8, 'upload to hub': 22.7 };
  st.rows_ingested_last_14d = [
    { event_type: 'WatchEvent', latest_event: '2026-10-20T23:59:41Z', rows_24h: 8571, missing_hours: 0 },
    { event_type: 'PullRequestEvent', latest_event: '2026-10-20T23:59:58Z', rows_24h: 40445, missing_hours: 0 },
    { event_type: 'IssuesEvent', latest_event: '2026-10-20T23:59:12Z', rows_24h: 17140, missing_hours: 1 },
  ];
  st.model = { version: '20261019-b5ff585', promoted_at: '2026-10-19T18:00:00+00:00', cv_pooled_pr_auc: 0.108, holdout_pr_auc: 0.158 };
  st.drift = { as_of: '2026-10-20', high_drift_threshold: 0.25, psi_by_feature: { stars_3d: 0.04, actor_days_14d: 0.12, primary_language: 0.31, stars_7d: 0.08, sg_tm_max_14d: 0.02, age_days: 0.55 } };
  writeFileSync(p, JSON.stringify(st, null, 2) + '\n');
  console.log('status fixture patched');
}

// ---- digest fixture (Phase 12 data does not exist yet; this is the provisional shape) ----
{
  const dir = new URL('../test-data/digests/', import.meta.url);
  mkdirSync(dir, { recursive: true });
  const pick = (r, extra = {}) => ({ repo_id: r.repo_id, repo_name: r.repo_name, prob: r.prob, explanation: r.explanation, language: r.language, age_days: r.age_days, stars_total: r.stars_total_observed, owner_id: r.owner_id, owner_type: r.owner_type, ...extra });
  const issue = (week, start, end) => ({
    week, start, end,
    summary: 'Six repos joined the list, two climbed more than ten places, and 3 of last month\u2019s top 25 broke out.',
    new_on_board: rows.slice(0, 5).map((r) => pick(r)),
    movers: rows.slice(5, 8).map((r, i) => pick(r, { from_rank: 30 - i * 4, to_rank: 8 - i })),
    matured: rows.slice(8, 12).map((r, i) => pick(r, { hit: i % 3 === 0, gain_30d: i % 3 === 0 ? 640 : 40 + i * 9, predicted_on: '2026-09-14' })),
    notes: ['Model 20261019-b5ff585 stayed the champion.', 'One feature, primary language, showed a large drift (PSI 0.31).'],
  });
  const issues = [issue('2026-W42', '2026-10-12', '2026-10-18'), issue('2026-W41', '2026-10-05', '2026-10-11')];
  issues.forEach((d) => writeFileSync(new URL(`${d.week}.json`, dir), JSON.stringify(d, null, 2) + '\n'));
  writeFileSync(new URL('index.json', dir), JSON.stringify(issues.map(({ week, start, end, summary }) => ({ week, start, end, summary })), null, 2) + '\n');
  console.log('digest fixtures written');
}
