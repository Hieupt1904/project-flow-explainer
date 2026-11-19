/**
 * Adapter tests. They mount the plugin into a fake Context that enforces tool
 * name uniqueness, so a missing disposer shows up as a duplicate-registration
 * failure rather than a silent double mount.
 *
 * Run: node --test dsh-plugin/tests/
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { apply, inject, name, TOOL_NAME } from '../index.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const FIXTURE = path.resolve(HERE, '../../tests/fixtures/shop-app')
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
        // Real Cordis ties this disposer to the plugin fiber; the fake does the
        // same so an unload test exercises the same teardown path.
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

function fixtureCopy() {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'pfe-plugin-'))
  const repo = path.join(dir, 'shop-app')
  cpSync(FIXTURE, repo, { recursive: true, filter: (src) => !src.includes('artifacts') })
  writeFileSync(path.join(repo, '.env'), `API_KEY=${SECRET}\n`, 'utf8')
  return { dir, repo, cleanup: () => rmSync(dir, { recursive: true, force: true }) }
}

test('exports a Cordis plugin shape with one tool', () => {
  assert.equal(name, 'project-flow-explainer')
  assert.deepEqual(inject, ['tools'])
  const { ctx, tools } = makeContext()
  apply(ctx, {})
  assert.equal(tools.size, 1)
  const tool = tools.get(TOOL_NAME)
  assert.equal(tool.parameters.required.includes('repository_path'), true)
  assert.equal(tool.parameters.required.includes('flow_request'), true)
  assert.equal(typeof tool.output.render, 'function')
  assert.equal(typeof tool.execute, 'function')
  assert.equal(tool.isConcurrencySafe({}), false)
})

test('end-to-end: builds three artifacts through the core CLI', async () => {
  const fixture = fixtureCopy()
  const { ctx, tools } = makeContext()
  try {
    apply(ctx, {})
    const tool = tools.get(TOOL_NAME)
    const result = await tool.execute(
      { repository_path: fixture.repo, flow_request: REQUEST },
      { signal: new AbortController().signal },
    )
    assert.equal(result.status, 'ok')
    for (const key of ['flow_json', 'flow_html', 'overview', 'run']) {
      assert.equal(existsSync(result.artifacts[key]), true, `${key} missing`)
      assert.equal(path.isAbsolute(result.artifacts[key]), true)
    }
    assert.match(result.artifacts.flow_html, /artifacts\/flows\//)
    assert.ok(result.counts.verified > 0)
    assert.equal(result.flow_id, result.slug)
    const html = readFileSync(result.artifacts.flow_html, 'utf8')
    assert.ok(html.includes(result.flow_id))
    assert.ok(!html.includes('__FLOW_JSON__'))
    const rendered = tool.output.render({}, result)
    assert.equal(rendered[0].type, 'text')
    assert.ok(rendered[0].text.includes(result.artifacts.flow_html))
  } finally {
    fixture.cleanup()
  }
})

test('tool result never carries source secrets', async () => {
  const fixture = fixtureCopy()
  const { ctx, tools } = makeContext()
  try {
    apply(ctx, {})
    const result = await tools.get(TOOL_NAME).execute(
      { repository_path: fixture.repo, flow_request: REQUEST },
      { signal: new AbortController().signal },
    )
    assert.equal(JSON.stringify(result).includes(SECRET), false)
    for (const key of ['flow_json', 'flow_html', 'overview', 'run']) {
      const text = readFileSync(result.artifacts[key], 'utf8')
      assert.equal(text.includes(SECRET), false, `secret leaked into ${key}`)
    }
  } finally {
    fixture.cleanup()
  }
})

test('adapter and direct core produce the same graph', async () => {
  const fixture = fixtureCopy()
  const { ctx, tools } = makeContext()
  try {
    apply(ctx, {})
    const viaAdapter = await tools.get(TOOL_NAME).execute(
      { repository_path: fixture.repo, flow_request: REQUEST },
      { signal: new AbortController().signal },
    )
    const direct = await new Promise((resolve, reject) => {
      const child = spawn('python3', [
        path.resolve(HERE, '../../scripts/build_flow.py'),
        '--repo', fixture.repo, '--request', REQUEST, '--json',
        '--out-dir', path.join(fixture.repo, 'artifacts', 'direct'), '--slug', 'direct',
      ], { shell: false })
      let out = ''
      child.stdout.on('data', (chunk) => { out += chunk })
      child.on('error', reject)
      child.on('close', (code) => (code === 0 ? resolve(JSON.parse(out)) : reject(new Error(`exit ${code}`))))
    })
    const read = (file) => JSON.parse(readFileSync(file, 'utf8'))
    const shape = (graph) => graph.nodes.map((node) => [
      node.id, node.type, node.title, node.confidence, (node.source_refs || []).map((ref) => ref.path),
    ])
    assert.deepEqual(shape(read(viaAdapter.artifacts.flow_json)), shape(read(direct.paths.flow_json)))
  } finally {
    fixture.cleanup()
  }
})

test('rejects a missing flow request before running the core', async () => {
  const fixture = fixtureCopy()
  const { ctx, tools } = makeContext()
  try {
    apply(ctx, {})
    await assert.rejects(
      () => tools.get(TOOL_NAME).execute(
        { repository_path: fixture.repo, flow_request: '   ' },
        { signal: new AbortController().signal },
      ),
      (error) => {
        assert.match(error.message, /flow_request/i)
        assert.match(error.hint, /xuất báo cáo/i)
        return true
      },
    )
  } finally {
    fixture.cleanup()
  }
})

test('rejects relative and missing repository paths', async () => {
  const { ctx, tools } = makeContext()
  apply(ctx, {})
  const tool = tools.get(TOOL_NAME)
  await assert.rejects(
    () => tool.execute({ repository_path: 'relative/dir', flow_request: REQUEST },
      { signal: new AbortController().signal }),
    /tuyệt đối/,
  )
  await assert.rejects(
    () => tool.execute({ repository_path: '/nope/definitely/missing', flow_request: REQUEST },
      { signal: new AbortController().signal }),
    /Không thấy thư mục repository/,
  )
})

test('rejects an artifact directory outside the approved repository', async () => {
  const fixture = fixtureCopy()
  const { ctx, tools } = makeContext()
  try {
    apply(ctx, {})
    await assert.rejects(
      () => tools.get(TOOL_NAME).execute(
        { repository_path: fixture.repo, flow_request: REQUEST, output_directory: '../outside' },
        { signal: new AbortController().signal },
      ),
      /nằm trong repository đã duyệt/,
    )
    assert.equal(existsSync(path.join(fixture.dir, 'outside')), false)
  } finally {
    fixture.cleanup()
  }
})

test('honours allowedRoots pinning', async () => {
  const fixture = fixtureCopy()
  const { ctx, tools } = makeContext()
  try {
    apply(ctx, { allowedRoots: [path.join(fixture.dir, 'somewhere-else')] })
    await assert.rejects(
      () => tools.get(TOOL_NAME).execute(
        { repository_path: fixture.repo, flow_request: REQUEST },
        { signal: new AbortController().signal },
      ),
      /ngoài phạm vi được phép/,
    )
  } finally {
    fixture.cleanup()
  }
})

test('an aborted call stops the child and reports cancellation', async () => {
  const fixture = fixtureCopy()
  const { ctx, tools } = makeContext()
  try {
    apply(ctx, {})
    const controller = new AbortController()
    controller.abort()
    await assert.rejects(
      () => tools.get(TOOL_NAME).execute(
        { repository_path: fixture.repo, flow_request: REQUEST },
        { signal: controller.signal },
      ),
      /huỷ|Core kết thúc/,
    )
  } finally {
    fixture.cleanup()
  }
})

test('unload removes the tool and reload registers it again', async () => {
  const { ctx, tools, disposeAll } = makeContext()
  apply(ctx, {})
  assert.equal(tools.has(TOOL_NAME), true)
  disposeAll()
  assert.equal(tools.size, 0, 'dispose must unregister the tool')
  apply(ctx, {})
  assert.equal(tools.has(TOOL_NAME), true)
  // A second mount without unloading must fail loudly instead of shadowing.
  assert.throws(() => apply(ctx, {}), /already registered/)
})

test('rejects invalid configuration at load time', () => {
  const { ctx } = makeContext()
  assert.throws(() => apply(ctx, { timeoutMs: 0 }), /timeoutMs/)
  assert.throws(() => apply(ctx, { allowedRoots: 'nope' }), /allowedRoots/)
  assert.throws(() => apply(ctx, { coreRoot: '/tmp/not-a-core' }), /build_flow\.py/)
})
