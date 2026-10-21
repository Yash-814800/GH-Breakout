import colors from './languages.json';

const map = colors as Record<string, string>;

/** Linguist color for a language, or null (the dot then falls back to --ink-3). */
export function languageColor(name: string | null | undefined): string | null {
  return name ? (map[name] ?? null) : null;
}
