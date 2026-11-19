import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PACKAGE_ROOT = path.resolve(HERE, '..')
const clientSource = readFileSync(path.join(PACKAGE_ROOT, 'client.js'), 'utf8')
const manifest = JSON.parse(readFileSync(path.join(PACKAGE_ROOT, 'package.json'), 'utf8'))

/** Minimal React stand-in: enough for the settings card, no rendering engine. */
function reactStub() {
  return {
    createElement: (type, props, ...children) => ({ type, props: props ?? {}, children }),
    useState: (initial) => [initial, () => {}],
    useEffect: () => {},
  }
}

function loadClient() {
  let captured
  const registrations = []
  const sandbox = {
    window: { __ModuleLoader__: { load: (definition) => { captured = definition } } },
    require: (id) => {
      if (id === 'react') return reactStub()
      throw new Error('unexpected require: ' + id)
    },
    console,
  }
  vm.createContext(sandbox)
  vm.runInContext(clientSource, sandbox, { filename: 'client.js' })
  assert.ok(captured, 'client.js must call window.__ModuleLoader__.load')
  const exports = captured.factory(sandbox.require)
  const ctx = {
    slots: {
      inject: (name, register) => { registrations.push([name, register]) },
      register: (options, component) => { registrations.push(['register', options, component]) },
    },
  }
  return { captured, exports, ctx, registrations }
}

/** Arrays created inside the vm realm do not compare reference-equal. */
function plain(value) {
  return JSON.parse(JSON.stringify(value))
}

function flatten(node, out = []) {
  if (node === null || node === undefined) return out
  if (Array.isArray(node)) { for (const item of node) flatten(item, out); return out }
  if (typeof node !== 'object') return out
  out.push(node)
  for (const child of node.children ?? []) flatten(child, out)
  return out
}

const FORM = {
  state: {
    status: 'ready',
    writable: true,
    revision: 3,
    value: { allowedRoots: ['srv/a', 'srv/b'], pythonPath: 'python3', timeoutMs: 180000 },
  },
  mutate: async (ops) => { FORM.calls.push(ops); return true },
  calls: [],
}

test('client bundle declares the manifest identity', () => {
  const { captured, exports } = loadClient()
  assert.equal(captured.id, manifest.name)
  assert.deepEqual(plain(exports.inject), ['slots'])
  assert.equal(typeof exports.apply, 'function')
})

test('apply registers one keyed settings entry for this bundle', () => {
  const { exports, ctx, registrations } = loadClient()
  exports.apply(ctx)
  assert.equal(registrations.length, 1)
  assert.equal(registrations[0][0], 'plugins.bundle.config')
  registrations[0][1]()
  const [, options, component] = registrations[1]
  assert.equal(options.name, 'plugins.bundle.config')
  assert.equal(options.key, manifest.name)
  assert.equal(typeof component, 'function')
})

test('page view renders one control per config field', () => {
  const { exports, ctx, registrations } = loadClient()
  exports.apply(ctx)
  registrations[0][1]()
  const component = registrations[1][2]
  const tree = component({ view: 'page', form: FORM })
  const elements = flatten(tree)
  const ids = elements.map((node) => node.props?.id).filter(Boolean)
  for (const key of ['allowedRoots', 'pythonPath', 'coreRoot', 'timeoutMs', 'maxOutputBytes']) {
    assert.ok(ids.includes('pfe-' + key), 'missing control for ' + key)
  }
  const roots = elements.find((node) => node.props?.id === 'pfe-allowedRoots')
  assert.equal(roots.type, 'textarea')
  assert.equal(roots.props.value, 'srv/a\nsrv/b')
})

test('save sends every field as one mutate batch', async () => {
  FORM.calls.length = 0
  const { exports, ctx, registrations } = loadClient()
  exports.apply(ctx)
  registrations[0][1]()
  const component = registrations[1][2]
  const tree = component({ view: 'page', form: FORM })
  const button = flatten(tree).find((node) => node.type === 'button')
  assert.ok(button, 'missing save button')
  await button.props.onClick()
  assert.equal(FORM.calls.length, 1)
  const ops = FORM.calls[0]
  const roots = ops.find((op) => op.path[0] === 'allowedRoots')
  assert.deepEqual(plain(roots.value), ['srv/a', 'srv/b'])
  const timeout = ops.find((op) => op.path[0] === 'timeoutMs')
  assert.equal(timeout.value, 180000)
  const core = ops.find((op) => op.path[0] === 'coreRoot')
  assert.equal(core.op, 'unset', 'an empty text field must clear the value')
})

test('summary view explains an empty root list instead of pretending it is configured', () => {
  const { exports, ctx, registrations } = loadClient()
  exports.apply(ctx)
  registrations[0][1]()
  const component = registrations[1][2]
  const tree = component({
    view: 'summary',
    form: { state: { value: { allowedRoots: [] }, writable: true }, mutate: async () => true },
  })
  const flat = flatten(tree).map((node) => node.children).flat().filter(Boolean).join(' ')
  assert.match(flat, /Chưa cấu hình/)
})

test('a missing host form is reported, not silently rendered', () => {
  const { exports, ctx, registrations } = loadClient()
  exports.apply(ctx)
  registrations[0][1]()
  const component = registrations[1][2]
  const tree = component({ view: 'page', form: undefined })
  const text = flatten(tree).map((node) => node.children).flat().filter((item) => typeof item === 'string').join(' ')
  assert.match(text, /chưa cung cấp form cấu hình/i)
})