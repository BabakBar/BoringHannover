import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { Resvg } from '@resvg/resvg-js';
import pngToIco from 'png-to-ico';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const projectRoot = path.resolve(__dirname, '..');
const publicDir = path.join(projectRoot, 'public');

const sources = [
  path.join(publicDir, 'favicon-h.svg'),
  path.join(publicDir, 'icon.svg')
];

async function readFirstExisting(filePaths) {
  for (const p of filePaths) {
    try {
      const data = await fs.readFile(p, 'utf8');
      return { path: p, data };
    } catch {
      // ignore
    }
  }
  throw new Error(
    `No SVG source found. Expected one of: ${filePaths.map((p) => path.relative(projectRoot, p)).join(', ')}`
  );
}

function renderPng(svg, size) {
  const resvg = new Resvg(svg, {
    fitTo: { mode: 'width', value: size }
  });
  const rendered = resvg.render();
  return Buffer.from(rendered.asPng());
}

async function writeFileIfChanged(outPath, buf) {
  try {
    const existing = await fs.readFile(outPath);
    if (existing.equals(buf)) return false;
  } catch {
    // no existing
  }
  await fs.writeFile(outPath, buf);
  return true;
}

async function main() {
  await fs.mkdir(publicDir, { recursive: true });

  const { path: srcPath, data: svg } = await readFirstExisting(sources);

  const outputs = [
    { file: 'favicon-32x32.png', size: 32 },
    { file: 'favicon-48x48.png', size: 48 },
    { file: 'apple-touch-icon.png', size: 180 },
    { file: 'android-chrome-192x192.png', size: 192 },
    { file: 'android-chrome-512x512.png', size: 512 }
  ];

  const rendered = new Map();

  for (const { file, size } of outputs) {
    const buf = renderPng(svg, size);
    rendered.set(size, buf);
    const outPath = path.join(publicDir, file);
    await writeFileIfChanged(outPath, buf);
  }

  // ICO: include multiple sizes for best compatibility.
  // Google can use /favicon.ico, and browsers will often look for it by default.
  const icoPngs = [16, 32, 48].map((s) => rendered.get(s) ?? renderPng(svg, s));
  const ico = await pngToIco(icoPngs);
  await writeFileIfChanged(path.join(publicDir, 'favicon.ico'), ico);

  // Helpful log (kept short, works in CI)
  console.log(
    `[icons] generated from ${path.relative(projectRoot, srcPath)} -> favicon.ico + PNGs (${outputs
      .map((o) => o.size)
      .join(', ')})`
  );
}

main().catch((err) => {
  console.error('[icons] generation failed:', err);
  process.exitCode = 1;
});
