#!/usr/bin/env node
/**
 * Build an installable bundle tarball without duplicating logic by hand.
 *
 * The package alone cannot reach the core: `npm pack dsh-plugin` would ship
 * `index.js` + `lib/` and nothing else, while the core lives at the repository
 * root. This script stages the package, copies the core files from the current
 * checkout into `vendor/core/`, then packs that staging directory. The vendor
 * copy is generated at pack time from HEAD — never edited by hand.
 *
 * Usage:
 *   node dsh-plugin/scripts/pack.mjs            # pack into <repo>/dist/
 *   node dsh-plugin/scripts/pack.mjs --keep     # keep the staging directory
 * Prints one JSON object: {tarball, staging, files, packSize}.
 */
import { execFileSync } from 'node:child_process'
import {
  cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync,
} from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PACKAGE_ROOT = path.resolve(HERE, '..')
const REPO_ROOT = path.resolve(PACKAGE_ROOT, '..')
const keep = process.argv.includes('--keep')
// Tests pack into their own directory: packing into dist/ and deleting the
// result left the release artifact missing after a test run.
const outIndex = process.argv.indexOf('--out')
const OUT_DIR = outIndex > -1 && process.argv[outIndex + 1]
  ? path.resolve(process.argv[outIndex + 1])
  : path.join(REPO_ROOT, 'dist')

const CORE_FILES = [
  ['scripts/build_flow.py', 'vendor/core/scripts/build_flow.py'],
  ['scripts/render_flow.py', 'vendor/core/scripts/render_flow.py'],
  ['assets/workflow_template.html', 'vendor/core/assets/workflow_template.html'],
  ['tools/pfe_cli.py', 'vendor/core/tools/pfe_cli.py'],
]

// The knowledge layer is a package, not a single file: copy it whole, minus
// bytecode caches, so the packed install can index/search without a checkout.
const CORE_PACKAGE = [['pfe', 'vendor/core/pfe']]

function fail(message) {
  console.log(`@@ERROR@@${message}`)
  process.exit(1)
}

for (const [source] of CORE_FILES) {
  if (!statSync(path.join(REPO_ROOT, source), { throwIfNoEntry: false })) {
    fail(`missing core file: ${source} (run from the repository checkout)`)
  }
}

const staging = mkdtempSync(path.join(os.tmpdir(), 'dsh-pfe-pack-'))
const staged = []
try {
  cpSync(path.join(PACKAGE_ROOT, 'index.js'), path.join(staging, 'index.js'))
  // The browser half of the bundle: the settings card registered into
  // plugins.bundle.config. Absent when a bundle ships host-only.
  const clientEntry = path.join(PACKAGE_ROOT, 'client.js')
  if (statSync(clientEntry, { throwIfNoEntry: false })) {
    cpSync(clientEntry, path.join(staging, 'client.js'))
  }
  cpSync(path.join(PACKAGE_ROOT, 'lib'), path.join(staging, 'lib'), { recursive: true })
  cpSync(path.join(PACKAGE_ROOT, 'cordis.patch.yml'), path.join(staging, 'cordis.patch.yml'))
  const readme = path.join(PACKAGE_ROOT, 'README.md')
  if (statSync(readme, { throwIfNoEntry: false })) cpSync(readme, path.join(staging, 'README.md'))

  for (const [source, target] of CORE_FILES) {
    const destination = path.join(staging, target)
    mkdirSync(path.dirname(destination), { recursive: true })
    cpSync(path.join(REPO_ROOT, source), destination)
    staged.push(target)
  }

  for (const [source, target] of CORE_PACKAGE) {
    const destination = path.join(staging, target)
    mkdirSync(path.dirname(destination), { recursive: true })
    cpSync(path.join(REPO_ROOT, source), destination, {
      recursive: true,
      filter: (item) => !item.includes('__pycache__') && !item.endsWith('.pyc'),
    })
    staged.push(target + '/')
  }

  // Keep the manifest honest about what the tarball contains, minus scripts
  // that only make sense inside the checkout.
  const manifest = JSON.parse(readFileSync(path.join(PACKAGE_ROOT, 'package.json'), 'utf8'))
  delete manifest.scripts
  writeFileSync(path.join(staging, 'package.json'),
    `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
  staged.push('package.json', 'index.js', 'lib/', 'cordis.patch.yml')
  if (statSync(clientEntry, { throwIfNoEntry: false })) staged.push('client.js')

  const outDir = OUT_DIR
  mkdirSync(outDir, { recursive: true })
  const output = execFileSync('npm', ['pack', '--json', '--pack-destination', outDir], {
    cwd: staging, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
  })
  const parsed = JSON.parse(output)
  const record = Array.isArray(parsed) ? parsed[0] : parsed
  const tarball = path.join(outDir, record.filename)
  console.log(JSON.stringify({
    tarball,
    staging: keep ? staging : null,
    files: record.entryCount ?? record.files?.length ?? null,
    packSize: record.size ?? statSync(tarball).size,
    staged,
  }))
} finally {
  if (!keep) rmSync(staging, { recursive: true, force: true })
}
