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
  const settings = { ...DEFAULTS, ...(config ?? {}) }
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
export function apply(ctx, config = {}) {
  const settings = normalizeConfig(config)
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
    description:
      'Phân tích một repository trên máy và dựng sơ đồ quy trình dạng HTML mở offline, '
      + 'kèm dữ liệu có cấu trúc và bản giải thích. Chỉ đọc source trong allowedRoots, '
      + 'không gọi network, không chạy code của repository, không sửa file nguồn. '
      + 'Artifact chỉ ghi vào <repo>/artifacts/flows/<slug>/. '
      + 'Trả đường dẫn tới flow.json, flow.html, overview.md và số bước theo mức tin cậy.',
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
            },
            required: ['repository', 'artifacts', 'source_refs'],
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
          'artifacts_dir', 'artifacts', 'path_visibility', 'output_contract', 'counts',
          'files_scanned', 'related_count', 'source_version', 'warnings', 'limits'],
        additionalProperties: false,
      },
      render(_args, value) {
        const lines = [
          `Đã dựng sơ đồ: ${value.flow_id}`,
          `Bước: ${value.counts.verified} verified · ${value.counts.partial} partial · `
            + `${value.counts.inferred} inferred · ${value.counts.unknown} unknown`,
          `File khớp từ khoá nhưng ngoài luồng: ${value.related_count}`,
          `Mở sơ đồ: ${value.artifacts.flow_html}`,
          `Dữ liệu: ${value.artifacts.flow_json}`,
          `Giải thích: ${value.artifacts.overview}`,
        ]
        if (value.warnings.length > 0) {
          lines.push(`Cảnh báo: ${value.warnings.length} mục — xem overview.md`)
        }
        lines.push('Nội dung source không được đưa vào kết quả; chỉ có đường dẫn và số liệu.')
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
      return {
        status: 'ok',
        flow_id: payload.flow_id,
        slug: payload.slug,
        repository: payload.repository,
        repository_name: payload.repository_name ?? path.basename(payload.repository ?? ''),
        artifacts_dir: payload.artifacts_dir,
        artifacts: {
          flow_json: payload.paths.flow_json,
          flow_html: payload.paths.flow_html,
          overview: payload.paths.overview,
          run: payload.paths.run,
        },
        // Absolute paths are host-only: they are shown to the caller that named
        // the repository, never folded into knowledge results or artifacts.
        path_visibility: {
          repository: 'host-only',
          artifacts: 'host-only',
          source_refs: 'model-facing (repository-relative)',
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
  for (const definition of knowledgeTools({ settings, core })) {
    ctx.tools.register(definition)
  }
}
