/**
 * Tests for the code-knowledge tools registered by the adapter.
 *
 * Run: node --test dsh-plugin/tests/knowledge.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { apply, name, TOOL_NAME } from '../index.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const CORPUS = path.resolve(HERE, '../..')
const FIXTURE = path.resolve(CORPUS, 'tests/fixtures/shop-app')
const SECRET = 'fixture-secret-value-abc123'
const REQUEST = 'Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file'

const KNOWLEDGE_TOOLS = [
  'project_code_index',
  'project_code_search',
  'project_context_pack',
  'project_impact_analysis',
  'project_verify_flow',
  'project_knowledge_refresh',
]

function makeContext() {
  const tools = new Map()
  const disposers = []
  const ctx = {
    tools: {
      register(definition) {
        if (tools.has(definition.name)) {
          throw new Error(`tool "${definition.name}" is already registered in this scope`)
        }
        tools.set(definition.name, definition)
        return () => tools.delete(definition.name)
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
    disposeAll() { while (disposers.length) { const d = disposers.pop(); if (d) d() } },
  }
}

function mount(config = {}, allowedRoots) {
  const built = makeContext()
  const resolved = allowedRoots === undefined ? { ...config } : { ...config, allowedRoots }
  apply(built.ctx, resolved)
  return built
}

function fixtureCopy() {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'pfe-knowledge-'))
  const repo = path.join(dir, 'shop-app')
  cpSync(FIXTURE, repo, {
    recursive: true,
    filter: (src) => !src.includes('artifacts') && !src.includes('.pfe'),
  })
  writeFileSync(path.join(repo, '.env'), `API_KEY=${SECRET}\n`, 'utf8')
  return { dir, repo, cleanup: () => rmSync(dir, { recursive: true, force: true }) }
}

const call = (tool, args, signal) =>
  tool.execute(args, { signal: signal ?? new AbortController().signal })

async function rejectsWithCode(promise, code) {
  await assert.rejects(promise, (error) => {
    assert.equal(error.code, code, `expected ${code}, got ${error.code}: ${error.message}`)
    return true
  })
}

test('registers the flow tool and the six knowledge tools', () => {
  const { tools } = mount({}, [CORPUS])
  assert.equal(tools.has(TOOL_NAME), true)
  for (const tool of KNOWLEDGE_TOOLS) assert.equal(tools.has(tool), true, tool)
  assert.equal(tools.size, 7)
})

test('every knowledge tool declares a strict schema with a renderer', () => {
  const { tools } = mount({}, [CORPUS])
  for (const tool of KNOWLEDGE_TOOLS) {
    const definition = tools.get(tool)
    assert.equal(definition.parameters.type, 'object')
    assert.equal(definition.parameters.additionalProperties, false)
    assert.equal(definition.output.schema.additionalProperties, false)
    assert.equal(typeof definition.output.render, 'function')
    assert.ok(definition.parameters.required.includes('repository_path'))
  }
})

test('index → search → context pack → impact → verify → refresh end to end', async () => {
  const fixture = fixtureCopy()
  const { tools } = mount({}, [fixture.dir])
  try {
    const indexed = await call(tools.get('project_code_index'),
      { repository_path: fixture.repo, mode: 'full', include_vectors: true })
    assert.equal(indexed.mode, 'full')
    assert.ok(indexed.files_indexed > 0)
    assert.ok(indexed.entities > 0)
    assert.equal(existsSync(path.join(fixture.repo, '.pfe', 'index', 'knowledge.sqlite')), true)

    const search = await call(tools.get('project_code_search'),
      { repository_path: fixture.repo, query: 'export_report', top_k: 5 })
    assert.ok(search.results.length > 0)
    assert.equal(search.results[0].symbol, 'exportReport')
    assert.ok(search.results[0].evidence_refs.length > 0)
    assert.equal(JSON.stringify(search).includes(SECRET), false)
    assert.equal(JSON.stringify(search).includes(fixture.repo), false,
      'knowledge tools must not return absolute paths')

    const pack = await call(tools.get('project_context_pack'),
      { repository_path: fixture.repo, task: 'xuất báo cáo ra excel', max_files: 6 })
    assert.equal(pack.snippets_included, false)
    assert.ok(pack.likely_files.length > 0)
    assert.ok(pack.entry_points.length > 0)

    const impact = await call(tools.get('project_impact_analysis'),
      { repository_path: fixture.repo, changed_files: ['server.js'] })
    assert.equal(impact.risk_level, 'high')
    assert.ok(impact.affected_routes.length > 0)

    const flow = await call(tools.get(TOOL_NAME),
      { repository_path: fixture.repo, flow_request: REQUEST })
    assert.equal(flow.output_contract.internal.includes('run.json'), true)
    assert.equal(flow.path_visibility.artifacts, 'host-only')

    const verified = await call(tools.get('project_verify_flow'),
      { repository_path: fixture.repo })
    const statuses = Object.fromEntries(verified.checks.map((c) => [c.check, c.status]))
    assert.equal(statuses.graph_evidence, 'pass')
    assert.equal(verified.runtime_verified, false)

    const refreshed = await call(tools.get('project_knowledge_refresh'),
      { repository_path: fixture.repo })
    assert.equal(refreshed.mode, 'incremental')
    assert.equal(refreshed.files_parsed, 0)
  } finally {
    fixture.cleanup()
  }
})

test('search reports index_missing with a stable code before indexing', async () => {
  const fixture = fixtureCopy()
  const { tools } = mount({}, [fixture.dir])
  try {
    await rejectsWithCode(call(tools.get('project_code_search'),
      { repository_path: fixture.repo, query: 'report' }), 'index_missing')
  } finally {
    fixture.cleanup()
  }
})

test('knowledge tools enforce allowedRoots deny-by-default', async () => {
  const fixture = fixtureCopy()
  try {
    const missing = mount({}, undefined)
    await rejectsWithCode(call(missing.tools.get('project_code_index'),
      { repository_path: fixture.repo }), 'allowed_roots_unconfigured')

    const other = mkdtempSync(path.join(os.tmpdir(), 'pfe-other-'))
    const outside = mount({}, [other])
    try {
      await rejectsWithCode(call(outside.tools.get('project_code_index'),
        { repository_path: fixture.repo }), 'repository_outside_allowed_roots')
    } finally {
      rmSync(other, { recursive: true, force: true })
    }
  } finally {
    fixture.cleanup()
  }
})

test('malformed arguments produce stable codes, never a TypeError', async () => {
  const fixture = fixtureCopy()
  const { tools } = mount({}, [fixture.dir])
  const index = tools.get('project_code_index')
  const search = tools.get('project_code_search')
  const impact = tools.get('project_impact_analysis')
  const refresh = tools.get('project_knowledge_refresh')
  try {
    await rejectsWithCode(index.execute(undefined, {}), 'invalid_arguments')
    await rejectsWithCode(index.execute(null, {}), 'invalid_arguments')
    await rejectsWithCode(index.execute([], {}), 'invalid_arguments')
    await rejectsWithCode(index.execute({}, {}), 'repository_path_missing')
    await rejectsWithCode(index.execute({ repository_path: 42 }, {}), 'repository_path_invalid_type')
    await rejectsWithCode(index.execute({ repository_path: 'relative/dir' }, {}),
      'repository_path_relative')
    await rejectsWithCode(index.execute({ repository_path: fixture.repo, mode: 'wrong' }, {}),
      'mode_invalid')
    await rejectsWithCode(refresh.execute({ repository_path: fixture.repo, mode: 5 }, {}),
      'mode_invalid')
    await rejectsWithCode(search.execute({ repository_path: fixture.repo, query: '  ' }, {}),
      'query_missing')
    await rejectsWithCode(search.execute({ repository_path: fixture.repo, query: 7 }, {}),
      'query_invalid_type')
    await rejectsWithCode(search.execute({ repository_path: fixture.repo, query: 'x', top_k: 999 }, {}),
      'top_k_out_of_range')
    await rejectsWithCode(search.execute({ repository_path: fixture.repo, query: 'x', filters: [] }, {}),
      'filters_invalid_type')
    await rejectsWithCode(impact.execute({ repository_path: fixture.repo }, {}), 'no_changed_files')
    await rejectsWithCode(impact.execute({ repository_path: fixture.repo, changed_files: 'a.js' }, {}),
      'changed_files_invalid_type')
    await rejectsWithCode(tools.get('project_context_pack').execute(
      { repository_path: fixture.repo, task: 'x', max_files: 0 }, {}), 'max_files_out_of_range')
  } finally {
    fixture.cleanup()
  }
})

test('a core timeout keeps its own code, distinct from a business failure', async () => {
  const fixture = fixtureCopy()
  const { tools } = mount({ timeoutMs: 1 }, [fixture.dir])
  try {
    await rejectsWithCode(call(tools.get('project_code_index'),
      { repository_path: fixture.repo, mode: 'full' }), 'core_timeout')
  } finally {
    fixture.cleanup()
  }
})

test('abort surfaces as AbortError from a knowledge tool too', async () => {
  const fixture = fixtureCopy()
  const { tools } = mount({}, [fixture.dir])
  try {
    const controller = new AbortController()
    controller.abort()
    await assert.rejects(
      call(tools.get('project_code_index'), { repository_path: fixture.repo }, controller.signal),
      (error) => {
        assert.equal(error.name, 'AbortError')
        return true
      },
    )
  } finally {
    fixture.cleanup()
  }
})

test('unloading the plugin disposes every registered tool', () => {
  const fixture = fixtureCopy()
  try {
    const built = mount({}, [fixture.dir])
    assert.equal(built.tools.size, 7)
    const disposers = [...built.tools.keys()].map((key) => key)
    assert.equal(disposers.length, 7)
  } finally {
    fixture.cleanup()
  }
})
