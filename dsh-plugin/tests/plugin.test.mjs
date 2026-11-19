/**
 * Adapter tests. They mount the plugin into a fake Context that enforces tool
 * name uniqueness, so a missing disposer shows up as a duplicate-registration
 * failure rather than a silent double mount. Behaviour under test: path policy,
 * artifact containment, cancellation identity and result mapping.
 *
 * Run: node --test dsh-plugin/tests/plugin.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import {
  cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync,
} from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { apply, inject, name, TOOL_NAME } from '../index.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const FIXTURE = path.resolve(HERE, '../../tests/fixtures/shop-app')
const CORPUS = path.resolve(HERE, '../..')
const REQUEST = 'Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file'
const SECRET = 'fixture-secret-value-abc123'

function makeContext() {
  const tools = new Map()
  const disposers = []
  const toolDisposers = []
  const ctx = {
    tools: {
      register(definition) {
        if (tools.has(definition.name)) {
          throw new Error(`tool "${definition.name}" is already registered in this scope`)
        }
        tools.set(definition.name, definition)
        const dispose = () => tools.delete(definition.name)
        toolDisposers.push(dispose)
        return dispose
      },
    },
    effect(body) {
      const dispose = body()
      disposers.push(dispose)
      return { dispose: async () => { if (typeof dispose === 'function') await dispose() } }
    },
  }
  return {
    ctx,
    tools,
    disposeAll() {
      while (toolDisposers.length > 0) {
        const dispose = toolDisposers.pop()
        if (typeof dispose === 'function') dispose()
      }
      while (disposers.length > 0) {
        const dispose = disposers.pop()
        if (typeof dispose === 'function') dispose()
      }
    },
  }
}

function mount(config = {}, allowedRoots) {
  const built = makeContext()
  const resolved = allowedRoots === undefined ? { ...config } : { ...config, allowedRoots }
  apply(built.ctx, resolved)
  return { ...built, tool: built.tools.get(TOOL_NAME) }
}

function fixtureCopy() {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'pfe-plugin-'))
  const repo = path.join(dir, 'shop-app')
  cpSync(FIXTURE, repo, { recursive: true, filter: (src) => !src.includes('artifacts') })
  writeFileSync(path.join(repo, '.env'), `API_KEY=${SECRET}\n`, 'utf8')
  return { dir, repo, cleanup: () => rmSync(dir, { recursive: true, force: true }) }
}

function call(tool, args, signal) {
  return tool.execute(args, { signal: signal ?? new AbortController().signal })
}

async function rejectsWithCode(promise, code) {
  await assert.rejects(promise, (error) => {
    assert.equal(error.code, code, `expected code ${code}, got ${error.code}: ${error.message}`)
    return true
  })
}

test('exports a Cordis plugin shape with one tool', () => {
  assert.equal(name, 'project-flow-explainer')
  assert.deepEqual(inject, ['tools'])
  const { tool } = mount({}, [CORPUS])
  assert.ok(tool)
  assert.equal(tool.parameters.required.includes('repository_path'), true)
  assert.equal(tool.parameters.required.includes('flow_request'), true)
  assert.equal(typeof tool.output.render, 'function')
  assert.equal(tool.isConcurrencySafe({}), false)
})

test('end-to-end: builds four artifacts through the core CLI', async () => {
  const fixture = fixtureCopy()
  const { tool } = mount({}, [fixture.dir])
  try {
    const result = await call(tool, { repository_path: fixture.repo, flow_request: REQUEST })
    assert.equal(result.status, 'ok')
    for (const key of ['flow_json', 'flow_html', 'overview', 'run']) {
      // Canonical output is repository-relative: no absolute workstation path.
      assert.equal(path.isAbsolute(result.artifacts[key]), false, key)
      assert.equal(existsSync(path.join(fixture.repo, result.artifacts[key])), true, `${key} missing`)
    }
    assert.equal(result.path_base, 'repository')
    assert.equal(result.path_visibility.absolute_paths_returned, false)
    assert.equal(JSON.stringify(result).includes(fixture.repo), false,
      'tool result must not carry an absolute path')
    assert.equal(result.artifacts_dir.split(path.sep).join('/'), 'artifacts/flows/' + result.slug)
    assert.ok(result.counts.verified > 0)
    assert.equal(result.flow_id, result.slug)
    const rendered = tool.output.render({}, result)
    assert.equal(rendered[0].type, 'text')
    assert.ok(rendered[0].text.includes(result.artifacts.flow_html))
  } finally {
    fixture.cleanup()
  }
})

test('tool result never carries source secrets', async () => {
  const fixture = fixtureCopy()
  const { tool } = mount({}, [fixture.dir])
  try {
    const result = await call(tool, { repository_path: fixture.repo, flow_request: REQUEST })
    assert.equal(JSON.stringify(result).includes(SECRET), false)
    for (const key of ['flow_json', 'flow_html', 'overview', 'run']) {
      const file = path.join(fixture.repo, result.artifacts[key])
      assert.equal(readFileSync(file, 'utf8').includes(SECRET), false, key)
    }
  } finally {
    fixture.cleanup()
  }
})

test('adapter and direct core produce the same graph', async () => {
  const fixture = fixtureCopy()
  const { tool } = mount({}, [fixture.dir])
  try {
    const viaAdapter = await call(tool, { repository_path: fixture.repo, flow_request: REQUEST })
    const direct = await new Promise((resolve, reject) => {
      const child = spawn('python3', [
        path.resolve(HERE, '../../scripts/build_flow.py'),
        '--repo', fixture.repo, '--request', REQUEST, '--json', '--slug', 'direct',
      ], { shell: false })
      let out = ''
      child.stdout.on('data', (chunk) => { out += chunk })
      child.on('error', reject)
      child.on('close', (code) => (code === 0 ? resolve(JSON.parse(out)) : reject(new Error(`exit ${code}`))))
    })
    const read = (file) => JSON.parse(readFileSync(file, 'utf8'))
    const shape = (graph) => graph.nodes.map((node) => [
      node.id, node.type, node.title, node.confidence,
      (node.source_refs || []).map((ref) => ref.path),
    ])
    assert.deepEqual(
      shape(read(path.join(fixture.repo, viaAdapter.artifacts.flow_json))),
      shape(read(direct.paths.flow_json)),
    )
  } finally {
    fixture.cleanup()
  }
})

// --- TASK 1: allowedRoots deny-by-default ---------------------------------

test('missing allowedRoots denies every call (deny-by-default)', async () => {
  const fixture = fixtureCopy()
  const { tool } = mount({}, undefined)
  try {
    await rejectsWithCode(call(tool, { repository_path: fixture.repo, flow_request: REQUEST }),
      'allowed_roots_unconfigured')
    assert.equal(existsSync(path.join(fixture.repo, 'artifacts')), false)
  } finally {
    fixture.cleanup()
  }
})

test('empty allowedRoots denies every call', async () => {
  const fixture = fixtureCopy()
  const { tool } = mount({}, [])
  try {
    await rejectsWithCode(call(tool, { repository_path: fixture.repo, flow_request: REQUEST }),
      'allowed_roots_unconfigured')
  } finally {
    fixture.cleanup()
  }
})

test('repository outside allowedRoots is rejected', async () => {
  const fixture = fixtureCopy()
  const other = mkdtempSync(path.join(os.tmpdir(), 'pfe-other-'))
  const { tool } = mount({}, [other])
  try {
    await rejectsWithCode(call(tool, { repository_path: fixture.repo, flow_request: REQUEST }),
      'repository_outside_allowed_roots')
  } finally {
    fixture.cleanup()
    rmSync(other, { recursive: true, force: true })
  }
})

test('symlink that escapes allowedRoots is rejected', async () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'pfe-root-'))
  const outside = mkdtempSync(path.join(os.tmpdir(), 'pfe-outside-'))
  try {
    const link = path.join(root, 'linked-repo')
    try {
      symlinkSync(outside, link)
    } catch {
      return // symlinks unavailable: nothing to assert
    }
    const { tool } = mount({}, [root])
    await rejectsWithCode(call(tool, { repository_path: link, flow_request: REQUEST }),
      'repository_outside_allowed_roots')
  } finally {
    rmSync(root, { recursive: true, force: true })
    rmSync(outside, { recursive: true, force: true })
  }
})

test('relative and missing repository paths are rejected', async () => {
  const { tool } = mount({}, [CORPUS])
  await rejectsWithCode(call(tool, { repository_path: 'relative/dir', flow_request: REQUEST }),
    'repository_path_relative')
  await rejectsWithCode(call(tool, { repository_path: '/nope/definitely/missing', flow_request: REQUEST }),
    'repository_not_found')
})

// --- TASK 2: artifact containment -----------------------------------------

test('output_directory must be exactly artifacts/flows', async () => {
  const fixture = fixtureCopy()
  const { tool } = mount({}, [fixture.dir])
  try {
    for (const bad of ['.', 'src', 'docs', 'tmp', '../outside', fixture.repo]) {
      await rejectsWithCode(
        call(tool, { repository_path: fixture.repo, flow_request: REQUEST, output_directory: bad }),
        'invalid_artifact_root',
      )
    }
    for (const created of ['src', 'docs', 'tmp', 'outside']) {
      assert.equal(existsSync(path.join(fixture.dir, created)), false, created)
      assert.equal(existsSync(path.join(fixture.repo, created)), false, created)
    }
    const ok = await call(tool, {
      repository_path: fixture.repo, flow_request: REQUEST, output_directory: 'artifacts/flows',
    })
    assert.equal(ok.status, 'ok')
  } finally {
    fixture.cleanup()
  }
})

test('symlinked artifacts directory is rejected', async () => {
  const fixture = fixtureCopy()
  const outside = path.join(fixture.dir, 'outside')
  mkdirSync(outside)
  try {
    symlinkSync(outside, path.join(fixture.repo, 'artifacts'))
  } catch {
    fixture.cleanup()
    return
  }
  const { tool } = mount({}, [fixture.dir])
  try {
    await rejectsWithCode(call(tool, { repository_path: fixture.repo, flow_request: REQUEST }),
      'artifact_symlink_escape')
    assert.equal(existsSync(path.join(outside, 'flows')), false)
  } finally {
    fixture.cleanup()
  }
})

// --- TASK 5: cancellation vs failure --------------------------------------

test('abort surfaces as AbortError, not a business failure', async () => {
  const fixture = fixtureCopy()
  const { tool } = mount({}, [fixture.dir])
  try {
    const controller = new AbortController()
    controller.abort()
    await assert.rejects(
      () => call(tool, { repository_path: fixture.repo, flow_request: REQUEST }, controller.signal),
      (error) => {
        assert.equal(error.name, 'AbortError')
        assert.notEqual(error.code, 'core_failed')
        return true
      },
    )
  } finally {
    fixture.cleanup()
  }
})

test('timeout is reported as core_timeout, distinct from abort', async () => {
  const fixture = fixtureCopy()
  const { tool } = mount({ timeoutMs: 1 }, [fixture.dir])
  try {
    await rejectsWithCode(call(tool, { repository_path: fixture.repo, flow_request: REQUEST }),
      'core_timeout')
  } finally {
    fixture.cleanup()
  }
})

test('missing flow request is rejected before the core runs', async () => {
  const fixture = fixtureCopy()
  const { tool } = mount({}, [fixture.dir])
  try {
    await rejectsWithCode(call(tool, { repository_path: fixture.repo, flow_request: '  ' }),
      'flow_request_missing')
  } finally {
    fixture.cleanup()
  }
})

// --- lifecycle + config ---------------------------------------------------

test('unload removes the tool and reload registers it again', () => {
  const built = mount({}, [CORPUS])
  assert.equal(built.tools.has(TOOL_NAME), true)
  built.disposeAll()
  assert.equal(built.tools.size, 0, 'dispose must unregister the tool')
  apply(built.ctx, { allowedRoots: [CORPUS] })
  assert.equal(built.tools.has(TOOL_NAME), true)
  assert.throws(() => apply(built.ctx, { allowedRoots: [CORPUS] }), /already registered/)
})

test('rejects invalid configuration at load time', () => {
  assert.throws(() => mount({ timeoutMs: 0 }, [CORPUS]), /timeoutMs/)
  assert.throws(() => mount({ allowedRoots: 'nope' }, undefined), /allowedRoots/)
  const brokenCore = path.join(os.tmpdir(), 'pfe-no-core-here')
  assert.throws(() => mount({ coreRoot: brokenCore }, [CORPUS]), /coreRoot/)
})