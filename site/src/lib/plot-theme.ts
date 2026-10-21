import { count, shortDate } from './format';

/** Concrete colors resolved from the CSS tokens (SVG attributes cannot read var() reliably). */
export interface Tokens {
  bg: string;
  surface: string;
  raised: string;
  ink: string;
  ink2: string;
  ink3: string;
  line: string;
  lineStrong: string;
  accent: string;
  accentSoft: string;
  rise: string;
  caution: string;
  font: string;
}

const NAMES: Record<keyof Tokens, string> = {
  bg: '--bg',
  surface: '--surface',
  raised: '--raised',
  ink: '--ink',
  ink2: '--ink-2',
  ink3: '--ink-3',
  line: '--line',
  lineStrong: '--line-strong',
  accent: '--accent',
  accentSoft: '--accent-soft',
  rise: '--rise',
  caution: '--caution',
  font: '--font-ui',
};

export function resolveTokens(el: Element = document.documentElement): Tokens {
  const cs = getComputedStyle(el);
  return Object.fromEntries(
    (Object.keys(NAMES) as (keyof Tokens)[]).map((k) => [k, cs.getPropertyValue(NAMES[k]).trim()]),
  ) as Tokens;
}

export const HEIGHTS = { sparkline: 64, standard: 240, hero: 280 } as const;

/** Shared Plot options; the caller adds marks and scales. */
export function baseOptions(t: Tokens, width: number, height: number = HEIGHTS.standard) {
  return {
    width: Math.max(160, Math.floor(width)),
    height,
    marginLeft: 40,
    marginBottom: 28,
    marginTop: 8,
    marginRight: 8,
    style: {
      fontFamily: t.font,
      fontSize: '12px',
      color: t.ink3,
      background: 'transparent',
      overflow: 'visible',
    },
    x: { tickSize: 0, ticks: 5 },
    y: { grid: true, tickSize: 0, ticks: 4, tickFormat: (d: number) => count(d, { compact: true }) },
  };
}

export const dateTick = (d: Date | string) => shortDate(d);

/** Fires `fn(width)` when the element's width changes (debounced 100 ms) and on theme changes. */
export function observeWidth(el: HTMLElement, fn: (width: number) => void): void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let last = 0;
  const run = () => {
    const w = el.clientWidth;
    if (w > 0) {
      last = w;
      fn(w);
    }
  };
  new ResizeObserver(() => {
    if (Math.abs(el.clientWidth - last) < 1) return;
    clearTimeout(timer);
    timer = setTimeout(run, 100);
  }).observe(el);
  document.addEventListener('themechange', run);
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', run);
  run();
}
