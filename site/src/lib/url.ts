/** URL helpers that always carry the GitHub Pages base path. */
const base = import.meta.env.BASE_URL.replace(/\/+$/, '');

export const url = (path = '/'): string => `${base}${path.startsWith('/') ? path : `/${path}`}`;
export const abs = (path: string, site: URL | string | undefined): string =>
  new URL(url(path), site ?? 'http://localhost').toString();
export const repoUrl = (id: number | string): string => url(`/repo/${id}/`);
export const dataUrl = (file: string): string => url(`/data/${file}`);

export const GITHUB_REPO = 'https://github.com/Yash-814800/GH-Breakout';
export const HF_EVENTS = 'https://huggingface.co/datasets/Yasshh814/gh-breakout-events';
export const HF_DERIVED = 'https://huggingface.co/datasets/Yasshh814/gh-breakout-derived';
export const HF_SNAPSHOTS = 'https://huggingface.co/datasets/Yasshh814/gh-breakout-snapshots';
export const HF_MODELS = 'https://huggingface.co/Yasshh814/gh-breakout-models';
