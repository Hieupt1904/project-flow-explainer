/**
 * DSH adapter for Project Flow Explainer.
 *
 * The core (Python, no third-party packages) stays independent: this plugin
 * only validates arguments, contains paths, calls the core CLI and maps the
 * result. It imports nothing from @deepseek-ai/* on purpose — a profile's
 * node_modules cannot resolve those packages, so the definition is hand-built
 * and handed to `ctx.tools.register`, which manages its lifecycle.
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { runCore } from './lib/core-runner.js'
import {
  InputError, resolveArtifactRoot, resolveCoreRoot, resolveRepository,
} from './lib/paths.js'

export const name = 'project-flow-explainer'
export const inject = ['tools']

export const TOOL_NAME = 'project_flow_explain'
const PACKAGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const DEFAULTS = {
  pythonPath: 'python3',
  coreRoot: PACKAGE_ROOT,
  allowedRoots: [],
  timeoutMs: 180000,
  maxOutputBytes: 1024 * 1024,
}

function badConfig(message) {
  throw new Error(`${name}: ${message}`)
}

function normalizeConfig(config) {
  const settings = { ...DEFAULTS, ...(config ?? {}) }
  if (typeof settings.pythonPath !== 'string' || settings.pythonPath.trim() === '') {
    badConfig('pythonPath phải là chuỗi không rỗng')
  }
  if (typeof settings.coreRoot !== 'string' || settings.coreRoot.trim() === '') {
    badConfig('coreRoot phải là chuỗi không rỗng')
  }
  if (!Array.isArray(settings.allowedRoots) || settings.allowedRoots.some((item) => typeof item !== 'string')) {
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

function describeFailure({ code, stderr, timedOut, aborted, truncated }) {
  if (aborted) return 'Lần chạy đã bị huỷ; tiến trình core đã được dừng.'
  if (timedOut) return 'Core vượt quá thời gian cho phép và đã bị dừng.'
  const tail = stderr.trim().split('\n').slice(-4).join(' ').slice(0, 600)
  const suffix = truncated ? ' (log bị cắt bớt)' : ''
  return `Core kết thúc với mã ${code}: ${tail || 'không có thông tin lỗi'}${suffix}`
}

function parseCoreResult(result) {
  const raw = result.stdout.trim()
  const line = raw.split('\n').filter(Boolean).pop() ?? ''
  try {
    return JSON.parse(line)
  } catch {
    return null
  }
}

const TEXT = (value) => [{ type: 'text', text: value }]

/**
 * @param {object} ctx - Cordis context with the `tools` service injected.
 * @param {object} [config] - profile patch config.
 */
export function apply(ctx, config = {}) {
  const settings = normalizeConfig(config)
  const { root: coreRoot, script } = resolveCoreRoot(settings.coreRoot)
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
      + 'kèm dữ liệu có cấu trúc và bản giải thích. Chỉ đọc source, không gọi network, '
      + 'không chạy code của repository, không sửa file nguồn. '
      + 'Trả đường dẫn tới flow.json, flow.html, overview.md và số bước theo mức tin cậy.',
    parameters: {
      type: 'object',
      properties: {
        repository_path: {
          type: 'string',
          description: 'Đường dẫn tuyệt đối tới thư mục repository cần phân tích.',
        },
        flow_request: {
          type: 'string',
          description: 'Mô tả flow bằng tiếng Việt thông thường, ví dụ: "từ lúc bấm xuất báo cáo '
            + 'đến khi nhận được file, dữ liệu đi qua những bước nào và lỗi xử lý ở đâu".',
        },
        output_directory: {
          type: 'string',
          description: 'Thư mục chứa artifact, phải nằm trong repository đã duyệt. '
            + 'Mặc định: <repo>/artifacts/flows.',
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
        required: ['status', 'flow_id', 'slug', 'repository', 'artifacts', 'counts',
          'files_scanned', 'source_version', 'warnings', 'limits'],
        additionalProperties: false,
      },
      render(_args, value) {
        const lines = [
          `Đã dựng sơ đồ: ${value.flow_id}`,
          `Bước: ${value.counts.verified} verified · ${value.counts.partial} partial · `
            + `${value.counts.inferred} inferred · ${value.counts.unknown} unknown`,
          `File đã đọc: ${value.files_scanned}`,
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
      const repository = resolveRepository(args.repository_path, {
        allowedRoots: settings.allowedRoots,
      })
      const outputDirectory = resolveArtifactRoot(repository.root, args.output_directory)
      const request = typeof args.flow_request === 'string' ? args.flow_request.trim() : ''
      if (request === '') {
        throw new InputError(
          'Thiếu flow_request.',
          'Mô tả flow cần phân tích, ví dụ: "từ lúc người dùng nhấn xuất báo cáo đến khi nhận file".',
        )
      }

      const controller = new AbortController()
      const forwardAbort = () => controller.abort()
      if (exec?.signal) {
        if (exec.signal.aborted) controller.abort()
        else exec.signal.addEventListener('abort', forwardAbort, { once: true })
      }
      inFlight.add(controller)

      let run
      try {
        run = await runCore({
          pythonPath: settings.pythonPath,
          coreRoot,
          script,
          repository: repository.root,
          request,
          outputDirectory,
          slug: typeof args.slug === 'string' && args.slug.trim() !== '' ? args.slug.trim() : undefined,
          signal: controller.signal,
          timeoutMs: settings.timeoutMs,
          maxOutputBytes: settings.maxOutputBytes,
        })
      } finally {
        inFlight.delete(controller)
        if (exec?.signal) exec.signal.removeEventListener('abort', forwardAbort)
      }

      const payload = parseCoreResult(run)
      if (payload === null) {
        throw new Error(describeFailure(run))
      }
      if (payload.status === 'error') {
        throw new InputError(
          `[${payload.code}] ${payload.message}`,
          payload.hint,
        )
      }
      if (run.code !== 0 && payload.status !== 'ok') {
        throw new Error(describeFailure(run))
      }

      const source = payload.source ?? {}
      return {
        status: 'ok',
        flow_id: payload.flow_id,
        slug: payload.slug,
        repository: payload.repository,
        artifacts: {
          flow_json: payload.paths.flow_json,
          flow_html: payload.paths.flow_html,
          overview: payload.paths.overview,
          run: payload.paths.run,
        },
        counts: {
          verified: payload.counts?.verified ?? 0,
          partial: payload.counts?.partial ?? 0,
          inferred: payload.counts?.inferred ?? 0,
          unknown: payload.counts?.unknown ?? 0,
        },
        files_scanned: payload.files_scanned ?? 0,
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
}
