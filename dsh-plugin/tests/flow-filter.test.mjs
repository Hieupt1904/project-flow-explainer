import test from 'node:test'
import assert from 'node:assert/strict'
import { cpSync, mkdtempSync, rmSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import os from 'node:os'
import path from 'node:path'
import * as plugin from '../index.js'

const ROOT = path.resolve(import.meta.dirname, '..', '..')
const FIXTURE = path.join(ROOT, 'tests', 'fixtures', 'shop-app')

function mount(config) {
  const tools = new Map()
  const ctx = {
    tools: { register(definition) { tools.set(definition.name, definition); return () => {} } },
    effect(body) { body(); return { dispose: async () => {} } },
    on() { return () => {} },
    get() { return undefined },
    inject(_services, callback) {
      callback({ get: () => undefined, workingDirectory: { async ensure() { return '/tmp' } },
        commands: { register() { return () => {} } } })
    },
  }
  plugin.apply(ctx, config)
  return tools
}

test('filters.flow_id reaches the core instead of being dropped', async (t) => {
  const base = mkdtempSync(path.join(os.tmpdir(), 'pfe-flowid-'))
  const repo = path.join(base, 'repo')
  cpSync(FIXTURE, repo, { recursive: true, filter: (src) => !src.includes('.pfe') })
  t.after(() => rmSync(base, { recursive: true, force: true }))

  const tools = mount({ allowedRoots: [base] })
  const index = tools.get('project_code_index')
  const search = tools.get('project_code_search')
  await index.execute({ repository_path: repo, mode: 'full' }, { signal: undefined })

  // Two flows, so a filter that is ignored returns too much instead of too little.
  const python = process.env.PFE_PYTHON || 'python3'
  execFileSync(python, ['-c', `
import sys
sys.path.insert(0, ${JSON.stringify(ROOT)})
from pfe import index, flow as flow_mod, facts
root = ${JSON.stringify(repo)}
files, _, _ = facts.scan_repository(root, include_tests=False)
known = {i.rel for i in files}; bn = facts.index_basenames(files)
for i in files: i.imports = facts.find_imports(i.text(), i.rel, known, bn)
for fid, phrase in (("flow-export", "xuất báo cáo"), ("flow-preview", "xem trước")):
    g, _, _, _ = flow_mod.build_graph(phrase, files, facts.git_state(root))
    g["flow_id"] = fid
    index.record_flow(root, g, "artifacts/flows/" + fid)
`], { stdio: 'pipe' })

  const unfiltered = await search.execute({ repository_path: repo, query: 'export' },
    { signal: undefined })
  const filtered = await search.execute(
    { repository_path: repo, query: 'export', filters: { flow_id: 'flow-export' } },
    { signal: undefined })
  const unknown = await search.execute(
    { repository_path: repo, query: 'export', filters: { flow_id: 'no-such-flow' } },
    { signal: undefined })

  assert.deepEqual(filtered.filters_applied, { flow_id: 'flow-export' },
    'the applied filter must be echoed back')
  assert.ok(filtered.flow_filter, 'a flow filter must report what it did')
  assert.equal(filtered.flow_filter.matched_flow, true)
  assert.ok(filtered.results.length > 0, 'a known flow must still return its members')
  assert.ok(filtered.results.length <= unfiltered.results.length,
    'a flow filter can only narrow the result set')
  assert.equal(unknown.results.length, 0, 'an unknown flow must not degrade into no filter')
  assert.ok(unknown.warnings.some((item) => item.includes('flow_id')))
})
