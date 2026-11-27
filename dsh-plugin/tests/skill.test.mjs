/**
 * The plugin registers a DSH skill and ships the same text for filesystem discovery.
 *
 * Run: node --test dsh-plugin/tests/skill.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import * as plugin from '../index.js'
import { SKILL_DESCRIPTION, SKILL_NAME, skillMarkdown, skillRegistration } from '../lib/skill.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(HERE, '../..')

function mount() {
  const registered = []
  const ctx = {
    tools: { register() { return () => {} } },
    effect(body) { body(); return { dispose: async () => {} } },
    on() { return () => {} },
    get() { return undefined },
    inject(services, callback) {
      if (!services.includes('skills')) return
      callback({
        skills: { register(skill) { registered.push(skill); return () => {} } },
      })
    },
  }
  plugin.apply(ctx, {})
  return registered
}

test('apply registers one runtime skill when the host has ctx.skills', () => {
  const registered = mount()
  assert.equal(registered.length, 1)
  const skill = registered[0]
  assert.equal(skill.name, SKILL_NAME)
  assert.equal(skill.source, 'runtime')
  assert.equal(skill.invocation.modelInvocable, true)
  assert.equal(skill.invocation.userInvocable, true)
  assert.ok(skill.description.length <= 500)
  assert.match(skill.content, /project_flow_explain/)
  assert.match(skill.content, /project_context_pack/)
  assert.deepEqual(skill, skillRegistration())
})

test('the workspace skill file matches the registered instructions', () => {
  const file = path.join(REPO, '.dsh', 'skills', SKILL_NAME, 'SKILL.md')
  assert.equal(readFileSync(file, 'utf8'), skillMarkdown())
  assert.ok(SKILL_DESCRIPTION.length <= 500)
})

test('a host without a skills service still mounts the tools', () => {
  const tools = new Map()
  const ctx = {
    tools: { register(definition) { tools.set(definition.name, definition); return () => {} } },
    effect(body) { body(); return { dispose: async () => {} } },
    on() { return () => {} },
    get() { return undefined },
  }
  plugin.apply(ctx, {})
  assert.equal(tools.size, 7)
})
