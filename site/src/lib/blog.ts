import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { Marked } from 'marked';
import { parse as parseYaml } from 'yaml';
import { url } from './url';

/** Posts live in docs/blog/*.md (readable on GitHub) and are rendered here; images are in docs/blog/img/. */
export const BLOG_DIR = resolve('../docs/blog');

export interface Post {
  slug: string;
  title: string;
  description: string;
  date: string;
  html: string;
  headings: { id: string; label: string }[];
}

export const slugify = (s: string) =>
  s
    .toLowerCase()
    .replace(/<[^>]+>/g, '')
    .replace(/&[a-z]+;/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');

/** Front matter (`---` block with title, date, description) and the Markdown body. */
export function splitFrontMatter(src: string): { meta: Record<string, unknown>; body: string } {
  const m = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(src);
  if (!m) return { meta: {}, body: src };
  return { meta: (parseYaml(m[1]!) as Record<string, unknown>) ?? {}, body: m[2]! };
}

export function renderMarkdown(md: string): { html: string; headings: Post['headings'] } {
  const headings: Post['headings'] = [];
  const marked = new Marked({ gfm: true });
  marked.use({
    renderer: {
      heading({ tokens, depth }) {
        const text = this.parser.parseInline(tokens);
        const id = slugify(text);
        if (depth === 2) headings.push({ id, label: text.replace(/<[^>]+>/g, '') });
        return `<h${depth} id="${id}">${text}</h${depth}>\n`;
      },
    },
  });
  let html = marked.parse(md, { async: false }) as string;
  // wide tables scroll inside the column instead of the page
  html = html
    .replace(/<table>/g, '<div class="table-wrap" tabindex="0" role="region" aria-label="Table"><table class="tbl">')
    .replace(/<\/table>/g, '</table></div>');
  // images are referenced as img/<file> in the Markdown file, so they also render on GitHub
  html = html.replace(/src="img\//g, `src="${url('/blog/img/')}`);
  // external links open in a new tab; internal ones keep the base path
  html = html.replace(/<a href="(https?:\/\/[^"]+)"/g, (_, h: string) =>
    h.startsWith('https://yash-814800.github.io/GH-Breakout/') ? `<a href="${h}"` : `<a href="${h}" target="_blank" rel="noopener"`,
  );
  return { html, headings };
}

export function getPosts(): Post[] {
  if (!existsSync(BLOG_DIR)) return [];
  return readdirSync(BLOG_DIR)
    .filter((f) => f.endsWith('.md'))
    .map((f) => {
      const { meta, body } = splitFrontMatter(readFileSync(join(BLOG_DIR, f), 'utf8'));
      const { html, headings } = renderMarkdown(body);
      return {
        slug: f.replace(/\.md$/, ''),
        title: String(meta.title ?? f),
        description: String(meta.description ?? ''),
        date: meta.date instanceof Date ? meta.date.toISOString().slice(0, 10) : String(meta.date ?? ''),
        html,
        headings,
      };
    })
    .sort((a, b) => b.date.localeCompare(a.date) || a.slug.localeCompare(b.slug));
}
