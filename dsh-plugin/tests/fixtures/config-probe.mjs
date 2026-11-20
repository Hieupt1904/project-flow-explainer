/**
 * Child-process probe for the native Config path.
 *
 * `loadSchemaModule()` anchors on `process.argv[1]` so it reaches the
 * installation's own schemastery. In a `node --test` worker that argv points at
 * the test runner, so the resolution has to be exercised in a fresh process
 * whose argv[1] is the dsh binary.
 *
 * Prints one JSON line: { anchorFound, config: 'native'|'fallback', hasObject, keys }
 */
import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PLUGIN = path.resolve(HERE, '../../index.js')

/**
 * Locate the installed dsh binary without hardcoding a workstation path.
 * Order: explicit env var, then whatever `which dsh` reports, then module
 * resolution. Returning undefined is a legitimate outcome (CI has no install)
 * and the test then asserts the fallback contract instead.
 */
function findInstallation() {
  const fromEnv = (process.env.DSH_INSTALL_BIN ?? '').trim()
  if (fromEnv !== '' && existsSync(fromEnv)) return fromEnv
  try {
    const which = spawnSync('which', ['dsh'], { encoding: 'utf8' })
    const binPath = (which.stdout ?? '').trim()
    if (binPath !== '') {
      // <prefix>/bin/dsh -> <prefix>/lib/node_modules/@deepseek-ai/dsh/lib/bin.js
      const prefix = path.dirname(path.dirname(binPath))
      const candidate = path.join(prefix, 'lib', 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js')
      if (existsSync(candidate)) return candidate
      // A plain symlink to bin.js is also usable as an argv anchor.
      if (existsSync(binPath)) return binPath
    }
  } catch {
    /* no shell, keep probing */
  }
  try {
    const resolved = import.meta.resolve('@deepseek-ai/dsh')
    if (resolved) return fileURLToPath(resolved)
  } catch {
    /* not resolvable */
  }
  return undefined
}

const bin = findInstallation()
if (bin === undefined) {
  console.log(JSON.stringify({ anchorFound: false, config: 'fallback', hasObject: false, keys: [] }))
  process.exit(0)
}

process.argv[1] = bin
const module = await import(pathToFileURL(PLUGIN).href)
const Config = module.Config
if (Config === undefined) {
  console.log(JSON.stringify({ anchorFound: true, config: 'fallback', hasObject: false, keys: [] }))
} else {
  // schemastery's toJSON is a ref table: { uid, refs: { "<uid>": {type, meta, inner} } }.
  // Field names are not in it, so report the volatile fields by description —
  // that is the thing settings.describe() needs in order to render a form.
  const json = typeof Config.toJSON === 'function' ? Config.toJSON() : {}
  const refs = json.refs ?? {}
  const descriptions = []
  for (const ref of Object.values(refs)) {
    const meta = ref?.meta ?? {}
    if (meta.volatile === true && typeof meta.description === 'string') {
      descriptions.push(Object.keys(meta).filter((k) => k === 'default').length + '|' + meta.description.split(' ')[0])
    }
  }
  console.log(JSON.stringify({
    anchorFound: true,
    config: 'native',
    hasObject: typeof Config === 'object' || typeof Config === 'function',
    volatileFields: descriptions.length,
    descriptions,
  }))
}
