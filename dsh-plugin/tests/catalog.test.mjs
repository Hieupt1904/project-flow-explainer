/**
 * Headless model catalog and the temporary `--patch` overlay.
 *
 * Run: node --test dsh-plugin/tests/catalog.test.mjs
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { createDshOverlay, loadYaml, projectCatalog } from '../../vendor/project-flow-explainer/assets/dsh-models.mjs'

test('projectCatalog keeps provider routes and drops credential material', () => {
  const catalog = projectCatalog([
    { id: 'agent-default-model', config: { provider: 'test-route', model: 'shared/model' } },
    { id: 'llm-pi-ai', config: { providers: {
      'test-route': {
        baseURL: 'https://example.invalid/v1',
        apiKeyEnv: 'FIXTURE_REF',
        headers: { Authorization: 'PRIVATE_HEADER' },
        models: [{ id: 'shared/model', name: 'Mô hình chung' }],
      },
    } } },
    { id: 'credentials', disabled: true },
  ])
  assert.equal(catalog.models.length, 1)
  assert.equal(catalog.models[0].provider, 'test-route')
  assert.equal(catalog.defaultId, JSON.stringify(['test-route', 'shared/model']))
  const stored = [...catalog.routes.values()][0].config
  assert.equal(stored.apiKeyEnv, 'FIXTURE_REF')
  assert.equal(stored.headers, undefined)
})

test('the model overlay is a YAML patch the launcher can parse as JSON', () => {
  const overlay = createDshOverlay({
    provider: 'other-route',
    model: 'shared/model',
    adapter: 'llm-pi-ai',
    config: { baseURL: 'https://example.invalid/v1', apiKeyEnv: 'FIXTURE_REF', models: [{ id: 'shared/model' }] },
  })
  try {
    assert.match(overlay.file, /selection\.yml$/)
    const rows = JSON.parse(readFileSync(overlay.file, 'utf8'))
    const choice = rows.find((row) => row.id === 'agent-default-model').config
    assert.equal(choice.provider, 'other-route')
    assert.equal(choice.model, 'shared/model')
    assert.equal(rows.some((row) => row.id === 'credentials' && row.disabled === false), true)
  } finally {
    overlay.dispose()
  }
})

test('loadYaml finds the package above a shim', () => {
  const root = mkdtempSync(path.join(os.tmpdir(), 'pfe-yaml-'))
  try {
    const shim = path.join(root, 'bin', 'dsh')
    const yamlDir = path.join(root, 'node_modules', 'yaml')
    mkdirSync(path.dirname(shim), { recursive: true })
    mkdirSync(yamlDir, { recursive: true })
    writeFileSync(shim, '#!/usr/bin/env node\n', 'utf8')
    writeFileSync(path.join(yamlDir, 'package.json'), JSON.stringify({ name: 'yaml', main: 'index.js' }))
    writeFileSync(path.join(yamlDir, 'index.js'), 'module.exports = { parseDocument() { return { errors: [], toJS() { return [] } } } }\n')
    const yaml = loadYaml(shim)
    assert.equal(typeof yaml.parseDocument, 'function')
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})
