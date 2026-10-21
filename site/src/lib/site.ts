import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';

interface SiteCfg {
  brand_name?: string;
  tagline?: string;
}
let cfg: SiteCfg = {};
try {
  cfg = (parse(readFileSync(resolve('../config/project.yaml'), 'utf8')) as { site?: SiteCfg }).site ?? {};
} catch {
  /* running outside the repo: fall back to the defaults below */
}

export const BRAND = cfg.brand_name ?? 'Breakout Radar';
export const TAGLINE = cfg.tagline ?? 'GitHub repos likely to break out in the next 30 days. Updated daily.';

export const NAV = [
  { href: '/', label: 'Today' },
  { href: '/track-record/', label: 'Track record' },
  { href: '/backtest/', label: 'Backtest' },
  { href: '/explore/', label: 'Explore' },
  { href: '/insights/', label: 'Insights' },
  { href: '/methodology/', label: 'Methodology' },
] as const;

export const BREAKOUT_DEFINITION =
  'A breakout is a repo gaining stars faster than 99.5% of similar young repos over the next 30 days.';
