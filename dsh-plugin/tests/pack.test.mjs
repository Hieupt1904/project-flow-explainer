/**
 * Packaging test (TASK 3): the tarball must work without the repository
 * checkout. The test packs the bundle, extracts it into a temp dir that has no
 * core around it, imports the packed entry point and runs a real analysis.
 *
 * Run: node --test dsh-plugin/tests/pack.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import {
  cpSync, existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync,
} from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PACKAGE_ROOT = path.resolve(HERE, '..')
const REPO_ROOT = path.resolve(PACKAGE_ROOT, '..')
const FIXTURE = path.join(REPO_ROOT, 'tests', 'fixtures', 'shop-app')
const REQUEST = 'Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file'

function pack() {
  // Own output directory: a test must never delete the release artifact.
  const outDir = mkdtempSync(path.join(os.tmpdir(), 'pfe-pack-out-'))
  const output = execFileSync('node',
    [path.join(PACKAGE_ROOT, 'scripts', 'pack.mjs'), '--out', outDir], {
      cwd: PACKAGE_ROOT, encoding: 'utf8',
    })
  const line = output.trim().split('\n').filter((entry) => entry.startsWith('{')).pop()
  return JSON.parse(line)
}

function extract(tarball, target) {
  mkdirSync(target, { recursive: true })
  execFileSync('tar', ['-xzf', tarball, '-C', target, '--strip-components=1'], { stdio: 'ignore' })
}

function fixtureCopy(dir) {
  const repo = path.join(dir, 'shop-app')
  cpSync(FIXTURE, repo, { recursive: true, filter: (src) => !src.includes('artifacts') })
  writeFileSync(path.join(repo, '.env'), 'API_KEY=fixture-secret-value-abc123\n', 'utf8')
  return repo
}

function makeContext() {
  const tools = new Map()
  return {
    ctx: {
      tools: {
        register(definition) {
          tools.set(definition.name, definition)
          return () => tools.delete(definition.name)
        },
      },
      effect(body) {
        const dispose = body()
        return { dispose: async () => { if (typeof dispose === 'function') dispose() } }
      },
    },
    tools,
  }
}

test('packed tarball carries the core and works without the checkout', async () => {
  const packed = pack()
  assert.equal(existsSync(packed.tarball), true, 'tarball missing')
  const listing = execFileSync('tar', ['-tzf', packed.tarball], { encoding: 'utf8' })
  for (const expected of [
    'package/index.js',
    'package/lib/paths.js',
    'package/lib/core-runner.js',
    'package/cordis.patch.yml',
    'package/package.json',
    'package/vendor/core/scripts/build_flow.py',
    'package/vendor/core/scripts/render_flow.py',
    'package/vendor/core/assets/workflow_template.html',
    'package/vendor/core/tools/pfe_cli.py',
    'package/vendor/core/pfe/index.py',
    'package/vendor/core/pfe/retrieval.py',
  ]) {
    assert.ok(listing.includes(expected), `${expected} missing from tarball`)
  }

  const workdir = mkdtempSync(path.join(os.tmpdir(), 'pfe-packed-'))
  const installDir = path.join(workdir, 'installed')
  const repo = fixtureCopy(workdir)
  try {
    extract(packed.tarball, installDir)
    // The extracted package has no repository around it: resolveCoreRoot must
    // pick vendor/core, not a parent checkout.
    const paths = await import(pathToFileURL(path.join(installDir, 'lib', 'paths.js')).href)
    const core = paths.resolveCoreRoot({ packageRoot: installDir, env: {} })
    assert.equal(core.source, 'vendor', `core source was ${core.source}`)
    assert.ok(core.script.startsWith(installDir), core.script)

    const entry = await import(pathToFileURL(path.join(installDir, 'index.js')).href)
    const { ctx, tools } = makeContext()
    entry.apply(ctx, { allowedRoots: [workdir] })
    const tool = tools.get(entry.TOOL_NAME)
    assert.ok(tool, 'tool not registered by packed package')
    const result = await tool.execute(
      { repository_path: repo, flow_request: REQUEST },
      { signal: new AbortController().signal },
    )
    assert.equal(result.status, 'ok')
    for (const key of ['flow_json', 'flow_html', 'overview', 'run']) {
      assert.equal(path.isAbsolute(result.artifacts[key]), false, `${key} must be relative`)
      assert.equal(existsSync(path.join(repo, result.artifacts[key])), true, `${key} missing`)
    }
    assert.ok(result.artifacts.flow_html.startsWith('artifacts/flows/'))

    // The packed install must also carry the knowledge layer: index + search
    // have to work from the tarball alone, with no checkout around it.
    const indexTool = tools.get('project_code_index')
    const searchTool = tools.get('project_code_search')
    assert.ok(indexTool, 'project_code_index missing from packed install')
    assert.ok(searchTool, 'project_code_search missing from packed install')
    const built = await indexTool.execute(
      { repository_path: repo, mode: 'full' },
      { signal: new AbortController().signal },
    )
    assert.ok(built.files_indexed > 0)
    const found = await searchTool.execute(
      { repository_path: repo, query: 'export_report' },
      { signal: new AbortController().signal },
    )
    assert.equal(found.results[0].symbol, 'exportReport')
  } finally {
    rmSync(workdir, { recursive: true, force: true })
    rmSync(packed.tarball, { force: true })
  }
})

test('packed manifest keeps metadata and drops checkout-only scripts', () => {
  const packed = pack()
  const workdir = mkdtempSync(path.join(os.tmpdir(), 'pfe-manifest-'))
  try {
    extract(packed.tarball, workdir)
    const manifest = JSON.parse(
      execFileSync('node', ['-e', `process.stdout.write(require('node:fs').readFileSync(${JSON.stringify(path.join(workdir, 'package.json'))}, 'utf8'))`], { encoding: 'utf8' }),
    )
    assert.equal(manifest.name, 'dsh-project-flow-explainer')
    assert.equal(manifest.main, './index.js')
    assert.equal(manifest.type, 'module')
    assert.equal(manifest.engines.dsh, '0.2.2-rc.2')
    assert.equal(manifest.scripts, undefined, 'packed manifest should not keep dev scripts')
    assert.ok(manifest.dsh.bundle.patch, 'bundle patch missing')
    assert.ok(Array.isArray(manifest.files), 'files list missing')
  } finally {
    rmSync(workdir, { recursive: true, force: true })
    rmSync(packed.tarball, { force: true })
  }
})