/**
 * Argument contract: the declared parameter list is enforced.
 *
 * `ToolsService.register()` does not validate arguments and this plugin builds
 * its tool definitions by hand (no `defineTool`), so the declared
 * `additionalProperties: false` would otherwise be decorative: a typo like
 * `repositry_path` would look like a missing argument instead of a wrong one.
 *
 * Run: node --test dsh-plugin/tests/arguments.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import path from 'node:path'
import os from 'node:os'
import { cpSync, mkdtempSync, rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import * as plugin from '../index.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const CORPUS = path.resolve(HERE, '../..')
const FIXTURE = path.resolve(CORPUS, 'tests/fixtures/shop-app')

function mount() {
  const tools = new Map()
  const ctx = {
    tools: {
      register(definition) {
        tools.set(definition.name, definition)
        return () => tools.delete(definition.name)
      },
    },
    effect(body) {
      const dispose = body()
      return { dispose: async () => { if (typeof dispose === 'function') await dispose() } }
    },
    on() { return () => {} },
  }
  plugin.apply(ctx, { allowedRoots: [CORPUS] })
  return tools
}

/**
 * A throwaway copy of the fixture. Index/search must never run against a
 * checked-in fixture: the run writes `.pfe/`, and repo policy forbids it
 * (`scripts/check_repo_policy.py`), while `test_source_files_are_untouched`
 * compares the fixture's file hashes.
 */
function tempRepo(t) {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'pfe-args-'))
  cpSync(FIXTURE, dir, { recursive: true })
  t.after(() => rmSync(dir, { recursive: true, force: true }))
  return dir
}

async function codeOf(tools, name, args) {
  try {
    await tools.get(name).execute(args, { signal: undefined })
    return 'ok'
  } catch (error) {
    return error.code ?? error.message
  }
}

const CASES = [
  ['project_flow_explain', { repository_path: CORPUS, flow_request: 'x', repositry_path: CORPUS }],
  ['project_code_index', { repository_path: CORPUS, modes: 'full' }],
  ['project_code_search', { repository_path: CORPUS, query: 'x', topk: 5 }],
  ['project_context_pack', { repository_path: CORPUS, task: 'x', maxfiles: 3 }],
  ['project_impact_analysis', { repository_path: CORPUS, changed_files: ['a.js'], diffs: '' }],
  ['project_verify_flow', { repository_path: CORPUS, ui_verified: true }],
  ['project_knowledge_refresh', { repository_path: CORPUS, includes_vectors: true }],
]

for (const [tool, args] of CASES) {
  test(`${tool} rejects an undeclared argument`, async () => {
    const tools = mount()
    assert.equal(await codeOf(tools, tool, args), 'unknown_arguments')
  })
}

test('declared arguments are still accepted', async (t) => {
  const tools = mount()
  // Not `unknown_arguments`: the call reaches the tool's own validation.
  assert.notEqual(
    await codeOf(tools, 'project_code_search', { repository_path: tempRepo(t), query: 'export_report', top_k: 3 }),
    'unknown_arguments',
  )
  assert.notEqual(
    await codeOf(tools, 'project_code_index', { repository_path: tempRepo(t), mode: 'incremental', include_vectors: false }),
    'unknown_arguments',
  )
})

test('every declared parameter is accepted by the rejection list', async () => {
  // Meaningful only if it is driven by the schema: if a parameter is declared in
  // `parameters.properties` but missing from the hand-written allow-list, calling
  // with that key would be rejected as unknown — a real drift bug.
  const tools = mount()
  for (const [tool] of CASES) {
    const declared = Object.keys(tools.get(tool).parameters.properties)
    const args = Object.fromEntries(declared.map((key) => [key, undefined]))
    assert.notEqual(
      await codeOf(tools, tool, args),
      'unknown_arguments',
      `${tool}: a declared parameter is missing from the allow-list (${declared.join(', ')})`,
    )
  }
})
