/**
 * Slash command contract: `/project-flow-explainer <request>`.
 *
 * The command is the human entry point — it must run the same core with the same
 * repository policy as the tool, return a rendered result instead of throwing,
 * and never report success for a failure.
 *
 * Run: node --test dsh-plugin/tests/command.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import os from 'node:os'
import path from 'node:path'
import { cpSync, mkdtempSync, rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import * as plugin from '../index.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const CORPUS = path.resolve(HERE, '../..')
const FIXTURE = path.resolve(CORPUS, 'tests/fixtures/shop-app')

function mount(applied = {}, { withCommands = true, cwd = CORPUS } = {}) {
  const tools = new Map()
  const commands = new Map()
  const ctx = {
    tools: { register(d) { tools.set(d.name, d); return () => {} } },
    effect(b) { b(); return { dispose: async () => {} } },
    on() { return () => {} },
    get() { return undefined },
    workingDirectory: { async ensure() { return cwd } },
    inject(services, cb) {
      if (!withCommands || !services.includes('commands')) return
      cb({
        commands: {
          register(definition) {
            commands.set(definition.name, definition)
            return () => commands.delete(definition.name)
          },
        },
      })
    },
  }
  plugin.apply(ctx, { allowedRoots: [CORPUS, os.tmpdir()], ...applied })
  return { tools, commands, ctx }
}

function tempRepo(t) {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'pfe-command-'))
  cpSync(FIXTURE, dir, { recursive: true })
  t.after(() => rmSync(dir, { recursive: true, force: true }))
  return dir
}

test('registers exactly one command next to the seven tools', () => {
  const { tools, commands } = mount()
  assert.equal(tools.size, 7)
  assert.deepEqual([...commands.keys()], ['project-flow-explainer'])
})

test('mounts without a command service (headless composition)', () => {
  const { tools, commands } = mount({}, { withCommands: false })
  assert.equal(tools.size, 7, 'tools must still register when no command adapter exists')
  assert.equal(commands.size, 0)
})

test('the command declares a name the registry accepts and an input hint', () => {
  const command = mount().commands.get('project-flow-explainer')
  // @deepseek-ai/dsh-commands: /^[a-z][a-z0-9_-]*$/
  assert.match(command.name, /^[a-z][a-z0-9_-]*$/)
  assert.ok(command.description.length > 0)
  assert.ok(command.input.hint.includes('<mô tả luồng>'))
})

test('a real request returns success with the artifact paths', async (t) => {
  const repo = tempRepo(t)
  const command = mount({ allowedRoots: [CORPUS, os.tmpdir()] }, { cwd: repo })
    .commands.get('project-flow-explainer')
  const result = await command.handler({
    agent: {}, rawInput: 'xuất báo cáo', signal: AbortSignal.timeout(120_000),
  })
  assert.equal(result.kind, 'success', result.text)
  assert.match(result.text, /flow\.html/)
  assert.match(result.text, /artifacts\/flows\//, 'result must name repository-relative artifacts')
  assert.doesNotMatch(result.text, new RegExp(repo.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')),
    'the command must not echo the absolute repository path')
})

test('an empty request is an error with the usage line', async () => {
  const command = mount().commands.get('project-flow-explainer')
  const result = await command.handler({ agent: {}, rawInput: '   ', signal: undefined })
  assert.equal(result.kind, 'error')
  assert.match(result.text, /Thiếu mô tả luồng/)
  assert.match(result.text, /Cách dùng/)
})

test('a repository outside allowedRoots is refused with its stable code', async () => {
  const command = mount().commands.get('project-flow-explainer')
  const result = await command.handler({
    agent: {}, rawInput: 'x --repo /etc', signal: undefined,
  })
  assert.equal(result.kind, 'error')
  assert.match(result.text, /repository_outside_allowed_roots|repository_not_found/)
})

test('an unconfigured allowedRoots is refused, not silently widened', async () => {
  const { commands } = mount({ allowedRoots: undefined })
  const command = commands.get('project-flow-explainer')
  const result = await command.handler({ agent: {}, rawInput: 'xuất báo cáo', signal: undefined })
  assert.equal(result.kind, 'error')
  assert.match(result.text, /allowed_roots_unconfigured/)
})

test('--repo targets an explicit repository', async (t) => {
  const repo = tempRepo(t)
  const command = mount({ allowedRoots: [CORPUS, os.tmpdir()] }).commands.get('project-flow-explainer')
  const result = await command.handler({
    agent: {}, rawInput: `xuất báo cáo --repo ${repo}`, signal: AbortSignal.timeout(120_000),
  })
  assert.equal(result.kind, 'success', result.text)
})
