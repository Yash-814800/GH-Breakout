// Copies docs/blog/img/* to public/blog/img/ so that posts can reference img/<file> (works on GitHub and on the site).
import { cpSync, existsSync, mkdirSync } from 'node:fs';
const src = new URL('../../docs/blog/img/', import.meta.url);
const dst = new URL('../public/blog/img/', import.meta.url);
if (existsSync(src)) {
  mkdirSync(dst, { recursive: true });
  cpSync(src, dst, { recursive: true });
}
