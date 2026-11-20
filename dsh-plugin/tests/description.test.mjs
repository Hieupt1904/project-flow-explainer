/**
 * Tool surface contract (T5): description completeness and answer shape.
 *
 * The model chooses a tool from its description alone, so a missing section is a
 * routing bug, not a style issue. Each of the seven tools must state when to
 * use it, when not to, what it needs, what it returns, what to do next, and how
 * far to trust it — and every renderer must end with the next action.
 *
 * Run: node --test dsh-plugin/tests/description.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import * as plugin from '../index.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const CORPUS = path.resolve(HERE, '../..')

const SECTIONS = ['DÙNG KHI', 'KHÔNG DÙNG KHI', 'ĐIỀU KIỆN', 'KẾT QUẢ', 'TIẾP THEO', 'GIỚI HẠN']
const WORKFLOW_TOOLS = [
  'project_flow_explain', 'project_context_pack',
  'project_impact_analysis', 'project_verify_flow',
]
const MAINTENANCE_TOOLS = [
  'project_code_index', 'project_code_search', 'project_knowledge_refresh',
]

function mount() {
  const tools = new Map()
  const ctx = {
    tools: { register(definition) { tools.set(definition.name, definition); return () => {} } },
    effect(body) { body(); return { dispose: async () => {} } },
    on() { return () => {} },
  }
  plugin.apply(ctx, { allowedRoots: [CORPUS] })
  return tools
}

test('seven tools keep their existing names (no rename without migration)', () => {
  const tools = mount()
  assert.deepEqual([...tools.keys()].sort(),
    [...WORKFLOW_TOOLS, ...MAINTENANCE_TOOLS].sort())
  assert.equal(tools.size, 7)
})

for (const name of [...WORKFLOW_TOOLS, ...MAINTENANCE_TOOLS]) {
  test(`${name} declares all six description sections`, () => {
    const tool = mount().get(name)
    const missing = SECTIONS.filter((section) => !tool.description.includes(section))
    assert.deepEqual(missing, [], `${name} is missing: ${missing.join(', ')}`)
  })

  test(`${name} renderer ends with the next action`, () => {
    const tool = mount().get(name)
    assert.match(tool.output.render.toString(), /Tiếp theo|tiếp theo/,
      `${name}: the renderer must tell the reader what to do next`)
  })
}

test('the default workflow tool says it is the default before editing', () => {
  const tool = mount().get('project_context_pack')
  assert.match(tool.description, /MẶC ĐỊNH trước khi sửa/)
})

test('maintenance tools are labelled as maintenance', () => {
  const tools = mount()
  for (const name of ['project_code_index', 'project_code_search', 'project_knowledge_refresh']) {
    assert.match(tools.get(name).description, /maintenance/,
      `${name} must say it is a maintenance tool so the model prefers the workflow tools`)
  }
})

test('verify description separates static scan from browser and test execution', () => {
  const text = mount().get('project_verify_flow').description
  assert.match(text, /HTML tĩnh/i)
  assert.match(text, /KHÔNG phải kiểm trình duyệt/i)
  assert.match(text, /KHÔNG phải đã chạy test/i)
})
