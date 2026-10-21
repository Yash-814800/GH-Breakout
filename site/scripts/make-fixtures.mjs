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
