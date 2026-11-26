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
import { parseInput } from '../lib/command.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const CORPUS = path.resolve(HERE, '../..')
const FIXTURE = path.resolve(CORPUS, 'tests/fixtures/shop-app')

function mount(applied = {}, { withCommands = true, cwd = CORPUS, strictScope = false } = {}) {
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
      // A real Cordis scoped context inherits every other service from its
      // parent, but *reading* an undeclared service throws from the proxy:
      // `cannot get property "workingDirectory" without inject`. With
      // strictScope the mock reproduces that, which is the only shape that
      // catches a command that reads the service it never declared. `get()`
      // bypasses the inject requirement, exactly as Cordis does.
      const scope = {
        get: (name) => (name === 'workingDirectory' ? ctx.workingDirectory : ctx.get(name)),
        commands: {
          register(definition) {
            commands.set(definition.name, definition)
            return () => commands.delete(definition.name)
          },
        },
      }
      if (strictScope) {
        Object.defineProperty(scope, 'workingDirectory', {
          get() { throw new Error('cannot get property "workingDirectory" without inject') },
        })
      } else {
        scope.workingDirectory = ctx.workingDirectory
      }
      cb(scope)
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

test('map mode checks the same allowedRoots as a flow run', async () => {
  const { commands } = mount({ allowedRoots: undefined })
  const result = await commands.get('project-flow-explainer').handler({rawInput:'--map'})
  assert.equal(result.kind,'error')
  assert.match(result.text,/allowed_roots_unconfigured/)
})

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

test('a repository outside allowedRoots is refused with its stable code and a fix', async () => {
  const command = mount().commands.get('project-flow-explainer')
  const result = await command.handler({
    agent: {}, rawInput: 'x --repo /etc', signal: undefined,
  })
  assert.equal(result.kind, 'error')
  assert.match(result.text, /repository_outside_allowed_roots|repository_not_found/)
  // The person typing a command wants the run, not a policy lesson: name the flag.
  assert.match(result.text, /Cách sửa:.*--repo/)
})

test('a fresh install runs the command in the session directory', async (t) => {
  // The shipped default has no allowedRoots at all: the session's own directory
  // is the read scope DSH already granted, so the first run must work without a
  // configuration round trip.
  const repo = tempRepo(t)
  const { commands } = mount({ allowedRoots: undefined }, { cwd: repo })
  const result = await commands.get('project-flow-explainer').handler({
    agent: {}, rawInput: 'xuất báo cáo', signal: AbortSignal.timeout(120_000),
  })
  assert.equal(result.kind, 'success', result.text)
  assert.match(result.text, /flow\.html/)
})

test('strict mode refuses a session directory that is not listed', async () => {
  const { commands } = mount(
    { allowedRoots: [CORPUS], includeSessionRoot: false },
    { cwd: os.homedir() },
  )
  const result = await commands.get('project-flow-explainer')
    .handler({ agent: {}, rawInput: 'xuất báo cáo', signal: undefined })
  assert.equal(result.kind, 'error')
  assert.match(result.text, /Cách sửa:.*--repo/)
})

test('a scoped command context still reads the session directory', async (t) => {
  // Regression: the command is registered inside ctx.inject(['commands'], ...),
  // so its context declares only `commands`. A direct read of
  // `ctx.workingDirectory` there throws, and swallowing that throw fell back to
  // process.cwd() — the DSH launcher directory — so the command refused the very
  // repository the session was opened in.
  const repo = tempRepo(t)
  const { commands } = mount(
    { allowedRoots: [CORPUS, os.tmpdir()] },
    { cwd: repo, strictScope: true },
  )
  const result = await commands.get('project-flow-explainer').handler({
    agent: {}, rawInput: 'xuất báo cáo', signal: AbortSignal.timeout(120_000),
  })
  assert.equal(result.kind, 'success', result.text)
  assert.match(result.text, /flow\.html/)
})

test('strict mode with no roots is refused, never silently widened', async () => {
  const { commands } = mount({ allowedRoots: undefined, includeSessionRoot: false })
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

test('--repo accepts a quoted path with spaces', async (t) => {
  const base = mkdtempSync(path.join(os.tmpdir(), 'pfe-space-'))
  const repo = path.join(base, 'repo with spaces')
  cpSync(FIXTURE, repo, { recursive: true })
  t.after(() => rmSync(base, { recursive: true, force: true }))
  const command = mount({ allowedRoots: [CORPUS, os.tmpdir()] }).commands
    .get('project-flow-explainer')
  for (const raw of [`xuất báo cáo --repo "${repo}"`, `xuất báo cáo --repo='${repo}'`]) {
    const result = await command.handler({
      agent: {}, rawInput: raw, signal: AbortSignal.timeout(120_000),
    })
    assert.equal(result.kind, 'success', `${raw} -> ${result.text}`)
  }
})

test('a quoted path is not truncated at the first space', () => {
  // Built, not written: the repository policy rejects absolute workstation
  // paths in source, and a literal here would also pin the test to /tmp.
  const dir = mkdtempSync(path.join(os.tmpdir(), 'pfe-quote-'))
  const target = path.join(dir, 'repo with spaces')
  const parsed = parseInput(`xuất báo cáo --repo "${target}"`)
  assert.equal(parsed.repository, target)
  assert.equal(parsed.request, 'xuất báo cáo')
  rmSync(dir, { recursive: true, force: true })
})

test('--repo=value form is parsed too', () => {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'pfe-eq-'))
  const target = path.join(dir, 'a b')
  const parsed = parseInput(`xuất báo cáo --repo='${target}'`)
  assert.equal(parsed.repository, target)
  rmSync(dir, { recursive: true, force: true })
})