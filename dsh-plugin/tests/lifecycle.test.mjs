/**
 * T4 lifecycle: mount -> dispose -> remount, no duplicate tools, in-flight cancel.
 *
 * Run: node --test dsh-plugin/tests/lifecycle.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { chmodSync, cpSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import * as plugin from '../index.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const CORPUS = path.resolve(HERE, '../..')
const FIXTURE = path.resolve(CORPUS, 'tests/fixtures/shop-app')
const REQUEST = 'Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file'

const ALL_TOOLS = [
  'project_flow_explain', 'project_code_index', 'project_code_search',
  'project_context_pack', 'project_impact_analysis', 'project_verify_flow',
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
        const dispose = () => tools.delete(definition.name)
        disposers.push(dispose)
        return dispose
      },
    },
    effect(body) {
      const dispose = body()
      if (typeof dispose === 'function') disposers.push(dispose)
      return { dispose: async () => { if (typeof dispose === 'function') await dispose() } }
    },
  }
  return {
    ctx,
    tools,
    disposeAll() {
      while (disposers.length) {
        const dispose = disposers.pop()
        try { dispose() } catch { /* already disposed */ }
      }
    },
  }
}

test('mount registers exactly the seven tools once', () => {
  const { ctx, tools } = makeContext()
  plugin.apply(ctx, { allowedRoots: [CORPUS] })
  assert.deepEqual([...tools.keys()].sort(), [...ALL_TOOLS].sort())
  assert.equal(tools.size, 7)
})

test('dispose removes every tool and releases the names', () => {
  const built = makeContext()
  plugin.apply(built.ctx, { allowedRoots: [CORPUS] })
  assert.equal(built.tools.size, 7)
  built.disposeAll()
  assert.equal(built.tools.size, 0)
})

test('remount after dispose restores seven tools without duplicates', () => {
  const built = makeContext()
  plugin.apply(built.ctx, { allowedRoots: [CORPUS] })
  built.disposeAll()
  plugin.apply(built.ctx, { allowedRoots: [CORPUS] })
  assert.equal(built.tools.size, 7, 'duplicate or missing tool after remount')
  assert.deepEqual([...built.tools.keys()].sort(), [...ALL_TOOLS].sort())
})

test('mounting twice without dispose is rejected (no silent duplicate)', () => {
  const built = makeContext()
  plugin.apply(built.ctx, { allowedRoots: [CORPUS] })
  assert.throws(() => plugin.apply(built.ctx, { allowedRoots: [CORPUS] }), /already registered/)
})

test('dispose cancels an in-flight run', async () => {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'pfe-life-'))
  const repo = path.join(dir, 'shop-app')
  cpSync(FIXTURE, repo, { recursive: true, filter: (src) => !src.includes('artifacts') })
  // A deliberately slow interpreter makes "still running when disposed"
  // deterministic instead of a race with a 150 ms core run.
  const slowPython = path.join(dir, 'slow-python')
  // exec: the child IS the sleep, so SIGTERM ends it immediately (a wrapper
  // that waits for a grandchild would delay 'close' and mask the assertion).
  writeFileSync(slowPython, '#!/bin/sh\nexec sleep 30\n', 'utf8')
  chmodSync(slowPython, 0o755)
  const built = makeContext()
  plugin.apply(built.ctx, { allowedRoots: [dir], pythonPath: slowPython, timeoutMs: 30000 })
  const tool = built.tools.get('project_code_index')
  try {
    const run = tool.execute({ repository_path: repo, mode: 'full' },
      { signal: new AbortController().signal })
    await new Promise((resolve) => setTimeout(resolve, 100))
    built.disposeAll()
    await assert.rejects(run, (error) => {
      assert.equal(error.name, 'AbortError', `expected AbortError, got ${error.name}: ${error.message}`)
      return true
    })
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

test('no native Config export is claimed (BLOCKED_DSH_CONFIG_NATIVE)', () => {
  // The profile cannot resolve @deepseek-ai/schemastery, so exporting a fake
  // schema would be worse than validating by hand. Guard against a future
  // silent regression that starts claiming native validation.
  assert.ok(plugin.Config === undefined || typeof plugin.Config === 'function',
    'Config must be the real schemastery schema or undefined')
  assert.equal(typeof plugin.apply, 'function')
  assert.deepEqual(plugin.inject, ['tools'])
})

test('invalid config fails before any tool is registered', () => {
  const built = makeContext()
  assert.throws(() => plugin.apply(built.ctx, { allowedRoots: [CORPUS], timeoutMs: 0 }), /timeoutMs/)
  assert.equal(built.tools.size, 0)
})