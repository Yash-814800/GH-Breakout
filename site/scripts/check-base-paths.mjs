import fs from 'node:fs';
import path from 'node:path';

const distDir = path.resolve(process.env.OUT_DIR || 'dist');
const base = (process.env.BASE_PATH || '/GH-Breakout').replace(/\/+$/, '');

if (!fs.existsSync(distDir)) {
  console.error(`Dist directory ${distDir} does not exist. Run build first.`);
  process.exit(1);
}

function findFiles(dir, ext) {
  let results = [];
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      results = results.concat(findFiles(fullPath, ext));
    } else if (file.endsWith(ext)) {
      results.push(fullPath);
    }
  }
  return results;
}

const htmlFiles = findFiles(distDir, '.html');
const cssFiles = findFiles(distDir, '.css');
let violations = 0;

// If base is empty or root '/', any href="/" is fine
if (base && base !== '') {
  for (const file of htmlFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    const relPath = path.relative(distDir, file);

    // Look for href="/... or src="/... not starting with base or //
    // Match href="/..." or src="/..."
    const regex = /(?:href|src)=["'](\/[^"']*)["']/g;
    let match;
    while ((match = regex.exec(content)) !== null) {
      const url = match[1];
      // Ignore protocol-relative URLs (//example.com)
      if (url.startsWith('//')) continue;
      // Check if starts with base
      if (!url.startsWith(base)) {
        console.error(`[Base Path Violation] In ${relPath}: found un-prefixed URL "${url}" (expected base "${base}")`);
        violations++;
      }
    }
  }
}

// Root-relative url(/...) in CSS would also miss the base path.
if (base) {
  for (const file of cssFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    for (const m of content.matchAll(/url\(\s*["']?(\/[^)"']*)["']?\s*\)/g)) {
      if (!m[1].startsWith('//') && !m[1].startsWith(base)) {
        console.error(`[Base Path Violation] In ${path.relative(distDir, file)}: url(${m[1]}) is not under "${base}"`);
        violations++;
      }
    }
  }
}

if (violations > 0) {
  console.error(`\n❌ Failed: Found ${violations} base-path violations.`);
  process.exit(1);
} else {
  console.log(`✓ Base path check passed: all internal links in ${htmlFiles.length} HTML and ${cssFiles.length} CSS files respect base "${base}".`);
}
