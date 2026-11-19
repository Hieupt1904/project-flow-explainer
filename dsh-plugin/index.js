/**
 * DSH adapter for Project Flow Explainer.
 *
 * The core (Python, no third-party packages) stays independent: this plugin
 * only validates arguments, contains paths, calls the core CLI and maps the
 * result. It imports nothing from @deepseek-ai/* on purpose — a profile's
 * node_modules cannot resolve those packages, so the definition is hand-built
 * and handed to `ctx.tools.register`, which manages its lifecycle.
 *
 * Security posture (see README):
 *   - deny-by-default: without `allowedRoots` every call fails with
 *     `allowed_roots_unconfigured`;
 *   - artifacts may only be written to `<repo>/artifacts/flows`;
 *   - cancellation surfaces as AbortError so the runtime keeps the
 *     cancellation identity instead of recording a business failure.
 *
 * Besides `project_flow_explain`, this plugin registers the code-knowledge
 * tools from ./lib/tools.js (index, search, context pack, impact, verify,
 * refresh). They share the same path policy and the same core subprocess.
 */
import path from 'node:path'
import { createRequire } from 'node:module'
import { realpathSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { runCore } from './lib/core-runner.js'
import {
  InputError, resolveArtifactRoot, resolveCoreRoot, resolveRepository,
} from './lib/paths.js'
import { knowledgeTools } from './lib/tools.js'
import {
  assertObject, optionalString, requiredString,
} from './lib/validate.js'

export const name = 'project-flow-explainer'
export const inject = ['tools']

// The schema must come from the SAME schemastery instance the Loader uses.
// Node resolution from this package reaches the profile's own copy first, and
// a foreign copy makes the config projector emit {} for every volatile field
// (measured: cfg {"allowedRoots":{},"pythonPath":{},...}), so the Settings page
// drops the entry. Anchor a resolver at $DSH_HOME/profiles instead: the flat
// closure there links to the installation's schemastery, which is the Loader's.
function loadSchemaModule() {
  const candidates = []
  // The Loader runs from the installation; anchoring there resolves the exact
  // schemastery instance it validates with.
  try {
    // <install>/lib/node_modules/@deepseek-ai/dsh/lib/bin.js -> package root,
    // whose node_modules holds the Loader's own schemastery.
    const bin = realpathSync(process.argv[1] ?? '')
    const dshPackage = path.dirname(path.dirname(bin))
    candidates.push(createRequire(path.join(dshPackage, 'anchor.js')))
  } catch {
    // no argv anchor (tests, embedders)
  }
  if (process.env.DSH_HOME) {
    candidates.push(createRequire(path.join(process.env.DSH_HOME, 'profiles', 'anchor.js')))
  }
  candidates.push(createRequire(import.meta.url))
  let fallback
  for (const requireFrom of candidates) {
    try {
      const resolved = requireFrom.resolve('@deepseek-ai/schemastery')
      const loaded = requireFrom(resolved)
      const z = loaded.default ?? loaded
      if (typeof z?.object !== 'function') continue
      // Prefer the installation's copy: that is the instance the Loader uses.
      const candidate = { z, source: resolved }
      if (resolved.includes(path.join('@deepseek-ai', 'dsh', 'node_modules'))) return candidate
      fallback ??= candidate
    } catch {
      // try the next anchor
    }
  }
  return fallback
}

const schemaModule = loadSchemaModule()
let ConfigSchema
if (schemaModule !== undefined) {
  const z = schemaModule.z
  // .volatile() is what puts the entry into settings.describe(): without it the
  // Plugins page has no ConfigPageForm to pass to plugins.bundle.config.
  ConfigSchema = z.object({
    allowedRoots: z.array(z.string()).volatile().description(
      'Thư mục gốc được đọc, đường dẫn tuyệt đối. Rỗng nghĩa là từ chối mọi repository.'),
    pythonPath: z.string().default('python3').volatile()
      .description('Interpreter dùng để gọi core'),
    coreRoot: z.string().volatile().description('Thư mục core; bỏ trống để tự dò vendor/core'),
    timeoutMs: z.number().min(1).default(180000).volatile()
      .description('Ngân sách mỗi lần gọi, mili giây'),
    maxOutputBytes: z.number().min(1).default(1048576).volatile()
      .description('Giới hạn stdout và stderr'),
  })
}

/** Real schemastery schema when it resolved, otherwise undefined (fallback path). */
export const Config = ConfigSchema

export const TOOL_NAME = 'project_flow_explain'
const PACKAGE_ROOT = path.dirname(fileURLToPath(import.meta.url))

const DEFAULTS = {
  pythonPath: 'python3',
  coreRoot: undefined,
  // Deny-by-default: undefined/empty means "no repository is allowed".
  allowedRoots: undefined,
  timeoutMs: 180000,
  maxOutputBytes: 1024 * 1024,
}

function badConfig(message, hint) {
  throw new InputError('invalid_plugin_config', `${name}: ${message}`, hint)
}

function normalizeConfig(config) {
  // Volatile settings are placeholders ({}) until the user layer carries a
  // value, so every field is type-checked and falls back to its default instead
  // of failing the mount. A real wrong type still fails: the Loader's Config
  // schema rejects it before apply().
  const raw = config ?? {}
  const settings = { ...DEFAULTS }
  for (const [key, value] of Object.entries(raw)) {
    // Volatile fields arrive as {} before the settings layer has a value.
    // That placeholder means "unset"; any other wrong shape must still fail.
    const placeholder = typeof value === 'object' && value !== null
      && !Array.isArray(value) && Object.keys(value).length === 0
    if (value === undefined || value === null || placeholder) continue
    settings[key] = value
  }
  if (typeof settings.pythonPath !== 'string' || settings.pythonPath.trim() === '') {
    badConfig('pythonPath phải là chuỗi không rỗng')
  }
  if (settings.coreRoot !== undefined && typeof settings.coreRoot !== 'string') {
    badConfig('coreRoot phải là chuỗi đường dẫn')
  }
  if (settings.allowedRoots !== undefined && !Array.isArray(settings.allowedRoots)) {
    badConfig('allowedRoots phải là mảng chuỗi đường dẫn')
  }
  if (!Number.isFinite(settings.timeoutMs) || settings.timeoutMs <= 0) {
    badConfig('timeoutMs phải là số dương')
  }
  if (!Number.isFinite(settings.maxOutputBytes) || settings.maxOutputBytes <= 0) {
    badConfig('maxOutputBytes phải là số dương')
  }
  return settings
}

/** A cancellation that the runtime recognises as a cancellation, not a failure. */
function abortError(reason) {
  const error = new Error(reason instanceof Error ? reason.message : 'tool call aborted')
  error.name = 'AbortError'
  return error
}

function failure(kind, run) {
  const tail = run.stderr.trim().split('\n').slice(-3).join(' ').slice(0, 500)
  return new InputError(kind, `${kind}: ${tail || 'không có thông tin lỗi'}`,
    'Xem log của core; chạy lại CLI với --json để lấy mã lỗi chi tiết.')
}

function parseCoreResult(result) {
  const line = result.stdout.trim().split('\n').filter(Boolean).pop() ?? ''
  try {
    return JSON.parse(line)
  } catch {
    return null
  }
}

const TEXT = (value) => [{ type: 'text', text: value }]

/**
 * @param {object} ctx - Cordis context with the `tools` service injected.
 * @param {object} [config] - profile patch config (`allowedRoots` required to use the tool).
 */
/**
 * Volatile fields reach apply() as {} placeholders: the Loader keeps their
 * values in the settings document instead of the static config. Read them from
 * the settings service once and refresh on its document event, so every tool
 * call sees the current user layer.
 * @param {object} ctx - Cordis context (settings service optional).
 * @param {object} target - normalized settings object updated in place.
 */
function attachLiveSettings(ctx, target) {
  const read = () => {
    try {
      const rows = ctx.settings?.describe?.({ redactSecrets: true }) ?? []
      const mine = rows.find((row) => String(row.ns) === name)
      // `value` is the resolved form: profile patch + user layer + defaults.
      // `user` alone is just the profile's own patch layer, so using it would
      // ignore the bundle's configured roots.
      if (mine === undefined || mine.value === undefined) return
      const layer = {}
      for (const [key, value] of Object.entries(mine.value)) {
        if (value !== undefined && value !== null) layer[key] = value
      }
      Object.assign(target, normalizeConfig({ ...target, ...layer }))
    } catch {
      // settings unavailable (headless mount, unit test): keep the static config
    }
  }
  read()
  try {
    ctx.on('settings/document-updated', (ns) => {
      if (String(ns).includes(name)) read()
    })
  } catch {
    // no event service in this composition
  }
}

export function apply(ctx, config = {}) {
  const settings = normalizeConfig(config)
  // The settings service is optional: a headless mount or a unit test has none.
  // Declaring the dependency through ctx.inject keeps the mount valid either way.
  try {
    ctx.inject(['settings'], (scoped) => { attachLiveSettings(scoped, settings) })
  } catch {
    attachLiveSettings(ctx, settings)
  }
  const core = resolveCoreRoot({
    coreRoot: settings.coreRoot,
    packageRoot: PACKAGE_ROOT,
  })
  const inFlight = new Set()

  ctx.effect(() => () => {
    for (const controller of inFlight) {
      try {
        controller.abort()
      } catch {
        /* already aborted */
      }
    }
    inFlight.clear()
  }, `${name}: dispose in-flight runs`)

  ctx.tools.register({
    name: TOOL_NAME,
      description: [
        'Dựng sơ đồ quy trình từ một repository và một yêu cầu bằng tiếng Việt.',
        'DÙNG KHI: cần hiểu một luồng nghiệp vụ trước khi sửa, hoặc giải thích cho người không đọc code.',
        'KHÔNG DÙNG KHI: chỉ cần tra một hàm/route (dùng project_code_search).',
        'ĐIỀU KIỆN: repository_path tuyệt đối trong allowedRoots; flow_request mô tả luồng cụ thể.',
        'KẾT QUẢ: flow.html (mở offline, có chế độ Đơn giản), flow.json, overview.md, run.json nội bộ.',
        'TIẾP THEO: project_context_pack để biết file nào cần đọc trước khi sửa.',
        'GIỚI HẠN: phân tích tĩnh, không chạy code; verified = vị trí + quan hệ, không phải runtime.',
      ].join('\n'),
    parameters: {
      type: 'object',
      properties: {
        repository_path: {
          type: 'string',
          description: 'Đường dẫn tuyệt đối tới thư mục repository, phải nằm trong allowedRoots.',
        },
        flow_request: {
          type: 'string',
          description: 'Mô tả flow bằng tiếng Việt thông thường, ví dụ: "từ lúc bấm xuất báo cáo '
            + 'đến khi nhận được file, dữ liệu đi qua những bước nào và lỗi xử lý ở đâu".',
        },
        output_directory: {
          type: 'string',
          description: 'Chỉ chấp nhận "artifacts/flows" (hoặc đường dẫn tuyệt đối tương ứng). '
            + 'Mặc định chính là thư mục đó.',
        },
        slug: {
          type: 'string',
          description: 'Tên thư mục artifact. Bỏ trống để tool tự sinh tên mới, tránh ghi đè.',
        },
      },
      required: ['repository_path', 'flow_request'],
      additionalProperties: false,
    },
    output: {
      schema: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['ok'] },
          flow_id: { type: 'string' },
          slug: { type: 'string' },
          repository: { type: 'string' },
          repository_name: { type: 'string' },
          path_base: { type: 'string' },
          artifacts_dir: { type: 'string' },
          artifacts: {
            type: 'object',
            properties: {
              flow_json: { type: 'string' },
              flow_html: { type: 'string' },
              overview: { type: 'string' },
              run: { type: 'string' },
            },
            required: ['flow_json', 'flow_html', 'overview', 'run'],
            additionalProperties: false,
          },
          path_visibility: {
            type: 'object',
            properties: {
              repository: { type: 'string' },
              artifacts: { type: 'string' },
              source_refs: { type: 'string' },
              absolute_paths_returned: { type: 'boolean' },
            },
            required: ['repository', 'artifacts', 'source_refs', 'absolute_paths_returned'],
            additionalProperties: false,
          },
          output_contract: {
            type: 'object',
            properties: {
              public: { type: 'array', items: { type: 'string' } },
              internal: { type: 'array', items: { type: 'string' } },
            },
            required: ['public', 'internal'],
            additionalProperties: false,
          },
          counts: {
            type: 'object',
            properties: {
              verified: { type: 'integer' },
              partial: { type: 'integer' },
              inferred: { type: 'integer' },
              unknown: { type: 'integer' },
            },
            required: ['verified', 'partial', 'inferred', 'unknown'],
            additionalProperties: false,
          },
          files_scanned: { type: 'integer' },
          related_count: { type: 'integer' },
          source_version: {
            type: 'object',
            properties: {
              commit: { type: 'string' },
              branch: { type: 'string' },
              dirty: { type: 'boolean' },
              dirty_files: { type: 'integer' },
            },
            required: ['commit', 'branch', 'dirty', 'dirty_files'],
            additionalProperties: false,
          },
          warnings: { type: 'array', items: { type: 'string' } },
          limits: { type: 'array', items: { type: 'string' } },
        },
        required: ['status', 'flow_id', 'slug', 'repository', 'repository_name',
          'path_base', 'artifacts_dir', 'artifacts', 'path_visibility', 'output_contract', 'counts',
          'files_scanned', 'related_count', 'source_version', 'warnings', 'limits'],
        additionalProperties: false,
      },
      render(_args, value) {
        const lines = [
          `Sơ đồ: ${value.flow_id} (${value.counts.verified} verified · `
            + `${value.counts.partial} partial · ${value.counts.inferred} inferred)`,
          `Mở: ${value.artifacts.flow_html}`,
          `Dữ liệu: ${value.artifacts.flow_json} · Giải thích: ${value.artifacts.overview}`,
          `Ngoài luồng: ${value.related_count} file chỉ khớp từ khoá`,
        ]
        if (value.warnings.length > 0) lines.push(`Cảnh báo: ${value.warnings[0]}`)
        lines.push('Đường dẫn tính từ repository. Không có nội dung source trong kết quả.')
        lines.push('Tiếp theo: gọi project_context_pack trước khi sửa file trong luồng.')
        return TEXT(lines.join('\n'))
      },
    },
    timeoutMs: settings.timeoutMs,
    // One call writes artifacts: never group it with a parallel batch.
    isConcurrencySafe: () => false,
    async execute(args, exec) {
      // Defence in depth: the runtime validates the JSON schema first, but a
      // direct execute() call must not be able to raise a raw TypeError.
      assertObject(args, TOOL_NAME)
      const repositoryPath = requiredString(args, 'repository_path', TOOL_NAME)
      const request = requiredString(args, 'flow_request', TOOL_NAME)
      const requestedOutput = optionalString(args, 'output_directory', TOOL_NAME)
      const requestedSlug = optionalString(args, 'slug', TOOL_NAME)
      const repository = resolveRepository(repositoryPath, {
        allowedRoots: settings.allowedRoots,
      })
      const outputDirectory = resolveArtifactRoot(
        repository.root, requestedOutput === '' ? undefined : requestedOutput)
      if (exec?.signal?.aborted) throw abortError(exec.signal.reason)

      const controller = new AbortController()
      const forwardAbort = () => controller.abort(exec.signal.reason)
      if (exec?.signal) exec.signal.addEventListener('abort', forwardAbort, { once: true })
      inFlight.add(controller)

      let run
      try {
        run = await runCore({
          pythonPath: settings.pythonPath,
          coreRoot: core.root,
          script: core.script,
          repository: repository.root,
          request,
          outputDirectory,
          slug: requestedSlug && requestedSlug.trim() !== '' ? requestedSlug.trim() : undefined,
          signal: controller.signal,
          timeoutMs: settings.timeoutMs,
          maxOutputBytes: settings.maxOutputBytes,
        })
      } finally {
        inFlight.delete(controller)
        if (exec?.signal) exec.signal.removeEventListener('abort', forwardAbort)
      }

      // Cancellation keeps its own identity: the runtime maps an Error named
      // `AbortError` to code ABORTED, so never dress it as a business failure.
      if (run.aborted) throw abortError(exec?.signal?.reason)
      if (run.timedOut) {
        throw new InputError('core_timeout',
          `Core vượt quá ${settings.timeoutMs} ms và đã bị dừng.`,
          'Tăng config.timeoutMs hoặc phân tích một luồng hẹp hơn.')
      }

      const payload = parseCoreResult(run)
      if (payload === null) {
        throw failure(run.code === null ? 'core_spawn_failed' : 'core_failed', run)
      }
      if (payload.status === 'error') {
        throw new InputError(payload.code, payload.message, payload.hint)
      }
      if (run.code !== 0) throw failure('core_failed', run)

      const source = payload.source ?? {}
      // Canonical output is model-facing, so it carries repository-relative
      // paths only. No DSH presentation boundary has been verified, so an
      // absolute workstation path must not leave this tool.
      const relative = (value) => {
        if (typeof value !== 'string' || value === '') return ''
        const rel = path.relative(repository.root, value)
        return rel.split(path.sep).join('/')
      }
      const artifactsDir = relative(payload.artifacts_dir)
      return {
        status: 'ok',
        flow_id: payload.flow_id,
        slug: payload.slug,
        repository: payload.repository_name ?? path.basename(repository.root),
        repository_name: payload.repository_name ?? path.basename(repository.root),
        path_base: 'repository',
        artifacts_dir: artifactsDir,
        artifacts: {
          flow_json: relative(payload.paths.flow_json),
          flow_html: relative(payload.paths.flow_html),
          overview: relative(payload.paths.overview),
          run: relative(payload.paths.run),
        },
        path_visibility: {
          repository: 'model-facing (name only)',
          artifacts: 'model-facing (repository-relative)',
          source_refs: 'model-facing (repository-relative)',
          absolute_paths_returned: false,
        },
        output_contract: {
          public: payload.contract?.public ?? ['flow.json', 'flow.html', 'overview.md'],
          internal: payload.contract?.internal ?? ['run.json'],
        },
        counts: {
          verified: payload.counts?.verified ?? 0,
          partial: payload.counts?.partial ?? 0,
          inferred: payload.counts?.inferred ?? 0,
          unknown: payload.counts?.unknown ?? 0,
        },
        files_scanned: payload.files_scanned ?? 0,
        related_count: Array.isArray(payload.related) ? payload.related.length : 0,
        source_version: {
          commit: source.commit ?? '',
          branch: source.branch ?? '',
          dirty: Boolean(source.dirty),
          dirty_files: source.dirty_files ?? 0,
        },
        warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
        limits: Array.isArray(payload.limits) ? payload.limits : [],
      }
    },
  })

  // Knowledge layer: same path policy, same core subprocess, separate tools.
  for (const definition of knowledgeTools({ settings, core, inFlight })) {
    ctx.tools.register(definition)
  }
}