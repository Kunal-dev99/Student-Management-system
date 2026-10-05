// Warm up the Next dev server: request every page once so it is compiled before anyone clicks.
//
// In dev mode Next builds a page the first time it is opened (0.2-0.9 s here) and doesn't prefetch
// links, so the first click on each page feels laggy and people click twice. start-frontend.bat
// runs this alongside `npm run dev`. Pages are found from src/app, so new ones are picked up;
// dynamic segments ([id]) get a placeholder, which still compiles the page's code.
//
//   node scripts/warmup.mjs [baseUrl]      (default http://localhost:3000)
import { readdirSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const base = (process.argv[2] || 'http://localhost:3000').replace(/\/$/, '')
const appDir = fileURLToPath(new URL('../src/app', import.meta.url))

function pages(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) out.push(...pages(full))
    else if (name === 'page.tsx' || name === 'page.ts' || name === 'page.jsx' || name === 'page.js') {
      const route = relative(appDir, dir).split(sep)
        .filter((seg) => seg && !(seg.startsWith('(') && seg.endsWith(')')))   // route groups
        .map((seg) => (seg.startsWith('[') ? 'warmup' : seg))                  // dynamic segments
        .join('/')
      out.push('/' + route)
    }
  }
  return out
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function waitForServer() {
  for (let i = 0; i < 180; i++) {          // up to 3 minutes for the dev server to come up
    try { await fetch(`${base}/login`); return true } catch { await sleep(1000) }
  }
  return false
}

const routes = [...new Set(pages(appDir))].sort()
if (!(await waitForServer())) {
  console.log('[warm-up] the frontend did not start; skipped')
  process.exit(0)
}
const started = Date.now()
let ok = 0
for (const route of routes) {             // one at a time: the dev compiler works page by page
  try {
    const res = await fetch(base + route, { redirect: 'manual' })
    if (res.status < 500) ok++
    await res.arrayBuffer()
  } catch { /* ignore: a page that fails to build shows its error when opened */ }
}
console.log(`[warm-up] ${ok}/${routes.length} pages compiled in ${Math.round((Date.now() - started) / 1000)} s - clicks are fast now`)
