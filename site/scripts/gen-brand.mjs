// Writes favicon.svg, favicon.ico, apple-touch-icon.png and site.webmanifest into public/ (committed; tiny).
import sharp from 'sharp';
import { writeFileSync } from 'node:fs';
import { BRAND, TAGLINE, dark, light, markSvg } from './brand-lib.mjs';

const pub = (f) => new URL(`../public/${f}`, import.meta.url);

// favicon.svg follows the system theme through an embedded media query.
const fav = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><style>.f{fill:${light.accent}}.b{fill:${light['on-accent']}}@media (prefers-color-scheme:dark){.f{fill:${dark.accent}}.b{fill:${dark['on-accent']}}}</style><rect class="f" width="24" height="24" rx="6"/><rect class="b" x="5" y="13" width="3.5" height="6" rx="1"/><rect class="b" x="10.25" y="10" width="3.5" height="9" rx="1"/><rect class="b" x="15.5" y="5" width="3.5" height="14" rx="1"/></svg>\n`;
writeFileSync(pub('favicon.svg'), fav);

// favicon.ico: one 32 x 32 PNG image inside an ICO container.
const png32 = await sharp(Buffer.from(markSvg(light, { size: 32 })), { density: 384 }).resize(32, 32).png().toBuffer();
const header = Buffer.alloc(22);
header.writeUInt16LE(0, 0); // reserved
header.writeUInt16LE(1, 2); // type: icon
header.writeUInt16LE(1, 4); // one image
header.writeUInt8(32, 6); // width
header.writeUInt8(32, 7); // height
header.writeUInt16LE(1, 10); // color planes
header.writeUInt16LE(32, 12); // bits per pixel
header.writeUInt32LE(png32.length, 14); // image size
header.writeUInt32LE(22, 18); // image offset
writeFileSync(pub('favicon.ico'), Buffer.concat([header, png32]));

// apple-touch-icon.png: the mark on the page background, 180 x 180 with padding (iOS rounds the corners itself).
const inner = await sharp(Buffer.from(markSvg(light, { size: 120 })), { density: 600 }).resize(120, 120).png().toBuffer();
await sharp({ create: { width: 180, height: 180, channels: 3, background: light.bg } }).composite([{ input: inner, left: 30, top: 30 }]).png().toFile(pub('apple-touch-icon.png').pathname);

writeFileSync(
  pub('site.webmanifest'),
  JSON.stringify(
    {
      name: BRAND,
      short_name: BRAND,
      description: TAGLINE,
      start_url: './',
      display: 'standalone',
      background_color: light.bg,
      theme_color: light.bg,
      icons: [
        { src: 'favicon.svg', sizes: 'any', type: 'image/svg+xml' },
        { src: 'apple-touch-icon.png', sizes: '180x180', type: 'image/png' },
      ],
    },
    null,
    2,
  ) + '\n',
);
console.log('brand assets written for', BRAND);
