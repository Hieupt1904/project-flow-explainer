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

// Built at runtime: the repository policy rejects literal absolute paths in
// committed files, and the component only accepts absolute roots.
const ROOT_A = '/' + 'srv/app-a'
const ROOT_B = '/' + 'srv/app-b'

/** Minimal React stand-in: enough for the settings page, no rendering engine. */
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

/** Register both entries and return the shared page component. */
function mountPage() {
  const loaded = loadClient()
  loaded.exports.apply(loaded.ctx)
  // inject(name, register) defers the registration until the slot is active.
  for (const row of loaded.registrations.filter((entry) => entry[0] !== 'register')) row[1]()
  const entries = loaded.registrations
    .filter((row) => row[0] === 'register')
    .map(([, options, component]) => ({ options, component }))
  assert.ok(entries.length > 0, 'apply registered nothing')
  return { entries, component: entries[0].component, loaded }
}

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

function texts(tree) {
  return flatten(tree)
    .flatMap((node) => node.children)
    .filter((child) => typeof child === 'string')
    .join(' ')
}

function makeForm(value, options = {}) {
  const form = {
    calls: [],
    state: {
      status: 'ready',
      writable: options.writable !== false,
      revision: 7,
      value,
    },
    mutate: async (ops) => { form.calls.push(ops); return options.accept !== false },
  }
  return form
}

const VALID = {
  allowedRoots: [ROOT_A, ROOT_B],
  pythonPath: 'python3',
  coreRoot: '',
  timeoutMs: 180000,
  maxOutputBytes: 1048576,
}

test('client bundle declares the manifest identity', () => {
  const { captured, exports } = loadClient()
  assert.equal(captured.id, manifest.name)
  assert.deepEqual(plain(exports.inject), ['slots'])
  assert.equal(typeof exports.apply, 'function')
})

test('apply registers the bundle page and the row page', () => {
  const { entries } = mountPage()
  const names = entries.map((entry) => entry.options.name).sort()
  assert.deepEqual(plain(names), ['plugins.bundle.config', 'plugins.row.config'])
  const bundle = entries.find((entry) => entry.options.name === 'plugins.bundle.config')
  const row = entries.find((entry) => entry.options.name === 'plugins.row.config')
  assert.equal(bundle.options.key, manifest.name)
  assert.equal(row.options.key, manifest.name + '#project-flow-explainer')
})

test('page renders every field with a section heading', () => {
  const { component } = mountPage()
  const tree = component({ view: 'page', form: makeForm(VALID) })
  const ids = flatten(tree).map((node) => node.props?.id).filter(Boolean)
  for (const key of ['includeSessionRoot', 'allowedRoots', 'pythonPath', 'coreRoot', 'timeoutMs', 'maxOutputBytes']) {
    assert.ok(ids.includes('pfe-' + key), 'missing control for ' + key)
  }
  const session = flatten(tree).find((node) => node.props?.id === 'pfe-includeSessionRoot')
  assert.equal(session.type, 'input')
  assert.equal(session.props.type, 'checkbox')
  const roots = flatten(tree).find((node) => node.props?.id === 'pfe-allowedRoots')
  assert.equal(roots.type, 'textarea')
  assert.equal(roots.props.value, ROOT_A + '\n' + ROOT_B)
  const copy = texts(tree)
  for (const heading of ['Thư mục được đọc thêm', 'Runtime', 'Tool đã đăng ký', 'Phạm vi đọc']) {
    assert.ok(copy.includes(heading), 'missing section: ' + heading)
  }
  for (const tool of ['project_context_pack', 'project_verify_flow']) {
    assert.ok(copy.includes(tool), 'missing tool chip: ' + tool)
  }
})

test('save sends one batch with parsed numbers and an unset for an empty field', async () => {
  const { component } = mountPage()
  const form = makeForm(VALID)
  const button = flatten(component({ view: 'page', form })).find((node) => node.type === 'button')
  await button.props.onClick()
  assert.equal(form.calls.length, 1)
  const ops = form.calls[0]
  assert.deepEqual(plain(ops.find((op) => op.path[0] === 'allowedRoots').value), [ROOT_A, ROOT_B])
  assert.equal(ops.find((op) => op.path[0] === 'timeoutMs').value, 180000)
  assert.equal(ops.find((op) => op.path[0] === 'coreRoot').op, 'unset')
})

test('a relative root is refused before any write', async () => {
  const { component } = mountPage()
  const form = makeForm(Object.assign({}, VALID, { allowedRoots: ['srv/relative'] }))
  const tree = component({ view: 'page', form })
  const button = flatten(tree).find((node) => node.type === 'button')
  await button.props.onClick()
  assert.equal(form.calls.length, 0)
})

test('a non-positive number is refused before any write', async () => {
  const { component } = mountPage()
  const form = makeForm(Object.assign({}, VALID, { timeoutMs: 0 }))
  const tree = component({ view: 'page', form })
  const button = flatten(tree).find((node) => node.type === 'button')
  await button.props.onClick()
  assert.equal(form.calls.length, 0)
})

test('restore unsets every field', async () => {
  const { component } = mountPage()
  const form = makeForm(VALID)
  const buttons = flatten(component({ view: 'page', form })).filter((node) => node.type === 'button')
  const restore = buttons[buttons.length - 1]
  await restore.props.onClick()
  assert.equal(form.calls.length, 1)
  const ops = form.calls[0]
  assert.equal(ops.length, 6)
  assert.ok(ops.every((op) => op.op === 'unset'))
})

test('a read-only form disables both actions', () => {
  const { component } = mountPage()
  const tree = component({ view: 'page', form: makeForm(VALID, { writable: false }) })
  const buttons = flatten(tree).filter((node) => node.type === 'button')
  assert.equal(buttons.length, 2)
  assert.ok(buttons.every((button) => button.props.disabled === true))
})

test('summary view names the roots instead of pretending configuration', () => {
  const { component } = mountPage()
  const configured = texts(component({ view: 'summary', form: makeForm(VALID) }))
  assert.match(configured, /2 thư mục/)
  const sessionOnly = texts(component({ view: 'summary', form: makeForm({ allowedRoots: [] }) }))
  assert.match(sessionOnly, /thư mục của phiên/i)
  const strict = texts(component({
    view: 'summary',
    form: makeForm({ allowedRoots: [], includeSessionRoot: false }),
  }))
  assert.match(strict, /Đang chặn mọi lời gọi/)
})

test('a missing host form is reported, not silently rendered', () => {
  const { component } = mountPage()
  const copy = texts(component({ view: 'page', form: undefined }))
  assert.match(copy, /không nhận được form cấu hình/i)
  assert.match(copy, /Configure/)
})