/**
 * Every number, date and string shown on the site goes through this module.
 * Locale is fixed to en-US and all dates are UTC.
 */

export const DASH = '—';
const MINUS = '−';

type Num = number | null | undefined;
const bad = (n: Num): n is null | undefined => n == null || !Number.isFinite(n);

const intFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

/** Integer with thousands separators; `compact` gives 2.9k / 1.3M (no trailing .0). */
export function count(n: Num, opts: { compact?: boolean } = {}): string {
  if (bad(n)) return DASH;
  const v = Math.round(n);
  if (!opts.compact || Math.abs(v) < 1000) return intFmt.format(v);
  const sign = v < 0 ? MINUS : '';
  const a = Math.abs(v);
  const tenths = (x: number) => Math.round(x * 10) / 10;
  let k = tenths(a / 1000);
  if (k < 1000) return `${sign}${trim(k)}k`;
  const m = tenths(a / 1_000_000);
  return `${sign}${trim(m)}M`;
}
const trim = (x: number) => (Number.isInteger(x) ? String(x) : x.toFixed(1));

/** Signed integer with a true minus sign. */
export function delta(n: Num): string {
  if (bad(n)) return DASH;
  const v = Math.round(n);
  if (v === 0) return '0';
  return v > 0 ? `+${intFmt.format(v)}` : `${MINUS}${intFmt.format(-v)}`;
}

/** 0–1 share or probability as an integer percent. */
export function pct(p: Num, opts: { digits?: number } = {}): string {
  if (bad(p)) return DASH;
  if (opts.digits != null) return `${(p * 100).toFixed(opts.digits)}%`;
  if (p <= 0) return '0%';
  if (p < 0.01) return '<1%';
  if (p > 0.99) return '>99%';
  return `${Math.round(p * 100)}%`;
}

/** Plain-language odds, e.g. "About 1 in 3". */
export function odds(p: Num): string {
  if (bad(p) || p <= 0) return DASH;
  if (p >= 0.65) return 'Likely';
  if (p >= 0.5) return 'About even odds';
  const n = Math.round(1 / p);
  if (n > 1000) return 'Less than 1 in 1,000';
  return `About 1 in ${intFmt.format(n)}`;
}

type DateLike = string | number | Date | null | undefined;

/** Parses 'YYYY-MM-DD', ISO timestamps (naive ones are UTC) and Dates. */
export function toDate(d: DateLike): Date | null {
  if (d == null || d === '') return null;
  if (d instanceof Date) return Number.isNaN(d.getTime()) ? null : d;
  if (typeof d === 'number') return new Date(d);
  let s = d.trim();
  if (/^\d{4}-\d{2}-\d{2}T[\d:.]+$/.test(s)) s += 'Z';
  const out = new Date(s);
  return Number.isNaN(out.getTime()) ? null : out;
}

const utc = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', ...o });
const F_DATE = utc({ month: 'short', day: 'numeric', year: 'numeric' });
const F_SHORT = utc({ month: 'short', day: 'numeric' });
const F_TIME = utc({ hour: '2-digit', minute: '2-digit', hour12: false });

export function date(d: DateLike): string {
  const x = toDate(d);
  return x ? F_DATE.format(x) : DASH;
}

/** "Oct 21", plus the year when it differs from `refYear` (default: current year). */
export function shortDate(d: DateLike, refYear: number = new Date().getUTCFullYear()): string {
  const x = toDate(d);
  if (!x) return DASH;
  return x.getUTCFullYear() === refYear ? F_SHORT.format(x) : F_DATE.format(x);
}

/** "Aug 22 – Oct 21, 2026"; shared month/year parts are merged. */
export function dateRange(a: DateLike, b: DateLike): string {
  const x = toDate(a);
  const y = toDate(b);
  if (!x || !y) return DASH;
  const sameYear = x.getUTCFullYear() === y.getUTCFullYear();
  const sameMonth = sameYear && x.getUTCMonth() === y.getUTCMonth();
  if (sameMonth) return `${F_SHORT.format(x)}–${y.getUTCDate()}, ${y.getUTCFullYear()}`;
  if (sameYear) return `${F_SHORT.format(x)} – ${F_DATE.format(y)}`;
  return `${F_DATE.format(x)} – ${F_DATE.format(y)}`;
}

const REL = new Intl.RelativeTimeFormat('en-US', { numeric: 'auto' });
/** "3 hours ago", "yesterday". */
export function relTime(ts: DateLike, now: DateLike = new Date()): string {
  const t = toDate(ts);
  const n = toDate(now);
  if (!t || !n) return DASH;
  const sec = Math.round((t.getTime() - n.getTime()) / 1000);
  const abs = Math.abs(sec);
  if (abs < 60) return 'just now';
  if (abs < 3600) return REL.format(Math.round(sec / 60), 'minute');
  if (abs < 86400) return REL.format(Math.round(sec / 3600), 'hour');
  return REL.format(Math.round(sec / 86400), 'day');
}

export function utcTime(ts: DateLike): string {
  const x = toDate(ts);
  return x ? `${F_TIME.format(x)} UTC` : DASH;
}

/** Durations in hours. */
export function hours(h: Num): string {
  if (bad(h)) return DASH;
  if (h < 1) return 'under 1 h';
  if (h < 48) return `~${Math.round(h)} h`;
  return `~${Math.round(h / 24)} days`;
}

export function age(days: Num): string {
  if (bad(days)) return DASH;
  if (days < 1) return 'Created today';
  return `${intFmt.format(Math.round(days))} ${Math.round(days) === 1 ? 'day' : 'days'} old`;
}

/** "1 star", "2 stars". */
export function plural(n: Num, one: string, many: string = `${one}s`): string {
  if (bad(n)) return `${DASH} ${many}`;
  return `${intFmt.format(n)} ${n === 1 ? one : many}`;
}

export function repoName(full: string | null | undefined): { owner: string; name: string } {
  const s = (full ?? '').trim();
  const i = s.indexOf('/');
  if (i < 0) return { owner: '', name: s };
  return { owner: s.slice(0, i), name: s.slice(i + 1) };
}

const EMOJI_CODE = /:[a-z0-9_+-]{2,}:/gi;
/** Single-line plain text for descriptions; null when nothing is left. */
export function cleanText(s: string | null | undefined, max = 200): string | null {
  if (s == null) return null;
  let t = String(s)
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(EMOJI_CODE, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!t) return null;
  if (t.length > max) {
    const cut = t.slice(0, max);
    const sp = cut.lastIndexOf(' ');
    t = `${(sp > max * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s.,;:!?-]+$/, '')}…`;
  }
  return t;
}

/** Sentence with exactly one terminal period and no double spaces. */
export function sentence(s: string | null | undefined): string | null {
  const t = cleanText(s, 1000);
  if (!t) return null;
  return `${t.replace(/[.\s]+$/, '')}.`;
}

export function missing(): string {
  return DASH;
}

/** First 10 hex chars plus an ellipsis; the caller puts the full hash in a title and a copy button. */
export function hash(h: string | null | undefined): string {
  if (!h) return DASH;
  return h.length > 10 ? `${h.slice(0, 10)}…` : h;
}

/** ISO date (YYYY-MM-DD) of a date-like value, for keys and URLs. */
export function isoDay(d: DateLike): string | null {
  const x = toDate(d);
  return x ? x.toISOString().slice(0, 10) : null;
}

/** ISO week label "Week 42, 2026" for digest titles. */
export function isoWeekLabel(d: DateLike): string {
  const x = toDate(d);
  if (!x) return DASH;
  const t = new Date(Date.UTC(x.getUTCFullYear(), x.getUTCMonth(), x.getUTCDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const yearStart = Date.UTC(t.getUTCFullYear(), 0, 1);
  const week = Math.ceil(((t.getTime() - yearStart) / 86_400_000 + 1) / 7);
  return `Week ${week}, ${t.getUTCFullYear()}`;
}

/** Whole-percent axis tick: 1 becomes "100%" (pct() would say ">99%"). */
export function pctAxis(p: Num): string {
  return bad(p) ? DASH : `${Math.round(p * 100)}%`;
}
