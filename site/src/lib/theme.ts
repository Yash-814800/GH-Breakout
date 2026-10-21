/** Theme preference: 'system' (attribute unset), 'light' or 'dark'. Runs in the browser only. */
export type ThemePref = 'system' | 'light' | 'dark';
const ORDER: ThemePref[] = ['system', 'light', 'dark'];

export function getPref(): ThemePref {
  try {
    const v = localStorage.getItem('theme');
    return v === 'light' || v === 'dark' ? v : 'system';
  } catch {
    return 'system';
  }
}

export function applyPref(pref: ThemePref): void {
  const root = document.documentElement;
  if (pref === 'system') root.removeAttribute('data-theme');
  else root.dataset.theme = pref;
  try {
    if (pref === 'system') localStorage.removeItem('theme');
    else localStorage.setItem('theme', pref);
  } catch {
    /* storage blocked: the choice lasts for this page view only */
  }
  root.dataset.themePref = pref;
  document.dispatchEvent(new CustomEvent('themechange', { detail: { pref } }));
}

export const nextPref = (p: ThemePref): ThemePref => ORDER[(ORDER.indexOf(p) + 1) % ORDER.length]!;

/** Called by charts to know when to redraw (explicit toggle or OS change). */
export function onThemeChange(fn: () => void): void {
  document.addEventListener('themechange', fn);
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', fn);
}
