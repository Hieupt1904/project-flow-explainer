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
  optionalString, requiredString, stringArray,
} from './validate.js'

const TEXT = (value) => [{ type: 'text', text: value }]

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
  const { settings, core, argv, exec, toolName, timeoutMs } = ctx
  if (exec?.signal?.aborted) throw abortError(exec.signal.reason)
  if (!core.cli) {
    throw new InputError('core_cli_not_found',
      `${toolName}: bản core này không có tools/pfe_cli.py.`,
      'Cài bundle đã pack (có vendor/core) hoặc đặt config.coreRoot trỏ tới checkout của repo.')
  }
  const controller = new AbortController()
  const forward = () => controller.abort(exec.signal.reason)
  if (exec?.signal) exec.signal.addEventListener('abort', forward, { once: true })
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

export function knowledgeTools({ settings, core }) {
  const repository = (args, toolName) => {
    const value = requiredString(args, 'repository_path', toolName)
    return resolveRepository(value, { allowedRoots: settings.allowedRoots })
  }

  return [
    {
      name: 'project_code_index',
      description:
        'Xây hoặc cập nhật index tri thức code cục bộ tại <repo>/.pfe/index/. '
        + 'Index gồm entity/relation có bằng chứng (file, symbol, route, import, call site, '
        + 'test, flow, error case), full-text search và vector tùy chọn (local-only). '
        + 'Không gọi network, không chạy code của repository, không index file bí mật.',
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
            embedding,
            value.warnings.length > 0 ? `Cảnh báo: ${value.warnings.length}` : 'Không có cảnh báo.',
          ].join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => false,
      async execute(args, exec) {
        assertObject(args, 'project_code_index')
        const { root } = repository(args, 'project_code_index')
        const mode = enumValue(args, 'mode', 'project_code_index',
          ['full', 'incremental'], 'incremental')
        const includeVectors = booleanFlag(args, 'include_vectors', 'project_code_index', false)
        const argv = ['index', '--repo', root, '--mode', mode]
        if (includeVectors) argv.push('--include-vectors')
        const payload = await invoke({ settings, core, argv, exec, toolName: 'project_code_index' })
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
      description:
        'Tìm context trong code bằng truy hồi hybrid: exact (FTS5) → vector tùy chọn → '
        + 'mở rộng graph → xếp hạng lại. Trả path, symbol, line range, relation, confidence, '
        + 'lý do khớp và source commit. Không trả nội dung source thô.',
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
          if (value.warnings.length > 0) lines.push(`Cảnh báo: ${value.warnings.join('; ')}`)
          return TEXT(lines.join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => true,
      async execute(args, exec) {
        assertObject(args, 'project_code_search')
        const { root } = repository(args, 'project_code_search')
        const query = requiredString(args, 'query', 'project_code_search')
        const topK = integerInRange(args, 'top_k', 'project_code_search',
          { min: 1, max: 50, fallback: 10 })
        const filters = filtersObject(args, 'project_code_search')
        const argv = ['search', '--repo', root, '--query', query, '--top-k', String(topK)]
        if (filters.language) argv.push('--language', filters.language)
        if (filters.kind) argv.push('--kind', filters.kind)
        const payload = await invoke({ settings, core, argv, exec, toolName: 'project_code_search' })
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
      description:
        'Gom context cho một task code: flow liên quan, entry point, symbol bị ảnh hưởng, '
        + 'test liên quan, file nên đọc, phụ thuộc, cảnh báo stale. Mặc định KHÔNG trả snippet; '
        + 'include_snippets chỉ dùng khi người gọi chủ động bật trong phiên local.',
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
            source_commit: { type: 'string' },
            stale: { type: 'boolean' },
            max_files: { type: 'integer' },
            snippets_included: { type: 'boolean' },
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
                  route: { type: 'string' },
                  start_line: { type: 'integer' },
                  confidence: { type: 'string' },
                },
                required: ['path', 'route', 'start_line', 'confidence'],
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
                },
                required: ['symbol', 'path', 'start_line'],
                additionalProperties: false,
              },
            },
            related_tests: {
              type: 'array',
              items: {
                type: 'object',
                properties: { path: { type: 'string' }, start_line: { type: 'integer' } },
                required: ['path', 'start_line'],
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
                  start_line: { type: 'integer' },
                  end_line: { type: 'integer' },
                  confidence: { type: 'string' },
                  why_matched: { type: 'string' },
                },
                required: ['path', 'symbol', 'start_line', 'end_line', 'confidence', 'why_matched'],
                additionalProperties: false,
              },
            },
            dependencies: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  entity: { type: 'string' },
                  relation: { type: 'string' },
                  confidence: { type: 'string' },
                },
                required: ['entity', 'relation', 'confidence'],
                additionalProperties: false,
              },
            },
            warnings: { type: 'array', items: { type: 'string' } },
            evidence_refs: { type: 'array', items: refSchema },
          },
          required: ['task', 'source_commit', 'stale', 'max_files', 'snippets_included',
            'relevant_flows', 'entry_points', 'impacted_symbols', 'related_tests',
            'likely_files', 'dependencies', 'warnings', 'evidence_refs'],
          additionalProperties: false,
        },
        render(_args, value) {
          const lines = [
            `Context pack cho: ${value.task}`,
            `Commit: ${value.source_commit || 'không có git'}${value.stale ? ' · index stale' : ''}`,
            `Entry point: ${value.entry_points.length} · file nên đọc: ${value.likely_files.length}`,
          ]
          for (const item of value.likely_files.slice(0, 8)) {
            lines.push(`- ${item.path}:${item.start_line} ${item.symbol} — ${item.why_matched}`)
          }
          lines.push(`Snippet: ${value.snippets_included ? 'có (chế độ local)' : 'không'}`)
          return TEXT(lines.join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => true,
      async execute(args, exec) {
        assertObject(args, 'project_context_pack')
        const { root } = repository(args, 'project_context_pack')
        const task = requiredString(args, 'task', 'project_context_pack')
        const maxFiles = integerInRange(args, 'max_files', 'project_context_pack',
          { min: 1, max: 40, fallback: 12 })
        const snippets = booleanFlag(args, 'include_snippets', 'project_context_pack', false)
        const argv = ['context-pack', '--repo', root, '--task', task,
          '--max-files', String(maxFiles)]
        if (snippets) argv.push('--include-snippets')
        const payload = await invoke({ settings, core, argv, exec, toolName: 'project_context_pack' })
        return {
          task: payload.task ?? task,
          source_commit: payload.source_commit ?? '',
          stale: Boolean(payload.stale),
          max_files: payload.max_files ?? maxFiles,
          snippets_included: Boolean(payload.snippets_included),
          relevant_flows: payload.relevant_flows ?? [],
          entry_points: payload.entry_points ?? [],
          impacted_symbols: payload.impacted_symbols ?? [],
          related_tests: payload.related_tests ?? [],
          likely_files: (payload.likely_files ?? []).map((item) => ({
            path: item.path ?? '',
            symbol: item.symbol ?? '',
            start_line: item.start_line ?? 1,
            end_line: item.end_line ?? item.start_line ?? 1,
            confidence: item.confidence ?? 'inferred',
            why_matched: item.why_matched ?? '',
          })),
          dependencies: payload.dependencies ?? [],
          warnings: payload.warnings ?? [],
          evidence_refs: payload.evidence_refs ?? [],
        }
      },
    },

    {
      name: 'project_impact_analysis',
      description:
        'Phân tích tác động của các file thay đổi: flow/route/symbol bị ảnh hưởng, test liên quan, '
        + 'module phụ thuộc, mức rủi ro, artifact stale và gợi ý kiểm chứng. '
        + 'Cần index; trả đường dẫn tương đối và bằng chứng, không trả source.',
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
          ].join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => true,
      async execute(args, exec) {
        assertObject(args, 'project_impact_analysis')
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
        const payload = await invoke({ settings, core, argv, exec, toolName: 'project_impact_analysis' })
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
      description:
        'Kiểm tra kết quả đã sinh: schema graph, bằng chứng (không có call-edge giả, không có '
        + 'nhánh bypass), artifact đủ 3 file public, HTML không tải tài nguyên ngoài, '
        + 'privacy (không absolute path/secret trong artifact), mapping test. '
        + 'Trả verdict pass/partial/fail kèm bằng chứng từng check.',
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
            source_commit: { type: 'string' },
            flow_artifacts: { type: 'integer' },
            ui_verified: { type: 'boolean' },
            runtime_verified: { type: 'boolean' },
            notes: { type: 'array', items: { type: 'string' } },
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
          required: ['verdict', 'source_commit', 'flow_artifacts', 'ui_verified',
            'runtime_verified', 'notes', 'checks'],
          additionalProperties: false,
        },
        render(_args, value) {
          const lines = [`Verdict: ${value.verdict} · ${value.flow_artifacts} flow artifact`]
          for (const check of value.checks) {
            lines.push(`- ${check.check}: ${check.status} — ${check.detail}`)
          }
          lines.push('ui_verified=false: chỉ đọc HTML tĩnh. runtime_verified=false: không chạy code.')
          return TEXT(lines.join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => true,
      async execute(args, exec) {
        assertObject(args, 'project_verify_flow')
        const { root } = repository(args, 'project_verify_flow')
        const payload = await invoke({
          settings, core, argv: ['verify', '--repo', root], exec,
          toolName: 'project_verify_flow',
        })
        return {
          verdict: payload.verdict ?? 'partial',
          source_commit: payload.source_commit ?? '',
          flow_artifacts: payload.flow_artifacts ?? 0,
          ui_verified: Boolean(payload.ui_verified),
          runtime_verified: Boolean(payload.runtime_verified),
          notes: payload.notes ?? [],
          checks: payload.checks ?? [],
        }
      },
    },

    {
      name: 'project_knowledge_refresh',
      description:
        'Refresh index tăng dần sau khi sửa code: phát hiện file changed/added/deleted/renamed, '
        + 'chỉ parse lại phần đã đổi, báo stale. Không rebuild toàn bộ nếu không cần.',
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
          ].join('\n'))
        },
      },
      timeoutMs: settings.timeoutMs,
      isConcurrencySafe: () => false,
      async execute(args, exec) {
        assertObject(args, 'project_knowledge_refresh')
        const { root } = repository(args, 'project_knowledge_refresh')
        const mode = enumValue(args, 'mode', 'project_knowledge_refresh',
          ['full', 'incremental'], 'incremental')
        const includeVectors = booleanFlag(args, 'include_vectors',
          'project_knowledge_refresh', false)
        const argv = ['refresh', '--repo', root, '--mode', mode]
        if (includeVectors) argv.push('--include-vectors')
        const payload = await invoke({
          settings, core, argv, exec, toolName: 'project_knowledge_refresh',
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
