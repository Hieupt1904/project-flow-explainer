/**
 * Live settings binding: the settings row is keyed by the profile **entry id**,
 * which is not always the plugin name. A bundle row uses
 * `project-flow-explainer`; a hand-mounted row may use the package name
 * `dsh-project-flow-explainer`. Both must bind, and a row that appears only
 * after mount must still be picked up.
 *
 * Run: node --test dsh-plugin/tests/settings.test.mjs
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

function makeContext({ rows, getService } = {}) {
  const tools = new Map()
  const listeners = new Map()
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
    settings: {
      describe: () => rows ?? [],
    },
    on(event, handler) {
      listeners.set(event, handler)
      return () => listeners.delete(event)
    },
    get(name) {
      return getService?.(name)
    },
  }
  return { ctx, tools, emit: (event, ...args) => listeners.get(event)?.(...args) }
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

async function firstErrorCode(tools, repo) {
  const search = tools.get('project_code_search')
  try {
    await search.execute({ repository_path: repo, query: 'export_report' }, { signal: undefined })
    return 'ok'
  } catch (error) {
    return error.code ?? error.message
  }
}

test('strict mode with no row and no session root denies the call', async (t) => {
  const { ctx, tools } = makeContext({ rows: [] })
  plugin.apply(ctx, { includeSessionRoot: false })
  assert.equal(await firstErrorCode(tools, tempRepo(t)), 'allowed_roots_unconfigured')
})

test('a session directory is usable with no settings row at all', async (t) => {
  const repo = tempRepo(t)
  const workingDirectory = { async ensure() { return repo } }
  const { ctx, tools } = makeContext({ rows: [], getService: (n) => (n === 'workingDirectory' ? workingDirectory : undefined) })
  plugin.apply(ctx, {})
  const search = tools.get('project_code_search')
  let code = 'ok'
  try {
    await search.execute({ repository_path: repo, query: 'export_report' },
      { signal: undefined, agent: { cwd: repo } })
  } catch (error) {
    code = error.code ?? error.message
  }
  // Not a policy rejection any more: the only remaining failure would be a
  // missing index, which is the honest answer for a fresh copy.
  assert.notEqual(code, 'allowed_roots_unconfigured')
  assert.notEqual(code, 'repository_outside_allowed_roots')
})

test('a row keyed by the package name binds live settings', async (t) => {
  const rows = [{ ns: 'dsh-project-flow-explainer', value: { allowedRoots: [CORPUS] } }]
  const { ctx, tools } = makeContext({ rows })
  plugin.apply(ctx, { includeSessionRoot: false })
  // Not `allowed_roots_unconfigured` any more: the roots came from the row.
  assert.notEqual(await firstErrorCode(tools, tempRepo(t)), 'allowed_roots_unconfigured')
})

test('a row keyed by the entry id binds live settings', async (t) => {
  const rows = [{ ns: 'project-flow-explainer', value: { allowedRoots: [CORPUS] } }]
  const { ctx, tools } = makeContext({ rows })
  plugin.apply(ctx, { includeSessionRoot: false })
  assert.notEqual(await firstErrorCode(tools, tempRepo(t)), 'allowed_roots_unconfigured')
})

test('a row published after mount is adopted on the settings event', async (t) => {
  const rows = []
  const { ctx, tools, emit } = makeContext({ rows })
  plugin.apply(ctx, { includeSessionRoot: false })
  assert.equal(await firstErrorCode(tools, tempRepo(t)), 'allowed_roots_unconfigured')

  rows.push({ ns: 'dsh-project-flow-explainer', value: { allowedRoots: [CORPUS] } })
  emit('settings/document-updated', 'dsh-project-flow-explainer', 1)

  assert.notEqual(await firstErrorCode(tools, tempRepo(t)), 'allowed_roots_unconfigured')
})

test('an unrelated settings row is ignored', async (t) => {
  const rows = [{ ns: 'some-other-plugin', value: { allowedRoots: [CORPUS] } }]
  const { ctx, tools } = makeContext({ rows })
  plugin.apply(ctx, { includeSessionRoot: false })
  assert.equal(await firstErrorCode(tools, tempRepo(t)), 'allowed_roots_unconfigured')
})