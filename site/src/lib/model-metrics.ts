import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export interface Row {
  key: string;
  name: string;
  prAuc: number;
  prCi: [number, number];
  roc: number;
  p25: number | null;
  p25Ci: [number, number] | null;
}

const dir = resolve('../reports/metrics');
const read = (f: string) => (existsSync(`${dir}/${f}`) ? JSON.parse(readFileSync(`${dir}/${f}`, 'utf8')) : null);

/** Pooled cross-validation metrics of the champion and the baselines, from reports/metrics (written by the ML phases). */
export function modelRows(): Row[] | null {
  const cv = read('model_cv.json');
  const base = read('baseline.json');
  if (!cv?.main?.model || !base?.B1) return null;
  const names: Record<string, string> = {
    model: 'Champion (LightGBM)',
    B1: 'Baseline 1: stars in the last 7 days',
    B2: 'Baseline 2: stars in the last 14 days',
    B3: 'Baseline 3: star acceleration',
  };
  const rows: Row[] = [];
  for (const key of ['model', 'B1', 'B2', 'B3']) {
    const src = key === 'model' ? cv.main.model : (cv.main[key] ?? base[key]);
    if (!src?.pooled) continue;
    const p25 = (src.ci as { index: string; mean: number; ci_low: number; ci_high: number }[] | undefined)?.find((c) => c.index === 'precision@25');
    rows.push({
      key,
      name: names[key]!,
      prAuc: src.pooled.pr_auc,
      prCi: [src.pooled_pr_auc_ci.ci_low, src.pooled_pr_auc_ci.ci_high],
      roc: src.pooled.roc_auc,
      p25: p25 ? p25.mean : null,
      p25Ci: p25 ? [p25.ci_low, p25.ci_high] : null,
    });
  }
  return rows;
}
