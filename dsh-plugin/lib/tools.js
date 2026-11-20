/**
 * Knowledge tools: index, search, context pack, impact analysis, verify, refresh.
 *
 * Shared rules for every tool in this file:
 *   - repository_path must be an absolute path inside allowedRoots (deny-by-default);
 *   - the core is reached through `tools/pfe_cli.py`, one JSON object on stdout;
 *   - results carry repository-relative paths, symbols and line ranges only —
 *     never raw source text, never an absolute workstation path;
 *   - a failure is an InputError with the core's stable code, so the runtime
 *     keeps the code instead of flattening it into prose.
 */
import path from 'node:path'
import { runCli } from './core-runner.js'
import { InputError, resolveRepository } from './paths.js'
import {
  assertObject, booleanFlag, enumValue, filtersObject, integerInRange,
  optionalString, rejectUnknownKeys, requiredString, stringArray,
} from './validate.js'

const TEXT = (value) => [{ type: 'text', text: value }]

/**
 * One description shape for every tool, so the model can choose without
 * reading the source. Keep each line short: the model pays for every token.
 */
function describe({ what, use, notUse, prereq, output, next, limits }) {
  // Six lines: what / when (+when not) / prerequisite / output meaning / next
  // action / limits. The model pays for this on every step, so each line stays
  // one clause — but dropping a line costs a wrong tool choice, which is more
  // expensive than the tokens. See README "Chi phí prompt".
  return [
    what,
    `DÙNG KHI: ${use} · KHÔNG DÙNG KHI: ${notUse}`,
    `ĐIỀU KIỆN: ${prereq}`,
    `KẾT QUẢ: ${output}`,
    `TIẾP THEO: ${next}`,
    `GIỚI HẠN: ${limits}`,
  ].join('\n')
}

function abortError(reason) {
  const error = new Error(reason instanceof Error ? reason.message : 'tool call aborted')
  error.name = 'AbortError'
  return error
}

function parsePayload(run) {
  const line = run.stdout.trim().split('\n').filter(Boolean).pop() ?? ''
  try {
    return JSON.parse(line)
  } catch {
    return null
  }
}

/**
 * Run one CLI subcommand and return the parsed payload.
 * Cancellation keeps its AbortError identity; timeout and core failure keep
 * separate codes so a caller can tell them apart.
 */
async function invoke(ctx) {
  const { settings, core, argv, exec, toolName, timeoutMs, inFlight } = ctx
  if (exec?.signal?.aborted) throw abortError(exec.signal.reason)
  if (!core.cli) {
    throw new InputError('core_cli_not_found',
      `${toolName}: bản core này không có tools/pfe_cli.py.`,
      'Cài bundle đã pack (có vendor/core) hoặc đặt config.coreRoot trỏ tới checkout của repo.')
  }
  const controller = new AbortController()
  const forward = () => controller.abort(exec.signal.reason)
  if (exec?.signal) exec.signal.addEventListener('abort', forward, { once: true })
  // Registered with the plugin so dispose() aborts this run too, not only the
  // flow tool's. Without this, unload leaves a child process running.
  inFlight?.add(controller)
  let run
  try {
    run = await runCli({
      pythonPath: settings.pythonPath,
      coreRoot: core.root,
      script: core.cli,
      args: argv,
      signal: controller.signal,
      timeoutMs: timeoutMs ?? settings.timeoutMs,
      maxOutputBytes: settings.maxOutputBytes,
    })
  } finally {
    inFlight?.delete(controller)
    if (exec?.signal) exec.signal.removeEventListener('abort', forward)
  }
  if (run.aborted) throw abortError(exec?.signal?.reason)
  if (run.timedOut) {
    throw new InputError('core_timeout',
      `${toolName}: core vượt quá ${timeoutMs ?? settings.timeoutMs} ms và đã bị dừng.`,
      'Tăng config.timeoutMs hoặc thu hẹp phạm vi phân tích.')
  }
  const payload = parsePayload(run)
  if (payload === null) {
    const tail = run.stderr.trim().split('\n').slice(-2).join(' ').slice(0, 400)
    throw new InputError(run.code === null ? 'core_spawn_failed' : 'core_failed',
      `${toolName}: core không trả JSON hợp lệ. ${tail}`,
      'Chạy lại CLI với --json để xem lỗi gốc.')
  }
  if (payload.status === 'error') {
    throw new InputError(payload.code, payload.message, payload.hint)
  }
  if (run.code !== 0) {
    throw new InputError('core_failed',
      `${toolName}: core exit ${run.code}.`,
      'Xem log của core để biết chi tiết.')
  }
  return payload
}

const repoProp = {
  type: 'string',
  description: 'Đường dẫn tuyệt đối tới thư mục repository, phải nằm trong allowedRoots.',
}

const refSchema = {
  type: 'object',
  properties: {
    path: { type: 'string' },
    start_line: { type: 'integer' },
    relation: { type: 'array', items: { type: 'string' } },
    confidence: { type: 'string' },
  },
  required: ['path', 'start_line', 'relation', 'confidence'],
  additionalProperties: false,
}

export function knowledgeTools({ settings, core, inFlight }) {
  const repository = (args, toolName) => {
    const value = requiredString(args, 'repository_path', toolName)
    return resolveRepository(value, { allowedRoots: settings.allowedRoots })
  }

  return [
    {
      name: 'project_code_index',
      description: describe({
    what: 'Xây/cập nhật index cục bộ tại <repo>/.pfe/index/ (maintenance).',
    use: 'lần đầu vào repo, hoặc sau khi pull/đổi nhiều file.',
    notUse: 'chỉ cần đọc một file đã biết đường dẫn.',
    prereq: 'repository_path tuyệt đối trong allowedRoots.',
    output: 'số file/symbol/route/test đã index; không trả source.',
    next: 'project_context_pack (hoặc project_code_search nếu biết tên).',
    limits: 'phân tích tĩnh, không chạy code; vector mặc định tắt.',
  }),
      parameters: {
        type: 'object',
        properties: {
          repository_path: repoProp,
          mode: { type: 'string', enum: ['full', 'incremental'] },
          include_vectors: { type: 'boolean' },
        },
        required: ['repository_path'],
        additionalProperties: false,
      },
      output: {
        schema: {
          type: 'object',
          properties: {
            index_id: { type: 'string' },
            index_version: { type: 'integer' },
            source_commit: { type: 'string' },
            mode: { type: 'string' },
            files_indexed: { type: 'integer' },
            files_parsed: { type: 'integer' },
            files_reused: { type: 'integer' },
            symbols_indexed: { type: 'integer' },
            routes_indexed: { type: 'integer' },
            tests_indexed: { type: 'integer' },
            entities: { type: 'integer' },
            facts: { type: 'integer' },
            stale_files: { type: 'integer' },
            embedding: {
              type: 'object',
              properties: {
                enabled: { type: 'boolean' },
                model: { type: 'string' },
                version: { type: 'string' },
                reason: { type: 'string' },
              },
              required: ['enabled'],
              additionalProperties: false,
            },
            warnings: { type: 'array', items: { type: 'string' } },
            changed: { type: 'array', items: { type: 'string' } },
            added: { type: 'array', items: { type: 'string' } },
            deleted: { type: 'array', items: { type: 'string' } },
            renamed: {
              type: 'array',
              items: {
                type: 'object',
                properties: { from: { type: 'string' }, to: { type: 'string' } },
                required: ['from', 'to'],
                additionalProperties: false,
              },
            },
          },
          required: ['index_id', 'index_version', 'source_commit', 'mode', 'files_indexed',
            'files_parsed', 'files_reused', 'symbols_indexed', 'routes_indexed',
            'tests_indexed', 'entities', 'facts', 'stale_files', 'embedding', 'warnings'],
          additionalProperties: false,
        },
        render(_args, value) {
          const embedding = value.embedding?.enabled
            ? `vector: ${value.embedding.model} v${value.embedding.version}`
            : `vector: tắt (${value.embedding?.reason ?? 'không bật'})`
          return TEXT([
            `Index ${value.mode}: ${value.files_indexed} file · ${value.entities} entity · ${value.facts} fact`,
            `Parse lại: ${value.files_parsed} · dùng lại cache: ${value.files_reused}`,
            `Symbol: ${value.symbols_indexed} · route: ${value.routes_indexed} · test: ${value.tests_indexed}`,
            `Commit nguồn: ${value.source_commit || 'không có git'} · stale: ${value.stale_files}`,
            `Tiếp theo: project_context_pack (gom context trước khi sửa).`,
            embedding,
            value.warnings.length > 0 ? `Cảnh báo: ${value.warnings.length}` : 'Không có cảnh báo.',
          ].join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => false,
      async execute(args, exec) {
        assertObject(args, 'project_code_index')
        rejectUnknownKeys(args, ['repository_path', 'mode', 'include_vectors'], 'project_code_index')
        const { root } = repository(args, 'project_code_index')
        const mode = enumValue(args, 'mode', 'project_code_index',
          ['full', 'incremental'], 'incremental')
        const includeVectors = booleanFlag(args, 'include_vectors', 'project_code_index', false)
        const argv = ['index', '--repo', root, '--mode', mode]
        if (includeVectors) argv.push('--include-vectors')
        const payload = await invoke({ settings, core, inFlight, argv, exec, toolName: 'project_code_index' })
        return {
          index_id: payload.index_id ?? '',
          index_version: payload.index_version ?? 0,
          source_commit: payload.source_commit ?? '',
          mode: payload.mode ?? mode,
          files_indexed: payload.files_indexed ?? 0,
          files_parsed: payload.files_parsed ?? 0,
          files_reused: payload.files_reused ?? 0,
          symbols_indexed: payload.symbols_indexed ?? 0,
          routes_indexed: payload.routes_indexed ?? 0,
          tests_indexed: payload.tests_indexed ?? 0,
          entities: payload.entities ?? 0,
          facts: payload.facts ?? 0,
          stale_files: payload.stale_files ?? 0,
          embedding: payload.embedding?.enabled
            ? {
              enabled: true,
              model: String(payload.embedding.model ?? ''),
              version: String(payload.embedding.version ?? ''),
            }
            : { enabled: false, reason: String(payload.embedding?.reason ?? 'không bật') },
          warnings: payload.warnings ?? [],
          changed: payload.changed ?? [],
          added: payload.added ?? [],
          deleted: payload.deleted ?? [],
          renamed: payload.renamed ?? [],
        }
      },
    },

    {
      name: 'project_code_search',
      description: describe({
    what: 'Tìm context: exact (FTS5) + graph + vector tùy chọn (maintenance).',
    use: 'biết tên hàm/lớp/route/từ khoá ngắn.',
    notUse: 'câu mô tả nghiệp vụ dài (dùng project_context_pack).',
    prereq: 'đã chạy project_code_index (nếu chưa: mã index_missing).',
    output: 'path, symbol, line range, relation, confidence, lý do khớp; không trả source.',
    next: 'mở đúng path:line, hoặc project_context_pack để gom theo task.',
    limits: 'khớp theo từ khoá; vector (nếu bật) chỉ là candidate lexical, không phải semantic.',
  }),
      parameters: {
        type: 'object',
        properties: {
          repository_path: repoProp,
          query: { type: 'string' },
          top_k: { type: 'integer', minimum: 1, maximum: 50 },
          filters: {
            type: 'object',
            properties: {
              language: { type: 'string' },
              kind: { type: 'string' },
              flow_id: { type: 'string' },
            },
            additionalProperties: false,
          },
        },
        required: ['repository_path', 'query'],
        additionalProperties: false,
      },
      output: {
        schema: {
          type: 'object',
          properties: {
            query: { type: 'string' },
            intent: { type: 'string' },
            source_commit: { type: 'string' },
            stale: { type: 'boolean' },
            channels: { type: 'array', items: { type: 'string' } },
            warnings: { type: 'array', items: { type: 'string' } },
            results: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  entity: { type: 'string' },
                  kind: { type: 'string' },
                  path: { type: 'string' },
                  symbol: { type: 'string' },
                  start_line: { type: 'integer' },
                  end_line: { type: 'integer' },
                  relation: { type: 'array', items: { type: 'string' } },
                  confidence: { type: 'string' },
                  reason: { type: 'string' },
                  score: { type: 'number' },
                  why_matched: { type: 'string' },
                  evidence_refs: { type: 'array', items: refSchema },
                },
                required: ['entity', 'kind', 'path', 'symbol', 'start_line', 'end_line',
                  'relation', 'confidence', 'reason', 'score', 'why_matched', 'evidence_refs'],
                additionalProperties: false,
              },
            },
          },
          required: ['query', 'intent', 'source_commit', 'stale', 'channels', 'warnings', 'results'],
          additionalProperties: false,
        },
        render(_args, value) {
          const lines = [
            `Truy hồi “${value.query}” · kênh: ${value.channels.join(', ') || 'không có'}`,
            `Kết quả: ${value.results.length}${value.stale ? ' · CẢNH BÁO: index cũ hơn HEAD' : ''}`,
          ]
          for (const item of value.results.slice(0, 8)) {
            lines.push(`- [${item.kind}] ${item.symbol || item.entity} — ${item.path}:${item.start_line}`
              + ` (${item.confidence}) · ${item.why_matched}`)
          }
          if (!value.results.length) lines.push('Không có kết quả: thử project_context_pack với mô tả nghiệp vụ.')
          else lines.push('Tiếp theo: mở path:line ở trên; cần gom theo task thì project_context_pack.')
          if (value.warnings.length > 0) lines.push(`Cảnh báo: ${value.warnings.join('; ')}`)
          return TEXT(lines.join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => true,
      async execute(args, exec) {
        assertObject(args, 'project_code_search')
        rejectUnknownKeys(args, ['repository_path', 'query', 'top_k', 'filters'], 'project_code_search')
        const { root } = repository(args, 'project_code_search')
        const query = requiredString(args, 'query', 'project_code_search')
        const topK = integerInRange(args, 'top_k', 'project_code_search',
          { min: 1, max: 50, fallback: 10 })
        const filters = filtersObject(args, 'project_code_search')
        const argv = ['search', '--repo', root, '--query', query, '--top-k', String(topK)]
        if (filters.language) argv.push('--language', filters.language)
        if (filters.kind) argv.push('--kind', filters.kind)
        const payload = await invoke({ settings, core, inFlight, argv, exec, toolName: 'project_code_search' })
        return {
          query: payload.query ?? query,
          intent: payload.intent ?? 'locate',
          source_commit: payload.source_commit ?? '',
          stale: Boolean(payload.stale),
          channels: payload.channels ?? [],
          warnings: payload.warnings ?? [],
          results: (payload.results ?? []).map((item) => ({
            entity: item.entity,
            kind: item.kind,
            path: item.path ?? '',
            symbol: item.symbol ?? '',
            start_line: item.start_line ?? 1,
            end_line: item.end_line ?? item.start_line ?? 1,
            relation: item.relation ?? [],
            confidence: item.confidence ?? 'inferred',
            reason: item.reason ?? item.why_matched ?? '',
            score: Number(item.score ?? 0),
            why_matched: item.why_matched ?? '',
            evidence_refs: (item.evidence_refs ?? []).map((ref) => ({
              path: ref.path ?? '',
              start_line: ref.start_line ?? 1,
              relation: ref.relation ?? [],
              confidence: ref.confidence ?? 'inferred',
            })),
          })),
        }
      },
    },

    {
      name: 'project_context_pack',
      description: describe({
        what: 'Gom context trước khi sửa: entry point, file nên đọc, dependency, test.',
        use: 'MẶC ĐỊNH trước khi sửa code — tool đầu tiên nên gọi.',
        notUse: 'chỉ cần kiểm artifact đã sinh (dùng project_verify_flow).',
        prereq: 'đã chạy project_code_index.',
        output: 'entry_points theo loại (http_route/cli_command/gui_event/callback/button_click/'
          + 'worker/main/public_api), likely_files, dependencies có path+line, related_tests.',
        next: 'sửa file trong likely_files, rồi project_impact_analysis.',
        limits: 'entry point chỉ từ dòng đăng ký thật; chưa chạy test; không trả source.',
      }),
      parameters: {
        type: 'object',
        properties: {
          repository_path: repoProp,
          task: { type: 'string' },
          include_snippets: { type: 'boolean' },
          max_files: { type: 'integer', minimum: 1, maximum: 40 },
        },
        required: ['repository_path', 'task'],
        additionalProperties: false,
      },
      output: {
        schema: {
          type: 'object',
          properties: {
            task: { type: 'string' },
            analysis_kind: { type: 'string' },
            intent: { type: 'string' },
            source_commit: { type: 'string' },
            stale: { type: 'boolean' },
            max_files: { type: 'integer' },
            snippets_included: { type: 'boolean' },
            limitations: { type: 'array', items: { type: 'string' } },
            warnings: { type: 'array', items: { type: 'string' } },
            not_verified: { type: 'array', items: { type: 'string' } },
            seen: {
              type: 'object',
              properties: {
                paths: { type: 'integer' },
                entities: { type: 'integer' },
                evidence: { type: 'integer' },
              },
              required: ['paths', 'entities', 'evidence'],
              additionalProperties: false,
            },
            relevant_flows: {
              type: 'array',
              items: {
                type: 'object',
                properties: { flow_id: { type: 'string' }, title: { type: 'string' } },
                required: ['flow_id', 'title'],
                additionalProperties: false,
              },
            },
            entry_points: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  path: { type: 'string' },
                  kind: { type: 'string' },
                  label: { type: 'string' },
                  route: { type: 'string' },
                  start_line: { type: 'integer' },
                  confidence: { type: 'string' },
                  evidence_kind: { type: 'string' },
                  evidence_refs: { type: 'array', items: refSchema },
                },
                required: ['path', 'kind', 'label', 'route', 'start_line', 'confidence',
                  'evidence_kind', 'evidence_refs'],
                additionalProperties: false,
              },
            },
            routes: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  route: { type: 'string' },
                  path: { type: 'string' },
                  start_line: { type: 'integer' },
                  confidence: { type: 'string' },
                  via: { type: 'string' },
                  evidence_refs: { type: 'array', items: refSchema },
                },
                required: ['route', 'path', 'start_line', 'confidence', 'via', 'evidence_refs'],
                additionalProperties: false,
              },
            },
            impacted_symbols: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  symbol: { type: 'string' },
                  path: { type: 'string' },
                  start_line: { type: 'integer' },
                  kind: { type: 'string' },
                  confidence: { type: 'string' },
                },
                required: ['symbol', 'path', 'start_line', 'kind', 'confidence'],
                additionalProperties: false,
              },
            },
            related_tests: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  path: { type: 'string' },
                  test: { type: 'string' },
                  start_line: { type: 'integer' },
                  confidence: { type: 'string' },
                  why_included: { type: 'string' },
                },
                required: ['path', 'test', 'start_line', 'confidence', 'why_included'],
                additionalProperties: false,
              },
            },
            likely_files: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  path: { type: 'string' },
                  symbol: { type: 'string' },
                  kind: { type: 'string' },
                  start_line: { type: 'integer' },
                  end_line: { type: 'integer' },
                  confidence: { type: 'string' },
                  location_confidence: { type: 'string' },
                  relevance_confidence: { type: 'string' },
                  why_matched: { type: 'string' },
                  relevance_why: { type: 'array', items: { type: 'string' } },
                  relation: { type: 'array', items: { type: 'string' } },
                  evidence_refs: { type: 'array', items: refSchema },
                },
                required: ['path', 'symbol', 'kind', 'start_line', 'end_line', 'confidence',
                  'location_confidence', 'relevance_confidence', 'why_matched',
                  'relevance_why', 'relation', 'evidence_refs'],
                additionalProperties: false,
              },
            },
            dependencies: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  entity: { type: 'string' },
                  kind: { type: 'string' },
                  path: { type: 'string' },
                  symbol: { type: 'string' },
                  start_line: { type: 'integer' },
                  end_line: { type: 'integer' },
                  relation: { type: 'string' },
                  confidence: { type: 'string' },
                  location_confidence: { type: 'string' },
                  relevance_confidence: { type: 'string' },
                  why_included: { type: 'string' },
                  evidence_refs: { type: 'array', items: refSchema },
                },
                required: ['entity', 'kind', 'path', 'symbol', 'start_line', 'end_line',
                  'relation', 'confidence', 'location_confidence', 'relevance_confidence',
                  'why_included', 'evidence_refs'],
                additionalProperties: false,
              },
            },
            external_dependencies: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  entity: { type: 'string' },
                  kind: { type: 'string' },
                  symbol: { type: 'string' },
                  relation: { type: 'string' },
                  confidence: { type: 'string' },
                  why_included: { type: 'string' },
                  location: { type: 'string' },
                },
                required: ['entity', 'kind', 'symbol', 'relation', 'confidence',
                  'why_included', 'location'],
                additionalProperties: false,
              },
            },
            evidence_refs: { type: 'array', items: refSchema },
          },
          required: ['task', 'analysis_kind', 'intent', 'source_commit', 'stale', 'max_files',
            'snippets_included', 'limitations', 'warnings', 'not_verified', 'seen',
            'relevant_flows', 'entry_points', 'routes', 'impacted_symbols', 'related_tests',
            'likely_files', 'dependencies', 'external_dependencies', 'evidence_refs'],
          additionalProperties: false,
        },
        render(_args, value) {
          const lines = [
            `Context: ${value.task}`,
            `Entry point: ${value.entry_points.length}`
              + (value.routes.length ? ` · route: ${value.routes[0].route}` : '')
              + ` · file nên đọc: ${value.likely_files.length}`,
          ]
          for (const item of value.likely_files.slice(0, 5)) {
            lines.push(`- ${item.path}:${item.start_line} ${item.symbol} (${item.relevance_confidence})`)
          }
          if (value.related_tests.length) {
            lines.push(`Test liên quan: ${value.related_tests.map((t) => t.path).join(', ')}`)
          }
          if (value.stale) lines.push('CẢNH BÁO: index cũ hơn HEAD — gọi project_knowledge_refresh.')
          for (const limit of value.limitations.slice(0, 2)) lines.push(`Giới hạn: ${limit}`)
          lines.push('Tiếp theo: sửa file trên, rồi project_impact_analysis.')
          return TEXT(lines.join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => true,
      async execute(args, exec) {
        assertObject(args, 'project_context_pack')
        rejectUnknownKeys(args, ['repository_path', 'task', 'max_files', 'include_snippets'], 'project_context_pack')
        const { root } = repository(args, 'project_context_pack')
        const task = requiredString(args, 'task', 'project_context_pack')
        const maxFiles = integerInRange(args, 'max_files', 'project_context_pack',
          { min: 1, max: 40, fallback: 12 })
        const snippets = booleanFlag(args, 'include_snippets', 'project_context_pack', false)
        const argv = ['context-pack', '--repo', root, '--task', task,
          '--max-files', String(maxFiles)]
        if (snippets) argv.push('--include-snippets')
        const payload = await invoke({ settings, core, inFlight, argv, exec, toolName: 'project_context_pack' })
        return {
          task: payload.task ?? task,
          analysis_kind: payload.analysis_kind ?? 'context_pack',
          intent: payload.intent ?? 'locate',
          source_commit: payload.source_commit ?? '',
          stale: Boolean(payload.stale),
          max_files: payload.max_files ?? maxFiles,
          snippets_included: Boolean(payload.snippets_included),
          limitations: payload.limitations ?? [],
          warnings: payload.warnings ?? [],
          not_verified: payload.not_verified ?? ['runtime', 'ui'],
          seen: payload.seen ?? { paths: 0, entities: 0, evidence: 0 },
          relevant_flows: payload.relevant_flows ?? [],
          entry_points: payload.entry_points ?? [],
          routes: payload.routes ?? [],
          impacted_symbols: payload.impacted_symbols ?? [],
          related_tests: payload.related_tests ?? [],
          likely_files: (payload.likely_files ?? []).map((item) => ({
            path: item.path ?? '',
            symbol: item.symbol ?? '',
            kind: item.kind ?? 'file',
            start_line: item.start_line ?? 1,
            end_line: item.end_line ?? item.start_line ?? 1,
            confidence: item.confidence ?? 'inferred',
            location_confidence: item.location_confidence ?? 'unknown',
            relevance_confidence: item.relevance_confidence ?? 'inferred',
            why_matched: item.why_matched ?? '',
            relevance_why: item.relevance_why ?? [],
            relation: item.relation ?? [],
            evidence_refs: item.evidence_refs ?? [],
          })),
          dependencies: payload.dependencies ?? [],
          external_dependencies: payload.external_dependencies ?? [],
          evidence_refs: payload.evidence_refs ?? [],
        }
      },
    },

    {
      name: 'project_impact_analysis',
      description: describe({
    what: 'Phân tích tác động của các file vừa sửa.',
    use: 'SAU KHI sửa, trước khi commit.',
    notUse: 'trước khi sửa (dùng project_context_pack).',
    prereq: 'đã chạy project_code_index; truyền changed_files hoặc diff.',
    output: 'flow/route/symbol bị ảnh hưởng, test liên quan, module phụ thuộc, risk_level.',
    next: 'chạy test trong related_tests, rồi project_verify_flow.',
    limits: 'chỉ thấy quan hệ có trong index; file mới chưa index báo unknown_files.',
  }),
      parameters: {
        type: 'object',
        properties: {
          repository_path: repoProp,
          changed_files: { type: 'array', items: { type: 'string' } },
          diff: { type: 'string' },
        },
        required: ['repository_path'],
        additionalProperties: false,
      },
      output: {
        schema: {
          type: 'object',
          properties: {
            source_commit: { type: 'string' },
            changed_files: { type: 'array', items: { type: 'string' } },
            risk_level: { type: 'string' },
            risk_reasons: { type: 'array', items: { type: 'string' } },
            index_stale: { type: 'boolean' },
            stale_files: { type: 'array', items: { type: 'string' } },
            unknown_files: { type: 'array', items: { type: 'string' } },
            warnings: { type: 'array', items: { type: 'string' } },
            suggested_verification: { type: 'array', items: { type: 'string' } },
            affected_flows: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  flow_id: { type: 'string' },
                  confidence: { type: 'string' },
                  path: { type: 'string' },
                },
                required: ['flow_id', 'confidence', 'path'],
                additionalProperties: false,
              },
            },
            affected_routes: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  route: { type: 'string' },
                  path: { type: 'string' },
                  start_line: { type: 'integer' },
                },
                required: ['route', 'path', 'start_line'],
                additionalProperties: false,
              },
            },
            affected_symbols: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  symbol: { type: 'string' },
                  path: { type: 'string' },
                  start_line: { type: 'integer' },
                },
                required: ['symbol', 'path', 'start_line'],
                additionalProperties: false,
              },
            },
            related_tests: {
              type: 'array',
              items: {
                type: 'object',
                properties: { test: { type: 'string' }, path: { type: 'string' } },
                required: ['test', 'path'],
                additionalProperties: false,
              },
            },
            downstream_modules: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  file: { type: 'string' },
                  relation: { type: 'string' },
                  path: { type: 'string' },
                },
                required: ['file', 'relation', 'path'],
                additionalProperties: false,
              },
            },
            stale_artifacts: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  flow_id: { type: 'string' },
                  generated_at: { type: 'string' },
                  artifact_dir: { type: 'string' },
                },
                required: ['flow_id', 'generated_at', 'artifact_dir'],
                additionalProperties: false,
              },
            },
            evidence_refs: { type: 'array', items: refSchema },
          },
          required: ['source_commit', 'changed_files', 'risk_level', 'risk_reasons',
            'index_stale', 'stale_files', 'unknown_files', 'warnings', 'suggested_verification',
            'affected_flows', 'affected_routes', 'affected_symbols', 'related_tests',
            'downstream_modules', 'stale_artifacts', 'evidence_refs'],
          additionalProperties: false,
        },
        render(_args, value) {
          return TEXT([
            `Tác động: ${value.changed_files.length} file · rủi ro ${value.risk_level}`,
            ...value.risk_reasons.map((item) => `- ${item}`),
            `Flow: ${value.affected_flows.length} · route: ${value.affected_routes.length} · `
              + `symbol: ${value.affected_symbols.length} · test: ${value.related_tests.length}`,
            `Kiểm chứng: ${value.suggested_verification.join(' · ')}`,
            'Tiếp theo: chạy test ở trên, rồi project_verify_flow.',
          ].join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => true,
      async execute(args, exec) {
        assertObject(args, 'project_impact_analysis')
        rejectUnknownKeys(args, ['repository_path', 'changed_files', 'diff'], 'project_impact_analysis')
        const { root } = repository(args, 'project_impact_analysis')
        const changed = stringArray(args, 'changed_files', 'project_impact_analysis')
        const diff = optionalString(args, 'diff', 'project_impact_analysis')
        if (changed.length === 0 && (diff === undefined || diff.trim() === '')) {
          throw new InputError('no_changed_files',
            'project_impact_analysis: cần changed_files hoặc diff.',
            'Truyền changed_files: ["src/app.py"] hoặc một unified diff.')
        }
        const argv = ['impact', '--repo', root]
        for (const item of changed) argv.push('--changed', item)
        if (diff) argv.push('--diff', diff)
        const payload = await invoke({ settings, core, inFlight, argv, exec, toolName: 'project_impact_analysis' })
        return {
          source_commit: payload.source_commit ?? '',
          changed_files: payload.changed_files ?? changed,
          risk_level: payload.risk_level ?? 'low',
          risk_reasons: payload.risk_reasons ?? [],
          index_stale: Boolean(payload.index_stale),
          stale_files: payload.stale_files ?? [],
          unknown_files: payload.unknown_files ?? [],
          warnings: payload.warnings ?? [],
          suggested_verification: payload.suggested_verification ?? [],
          affected_flows: payload.affected_flows ?? [],
          affected_routes: payload.affected_routes ?? [],
          affected_symbols: payload.affected_symbols ?? [],
          related_tests: payload.related_tests ?? [],
          downstream_modules: payload.downstream_modules ?? [],
          stale_artifacts: payload.stale_artifacts ?? [],
          evidence_refs: payload.evidence_refs ?? [],
        }
      },
    },

    {
      name: 'project_verify_flow',
      description: describe({
    what: 'Kiểm artifact/flow: schema, bằng chứng, HTML tĩnh, privacy, test mapping.',
    use: 'bước cuối, sau khi sửa và render lại flow.',
    notUse: 'thay cho việc chạy test hoặc mở trình duyệt.',
    prereq: 'đã có artifact trong <repo>/artifacts/flows/.',
    output: 'static_verdict (đã kiểm tĩnh) tách khỏi overall_verdict (cần cả UI + runtime), '
      + 'gates, checks, next_action.',
    next: 'overall=partial thì mở flow.html và chạy test liên quan; không đọc là "đã pass".',
    limits: 'quét HTML tĩnh KHÔNG phải kiểm trình duyệt; test mapping KHÔNG phải đã chạy test.',
  }),
      parameters: {
        type: 'object',
        properties: { repository_path: repoProp },
        required: ['repository_path'],
        additionalProperties: false,
      },
      output: {
        schema: {
          type: 'object',
          properties: {
            verdict: { type: 'string' },
            static_verdict: { type: 'string' },
            overall_verdict: { type: 'string' },
            source_commit: { type: 'string' },
            flow_artifacts: { type: 'integer' },
            ui_verified: { type: 'boolean' },
            runtime_verified: { type: 'boolean' },
            notes: { type: 'array', items: { type: 'string' } },
            not_verified: { type: 'array', items: { type: 'string' } },
            next_action: { type: 'string' },
            gates: {
              type: 'object',
              properties: {
                static: { type: 'string' },
                ui: { type: 'string' },
                runtime: { type: 'string' },
              },
              required: ['static', 'ui', 'runtime'],
              additionalProperties: false,
            },
            checks: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  check: { type: 'string' },
                  status: { type: 'string' },
                  detail: { type: 'string' },
                  evidence: { type: 'array', items: { type: 'string' } },
                },
                required: ['check', 'status', 'detail', 'evidence'],
                additionalProperties: false,
              },
            },
          },
          required: ['verdict', 'static_verdict', 'overall_verdict', 'source_commit',
            'flow_artifacts', 'ui_verified', 'runtime_verified', 'notes', 'not_verified',
            'next_action', 'gates', 'checks'],
          additionalProperties: false,
        },
        render(_args, value) {
          // The two verdicts mean different things and a reader who conflates
          // them thinks the page was rendered and the tests were run. Say which
          // is which, then which checks did run.
          const STATIC_PLAIN = 'chỉ đọc file, chưa mở trang'
          const lines = [
            `Kiểm tĩnh: ${value.static_verdict} (${STATIC_PLAIN})`,
            `Kết luận tổng: ${value.overall_verdict}`
              + (value.overall_verdict === 'partial'
                ? ' — chưa đủ bằng chứng để coi là đã pass' : ''),
            `Artifact: ${value.flow_artifacts} flow · gate chưa chạy: `
              + `${value.not_verified.join(', ') || 'không có'}`,
          ]
          const failed = value.checks.filter((c) => c.status === 'fail')
          for (const check of failed.slice(0, 3)) lines.push(`- FAIL ${check.check}: ${check.detail}`)
          if (!failed.length) {
            const blocked = value.checks.filter((c) => c.status === 'blocked')
            if (blocked.length) lines.push(`Check chưa chạy: ${blocked.map((c) => c.check).join(', ')}`)
          }
          lines.push(`Tiếp theo: ${value.next_action}`)
          return TEXT(lines.join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => true,
      async execute(args, exec) {
        assertObject(args, 'project_verify_flow')
        rejectUnknownKeys(args, ['repository_path'], 'project_verify_flow')
        const { root } = repository(args, 'project_verify_flow')
        const payload = await invoke({
          settings, core, argv: ['verify', '--repo', root], exec,
          toolName: 'project_verify_flow',
        })
        return {
          verdict: payload.overall_verdict ?? payload.verdict ?? 'partial',
          static_verdict: payload.static_verdict ?? 'partial',
          overall_verdict: payload.overall_verdict ?? 'partial',
          source_commit: payload.source_commit ?? '',
          flow_artifacts: payload.flow_artifacts ?? 0,
          ui_verified: Boolean(payload.ui_verified),
          runtime_verified: Boolean(payload.runtime_verified),
          notes: payload.notes ?? [],
          not_verified: payload.not_verified ?? ['ui', 'runtime'],
          next_action: payload.next_action ?? '',
          gates: payload.gates ?? { static: 'partial', ui: 'blocked', runtime: 'blocked' },
          checks: payload.checks ?? [],
        }
      },
    },

    {
      name: 'project_knowledge_refresh',
      description: describe({
    what: 'Refresh index tăng dần sau khi sửa code (maintenance).',
    use: 'sau khi sửa file, trước khi search/impact lần nữa.',
    notUse: 'khi index chưa tồn tại (dùng project_code_index mode=full).',
    prereq: 'index đã tồn tại.',
    output: 'file parse lại/dùng lại, changed/added/deleted/renamed, stale.',
    next: 'project_code_search hoặc project_impact_analysis.',
    limits: 'rename nhận qua content hash; không rebuild toàn bộ nếu không cần.',
  }),
      parameters: {
        type: 'object',
        properties: {
          repository_path: repoProp,
          mode: { type: 'string', enum: ['full', 'incremental'] },
          include_vectors: { type: 'boolean' },
        },
        required: ['repository_path'],
        additionalProperties: false,
      },
      output: {
        schema: {
          type: 'object',
          properties: {
            mode: { type: 'string' },
            files_parsed: { type: 'integer' },
            files_reused: { type: 'integer' },
            stale_files: { type: 'integer' },
            no_full_rebuild: { type: 'boolean' },
            changed: { type: 'array', items: { type: 'string' } },
            added: { type: 'array', items: { type: 'string' } },
            deleted: { type: 'array', items: { type: 'string' } },
            renamed: {
              type: 'array',
              items: {
                type: 'object',
                properties: { from: { type: 'string' }, to: { type: 'string' } },
                required: ['from', 'to'],
                additionalProperties: false,
              },
            },
            warnings: { type: 'array', items: { type: 'string' } },
          },
          required: ['mode', 'files_parsed', 'files_reused', 'stale_files',
            'no_full_rebuild', 'changed', 'added', 'deleted', 'renamed', 'warnings'],
          additionalProperties: false,
        },
        render(_args, value) {
          return TEXT([
            `Refresh ${value.mode}: parse lại ${value.files_parsed} · dùng lại ${value.files_reused}`,
            `changed ${value.changed.length} · added ${value.added.length} · `
              + `deleted ${value.deleted.length} · renamed ${value.renamed.length}`,
            `Rebuild toàn bộ: ${value.no_full_rebuild ? 'không' : 'có'}`,
            'Tiếp theo: project_code_search hoặc project_impact_analysis.',
          ].join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => false,
      async execute(args, exec) {
        assertObject(args, 'project_knowledge_refresh')
        rejectUnknownKeys(args, ['repository_path', 'mode', 'include_vectors'], 'project_knowledge_refresh')
        const { root } = repository(args, 'project_knowledge_refresh')
        const mode = enumValue(args, 'mode', 'project_knowledge_refresh',
          ['full', 'incremental'], 'incremental')
        const includeVectors = booleanFlag(args, 'include_vectors',
          'project_knowledge_refresh', false)
        const argv = ['refresh', '--repo', root, '--mode', mode]
        if (includeVectors) argv.push('--include-vectors')
        const payload = await invoke({
          settings, core, inFlight, argv, exec, toolName: 'project_knowledge_refresh',
        })
        return {
          mode: payload.mode ?? mode,
          files_parsed: payload.files_parsed ?? 0,
          files_reused: payload.files_reused ?? 0,
          stale_files: payload.stale_files ?? 0,
          no_full_rebuild: Boolean(payload.no_full_rebuild),
          changed: payload.changed ?? [],
          added: payload.added ?? [],
          deleted: payload.deleted ?? [],
          renamed: payload.renamed ?? [],
          warnings: payload.warnings ?? [],
        }
      },
    },
  ]
}

export { InputError, path }