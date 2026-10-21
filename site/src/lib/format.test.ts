import { describe, expect, it } from 'vitest';
import * as f from './format';

describe('count', () => {
  it('formats integers and compact values', () => {
    expect(f.count(186)).toBe('186');
    expect(f.count(2912)).toBe('2,912');
    expect(f.count(2912, { compact: true })).toBe('2.9k');
    expect(f.count(1_250_000, { compact: true })).toBe('1.3M');
    expect(f.count(999, { compact: true })).toBe('999');
    expect(f.count(1000, { compact: true })).toBe('1k');
    expect(f.count(999_999, { compact: true })).toBe('1M');
    expect(f.count(0)).toBe('0');
  });
  it('never prints NaN/null', () => {
    expect(f.count(null)).toBe('—');
    expect(f.count(undefined)).toBe('—');
    expect(f.count(Number.NaN)).toBe('—');
  });
});

describe('delta', () => {
  it('uses a true minus sign', () => {
    expect(f.delta(412)).toBe('+412');
    expect(f.delta(-3)).toBe('−3');
    expect(f.delta(0)).toBe('0');
    expect(f.delta(12345)).toBe('+12,345');
  });
});

describe('pct and odds', () => {
  it('rounds probabilities', () => {
    expect(f.pct(0.3418)).toBe('34%');
    expect(f.pct(0.004)).toBe('<1%');
    expect(f.pct(0.996)).toBe('>99%');
    expect(f.pct(0.0051, { digits: 2 })).toBe('0.51%');
    expect(f.pct(0)).toBe('0%');
  });
  it('describes odds', () => {
    expect(f.odds(0.34)).toBe('About 1 in 3');
    expect(f.odds(0.07)).toBe('About 1 in 14');
    expect(f.odds(0.51)).toBe('About even odds');
    expect(f.odds(0.97)).toBe('Likely');
    expect(f.odds(0.0004)).toBe('Less than 1 in 1,000');
    expect(f.odds(0.004)).toBe('About 1 in 250');
  });
});

describe('dates', () => {
  it('formats UTC dates', () => {
    expect(f.date('2026-10-21')).toBe('Oct 21, 2026');
    expect(f.date('2018-02-05T00:00:00')).toBe('Feb 5, 2018');
    expect(f.date('2026-10-21T23:59:59Z')).toBe('Oct 21, 2026');
    expect(f.date('nope')).toBe('—');
    expect(f.date(null)).toBe('—');
  });
  it('short dates add the year when it differs', () => {
    expect(f.shortDate('2026-10-21', 2026)).toBe('Oct 21');
    expect(f.shortDate('2025-12-30', 2026)).toBe('Dec 30, 2025');
  });
  it('merges ranges', () => {
    expect(f.dateRange('2026-08-22', '2026-10-21')).toBe('Aug 22 – Oct 21, 2026');
    expect(f.dateRange('2026-10-01', '2026-10-21')).toBe('Oct 1–21, 2026');
    expect(f.dateRange('2025-12-30', '2026-01-05')).toBe('Dec 30, 2025 – Jan 5, 2026');
  });
  it('relative and clock times', () => {
    const now = '2026-10-21T06:00:00Z';
    expect(f.relTime('2026-10-21T03:00:00Z', now)).toBe('3 hours ago');
    expect(f.relTime('2026-10-20T05:00:00Z', now)).toBe('yesterday');
    expect(f.relTime('2026-10-21T05:59:40Z', now)).toBe('just now');
    expect(f.utcTime('2026-10-21T03:42:10Z')).toBe('03:42 UTC');
  });
  it('week labels', () => {
    expect(f.isoWeekLabel('2026-10-15')).toBe('Week 42, 2026');
  });
});

describe('durations, ages, plurals', () => {
  it('hours', () => {
    expect(f.hours(0.4)).toBe('under 1 h');
    expect(f.hours(3.2)).toBe('~3 h');
    expect(f.hours(70)).toBe('~3 days');
  });
  it('age', () => {
    expect(f.age(0)).toBe('Created today');
    expect(f.age(1)).toBe('1 day old');
    expect(f.age(23)).toBe('23 days old');
  });
  it('plural', () => {
    expect(f.plural(1, 'star')).toBe('1 star');
    expect(f.plural(2, 'star')).toBe('2 stars');
    expect(f.plural(1250, 'repo')).toBe('1,250 repos');
    expect(f.plural(2, 'story', 'stories')).toBe('2 stories');
  });
});

describe('text', () => {
  it('repoName splits owner and name', () => {
    expect(f.repoName('a/b')).toEqual({ owner: 'a', name: 'b' });
    expect(f.repoName('a/b/c')).toEqual({ owner: 'a', name: 'b/c' });
    expect(f.repoName(null)).toEqual({ owner: '', name: '' });
  });
  it('cleanText strips shortcodes, links and whitespace', () => {
    expect(f.cleanText('  A :sparkles: tool\n\nfor [docs](https://x.y)  ')).toBe('A tool for docs');
    expect(f.cleanText('   ')).toBeNull();
    expect(f.cleanText(null)).toBeNull();
  });
  it('cleanText cuts at a word boundary', () => {
    const out = f.cleanText('word '.repeat(100), 50)!;
    expect(out.endsWith('…')).toBe(true);
    expect(out.length).toBeLessThanOrEqual(51);
    expect(out).not.toMatch(/wor…$/);
  });
  it('keeps CJK and emoji intact', () => {
    expect(f.cleanText('让你的agent一键连接 🚀')).toBe('让你的agent一键连接 🚀');
  });
  it('sentence has exactly one period', () => {
    expect(f.sentence('Flagged because x..  ')).toBe('Flagged because x.');
    expect(f.sentence('Hello   world')).toBe('Hello world.');
  });
  it('hash and missing', () => {
    expect(f.hash('28c2c179dd6afa14d37a6e7d5594af0491958bd1e789820e147966ecdf0f5c3c')).toBe('28c2c179dd…');
    expect(f.missing()).toBe('—');
  });
});
