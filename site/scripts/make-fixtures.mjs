// Patches site/test-data with the edge cases of Phase 14 §10.4 (idempotent).
// Usage: node scripts/make-fixtures.mjs
import { readFileSync, writeFileSync } from 'node:fs';

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
