// Offline verification bundle (used ONLY when `npm install` / `vite build` cannot run, e.g. no registry access).
// Bundles src/main.jsx with esbuild into <outdir>, copies index.html + public/, so the browser
// acceptance test can exercise the real app. This is NOT the production Vite build.
//   ESBUILD_PATH=/path/to/esbuild NODE_PATH=/path/to/node_modules node tests/build_preview.mjs /tmp/tw-preview
import fs from 'node:fs'; import path from 'node:path'; import { createRequire } from 'node:module'; import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.resolve(process.argv[2] || '/tmp/tw-preview');
const esbuild = require(process.env.ESBUILD_PATH || 'esbuild');
fs.rmSync(OUT, { recursive: true, force: true }); fs.mkdirSync(OUT, { recursive: true });
fs.cpSync(path.join(ROOT, 'public'), OUT, { recursive: true });
const nodePaths = (process.env.NODE_PATH || '').split(':').filter(Boolean);
await esbuild.build({
  entryPoints: [path.join(ROOT, 'src/main.jsx')], bundle: true, format: 'esm', outfile: path.join(OUT, 'assets/app.js'),
  loader: { '.js': 'jsx', '.jsx': 'jsx' }, jsx: 'automatic', nodePaths, logLevel: 'warning', minify: false,
  define: { 'import.meta.env': JSON.stringify({ BASE_URL: '/', VITE_GOOGLE_MAPS_API_KEY: process.env.VITE_GOOGLE_MAPS_API_KEY || '' }), 'process.env.NODE_ENV': '"production"' },
});
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')
  .replace('<script type="module" src="/src/main.jsx"></script>', '<link rel="stylesheet" href="/assets/app.css" /><script type="module" src="/assets/app.js"></script>');
fs.writeFileSync(path.join(OUT, 'index.html'), html);
console.log(`preview bundle written to ${OUT}`);
