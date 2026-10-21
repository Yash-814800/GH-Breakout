import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test } from '@playwright/test';

// Every page file must render through a layout (so global.css is always loaded).
function* walk(dir: string): Generator<string> {
  for (const n of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, n.name);
    if (n.isDirectory()) yield* walk(p);
    else if (n.name.endsWith('.astro')) yield p;
  }
}
test('every page uses a layout', () => {
  const files = [...walk(join(process.cwd(), 'src/pages')), ...walk(join(process.cwd(), 'src/styleguide'))];
  expect(files.length).toBeGreaterThan(5);
  for (const f of files) expect(readFileSync(f, 'utf8'), f).toMatch(/layouts\/(Base|App|Longform)Layout\.astro/);
});

test('global.css is imported once, by the base layout', () => {
  const hits: string[] = [];
  const srcDir = join(process.cwd(), 'src');
  for (const f of walk(srcDir)) if (readFileSync(f, 'utf8').includes("styles/global.css")) hits.push(f.replace(process.cwd(), ''));
  expect(hits).toEqual(['/src/layouts/BaseLayout.astro']);
});
