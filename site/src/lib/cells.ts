import { count, date } from './format';

/** Formats one query-result value for display: no raw floats, ISO strings or nulls. */
export function formatCell(v: unknown, kind: 'time' | 'other' = 'other'): { text: string; numeric: boolean } {
  if (v === null || v === undefined) return { text: '—', numeric: false };
  if (typeof v === 'bigint') return { text: count(Number(v)), numeric: true };
  if (typeof v === 'number') {
    if (kind === 'time') return { text: date(new Date(v)), numeric: false };
    if (Number.isInteger(v)) return { text: count(v), numeric: true };
    return { text: v.toLocaleString('en-US', { maximumFractionDigits: 3 }), numeric: true };
  }
  if (v instanceof Date) return { text: date(v), numeric: false };
  if (typeof v === 'boolean') return { text: v ? 'Yes' : 'No', numeric: false };
  return { text: String(v), numeric: false };
}
