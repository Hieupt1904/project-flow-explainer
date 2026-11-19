/**
 * Temporary DSH smoke probe.
 *
 * It runs inside a real booted profile: it reads the real Tool registry
 * (ctx.tools.definitions/get) and calls each installed definition. This proves
 * registry-runtime wiring, NOT model-driven selection (that needs an API key).
 *
 * Result is written to PFE_PROBE_OUT and the process exits, so the headless app
 * never needs a model call.
 */
import { writeFileSync } from 'node:fs'

export const name = 'pfe-smoke-probe'
export const inject = ['tools']

const OUT = process.env.PFE_PROBE_OUT || '/tmp/pfe-smoke/probe.json'
const MODE = process.env.PFE_PROBE_MODE || 'full'
const STEPS = (process.env.PFE_PROBE_STEPS || 'flow,context').split(',').map((s) => s.trim()).filter(Boolean)
const REPO = process.env.PFE_PROBE_REPO || '/tmp/pfe-smoke/repo'
const REQUEST = 'Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file'
const WAIT_MS = Number(process.env.PFE_PROBE_WAIT_MS || 4000)

function write(payload) {
  try {
    writeFileSync(OUT, JSON.stringify(payload, null, 2) + '\n', 'utf8')
  } catch (error) {
    process.stderr.write('probe write failed: ' + String(error) + '\n')
  }
}

async function call(definition, args, signal) {
  const controller = new AbortController()
  const useSignal = signal || controller.signal
  try {
    const value = await definition.execute(args, { signal: useSignal })
    return { ok: true, value }
  } catch (error) {
    return { ok: false, name: error?.name, code: error?.code, message: String(error?.message || error) }
  }
}

export function apply(ctx) {
  const record = {
    mode: MODE,
    started_at: new Date().toISOString(),
    profile: process.env.DSH_PROFILE || '',
    expected_tools: [
      'project_flow_explain', 'project_code_index', 'project_code_search',
      'project_context_pack', 'project_impact_analysis', 'project_verify_flow',
      'project_knowledge_refresh',
    ],
    calls: {},
  }
  const finish = () => { write(record); process.exit(0) }
  const deadline = Date.now() + WAIT_MS

  const run = async () => {
    const names = (ctx.tools.definitions?.() || []).map((item) => item.name).sort()
    record.registered_tools = names
    record.missing_tools = record.expected_tools.filter((tool) => !names.includes(tool))
    // The standard settings page comes from the Host's settings service: a
    // loader entry with a real Config is described there and the UI may
    // generate a page. Reading the descriptor is the evidence, not writing.
    try {
      const settings = ctx.get?.('settings')
      if (settings && typeof settings.describe === 'function') {
        const descriptors = settings.describe({ redactSecrets: true }) || []
        const mine = descriptors.find((item) => String(item.ns).includes('project-flow-explainer'))
        record.settings = mine === undefined ? {
          present: false,
          count: descriptors.length,
          available: descriptors.slice(0, 12).map((item) => String(item.ns)),
        } : {
          present: true,
          ns: String(mine.ns),
          auto_generate: mine.autoGenerate !== false,
          has_schema: mine.schema !== undefined && mine.schema !== null,
          value_keys: Object.keys(mine.value || {}).sort(),
          revision: mine.revision,
          applies: mine.applies,
          namespaces: descriptors.length,
        }
      } else {
        record.settings = { present: false, reason: 'settings service unavailable' }
      }
    } catch (error) {
      record.settings = { present: false, reason: String(error?.message || error) }
    }
    write(record)
    const get = (tool) => ctx.tools.get(tool)
    const tool = get('project_flow_explain')
    if (tool === undefined) {
      record.error = 'project_flow_explain is not in the registry'
      return finish()
    }
    if (MODE === 'empty-roots') {
      record.calls.indexWithEmptyRoots = await call(get('project_code_index'),
        { repository_path: REPO, mode: 'full' })
      return finish()
    }
    if (MODE === 'timeout') {
      record.calls.indexWithTinyTimeout = await call(get('project_code_index'),
        { repository_path: REPO, mode: 'full' })
      return finish()
    }

    // The profile shuts down as soon as the missing-credential check fails, so
    // the probe must be fast and must persist after every call: the index is
    // built by the CLI before boot, calls run in small batches, and each result
    // is flushed immediately.
    const catalogue = {
      flow: [tool, { repository_path: REPO, flow_request: REQUEST }],
      context: [get('project_context_pack'),
        { repository_path: REPO, task: 'xuất báo cáo ra excel', max_files: 6 }],
      impact: [get('project_impact_analysis'),
        { repository_path: REPO, changed_files: ['services/report_service.js'] }],
      verify: [get('project_verify_flow'), { repository_path: REPO }],
      search: [get('project_code_search'),
        { repository_path: REPO, query: 'export_report', top_k: 3 }],
      outsideRoots: [tool, { repository_path: '/tmp', flow_request: 'x' }],
      malformed: [tool, { repository_path: REPO }],
    }
    const steps = STEPS.filter((label) => label !== 'aborted')
      .map((label) => [label, ...(catalogue[label] || [undefined, {}])])
    for (const [label, definition, args] of steps) {
      if (definition === undefined) {
        record.calls[label] = { ok: false, code: 'tool_missing' }
        write(record)
        continue
      }
      record.calls[label] = await call(definition, args)
      write(record)
    }
    if (STEPS.includes('aborted')) {
      const aborted = new AbortController()
      aborted.abort()
      record.calls.aborted = await call(tool,
        { repository_path: REPO, flow_request: 'x' }, aborted.signal)
      write(record)
    }
    finish()
  }

  const tick = async () => {
    try {
      if ((ctx.tools.definitions?.() || []).some((item) => item.name === 'project_flow_explain')) {
        return await run()
      }
      if (Date.now() > deadline) {
        // A disabled row means the tool never appears: report that as evidence
        // instead of waiting for the app to shut the context down.
        record.registry_waited_ms = WAIT_MS
        record.registry_timeout = true
        return finish()
      }
      setTimeout(tick, 200)
    } catch (error) {
      record.error = String(error?.stack || error)
      finish()
    }
  }
  setTimeout(tick, 0)
}