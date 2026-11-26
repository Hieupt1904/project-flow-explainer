/**
 * Slash command `/project-flow-explainer` — the human entry point.
 *
 * Why a command and not only a tool: a tool is chosen by the model, so a person
 * who already knows what they want has to explain it and hope the model agrees.
 * A command is chosen by the person, runs the same core, and returns its output
 * straight to the UI without entering model history
 * (`@deepseek-ai/dsh-commands`: command output is rendered by the adapter and
 * does not affect the model's context or cache).
 *
 * Contract kept identical to the tool path: same repository policy, same core
 * invocation, same artifact location, no network, no repository code execution.
 */
import path from 'node:path'
import { runCli, runCore } from './core-runner.js'
import { existsSync } from 'node:fs'
import {
  InputError, resolveArtifactRoot, resolveRepository,
} from './paths.js'

export const COMMAND_NAME = 'project-flow-explainer'

const USAGE = 'Cách dùng: /project-flow-explainer <mô tả luồng>'
  + '\nVí dụ: /project-flow-explainer từ lúc bấm xuất báo cáo đến khi nhận được file'
  + '\nPhạm vi: thư mục của phiên đang mở, cộng các thư mục khai báo trong allowedRoots.'

/** Split `<request>` from optional `--repo <path>` so a person can target another repo. */
/**
 * Split `<request> [--repo <path>]`, accepting the three shapes a person types.
 *
 * A path with a space is the normal case on macOS and common on Linux, so the
 * value must be readable as `--repo "a b"`, `--repo='a b'` or a bare `--repo a`
 * (single token). The first version used `\S+` and silently swallowed only the
 * first word, which then failed as "not an absolute path" — a confusing error
 * about a path the user never typed.
 * @param {string} rawInput - exact text after the command name.
 * @returns {{request: string, repository: string|undefined}}
 */
export function parseInput(rawInput) {
  let text = String(rawInput ?? '').trim()
  let repo
  const match = text.match(/(?:^|\s)--repo(?:=("([^"]*)"|'([^']*)'|(\S+))|\s+("([^"]*)"|'([^']*)'|(\S+)))/)
  if (match !== null) {
    const quoted = match[2] ?? match[3] ?? match[6] ?? match[7]
    repo = quoted !== undefined ? quoted : (match[4] ?? match[8])
    text = (text.slice(0, match.index) + text.slice(match.index + match[0].length))
      .replace(/\s{2,}/g, ' ')
      .trim()
  }
  return { request: text, repository: repo }
}

/**
 * Resolve the repository for a command invocation.
 *
 * A slash command runs outside a tool execution, so there is no `exec.cwd`:
 * the session's working directory is the answer, and `process.cwd()` is only a
 * fallback when the host gives no session directory at all.
 *
 * The session directory is allowed by construction — DSH already confines that
 * session to it — so `--repo` is for reaching *another* repository, not a
 * requirement for the one the person is standing in.
 * @param {object} ctx - command-scope context.
 * @param {object|undefined} agent - invoking agent.
 * @param {string|undefined} explicit - `--repo` value when the user supplied one.
 * @param {AbortSignal|undefined} signal - cancellation from the UI request.
 * @param {object} settings - live plugin settings, read at call time.
 * @param {Function|undefined} sessionDirectory - resolver shared with the tools.
 */
async function repositoryFor(ctx, agent, explicit, signal, settings, sessionDirectory) {
  const policy = {
    allowedRoots: settings.allowedRoots,
    includeSessionRoot: settings.includeSessionRoot,
  }
  const sessionRoot = typeof sessionDirectory === 'function'
    ? await sessionDirectory(ctx, agent, signal)
    : undefined
  if (typeof explicit === 'string' && explicit !== '') {
    return resolveRepository(explicit, { ...policy, sessionRoot })
  }
  const candidate = typeof sessionRoot === 'string' && sessionRoot !== ''
    ? sessionRoot
    : process.cwd()
  try {
    return resolveRepository(candidate, { ...policy, sessionRoot })
  } catch (error) {
    // Name the source of the path: the launcher's directory is not the
    // session's, and without that line the rejection reads as "my repo is
    // broken" instead of "this call looked at the wrong folder".
    if (candidate === process.cwd() && error instanceof InputError) {
      error.hint = (error.hint ? error.hint + '\n' : '')
        + 'Nguồn đường dẫn: thư mục của tiến trình DSH (' + candidate
        + '), không phải thư mục của phiên. Truyền --repo <đường dẫn tuyệt đối>.'
    }
    throw error
  }
}

/**
 * Build the command definition for one mount.
 * @param {object} options - plugin settings plus the resolved core.
 * @returns {object} a definition accepted by `ctx.commands.register()`.
 */
export function flowCommand({ ctx, settings, core, sessionDirectory }) {
  return {
    name: COMMAND_NAME,
    description: 'Dựng sơ đồ luồng hoặc bản đồ Project Flow Explainer toàn kho bằng --map, --refresh-map, --blueprint.',
    input: {
      hint: '<mô tả luồng> [--repo <đường dẫn tuyệt đối>]',
      attachments: false,
    },
    // The request text is what the person typed; keeping it in the session log
    // is the point — it is the record of what they asked for.
    recordInput: true,
    handler: async (invocation) => {
      const { agent, rawInput, signal } = invocation
      const { request, repository } = parseInput(rawInput)
      if (request === '') return { kind: 'error', text: 'Thiếu mô tả luồng.\n' + USAGE }
      const mapMode = new Map([['--map', 'build'], ['--refresh-map', 'refresh'], ['--blueprint', 'plan']]).get(request)
      let root
      let outputDirectory
      try {
        root = (await repositoryFor(ctx, agent, repository, signal, settings, sessionDirectory)).root
        if (!mapMode) outputDirectory = resolveArtifactRoot(root)
      } catch (error) {
        const code = error?.code ?? 'command_failed'
        const hint = error?.hint ? '\n' + error.hint : ''
        // A command runs where the *session* lives, which is often not a
        // repository at all. Say what to type next instead of only what failed:
        // the person who just typed a command wants the run, not a policy lesson.
        const nextStep = code === 'repository_outside_allowed_roots'
            || code === 'repository_not_found'
            || code === 'repository_not_directory'
          ? '\nCách sửa: thêm --repo <đường dẫn tuyệt đối tới repository>, '
            + 'hoặc mở phiên trong chính thư mục repository.'
          : ''
        return {
          kind: 'error',
          text: `${code}: ${error?.message ?? String(error)}${hint}${nextStep}`,
        }
      }
      if (signal?.aborted) return { kind: 'error', text: 'ABORTED: lệnh đã bị huỷ.' }
      if (mapMode) {
        try {
          const coreRoot = (typeof core === 'function' ? core() : core).root
          const script = path.join(coreRoot, 'scripts', 'project_map.mjs')
          if (!existsSync(script)) return { kind: 'error', text: 'map_core_missing: Gói core chưa chứa Project Flow Explainer.' }
          const run = await runCli({ pythonPath: process.execPath, coreRoot, script, args: [mapMode, root], signal,
            timeoutMs: settings.timeoutMs, maxOutputBytes: settings.maxOutputBytes })
          if (run.aborted || run.timedOut) return { kind: 'error', text: run.aborted ? 'ABORTED: Lệnh đã bị hủy.' : 'core_timeout: Dựng bản đồ vượt quá thời gian.' }
          const data = JSON.parse(run.stdout.trim())
          if (run.code !== 0 || data.status !== 'ok') return { kind: 'error', text: (data.code || 'map_failed') + ': ' + (data.message || 'Trình dựng báo lỗi.') }
          return { kind: 'success', text: ['Bản đồ Project Flow Explainer: ' + data.artifacts.html,
            data.counts.files + ' tệp · ' + data.counts.modules + ' nhóm cấp cao · ' + data.counts.routes + ' đường dẫn web',
            'Dữ liệu: ' + data.artifacts.graph + ' · Cấu hình: ' + data.artifacts.architecture,
            'Để bật thanh Hỏi, chạy node project-flow-explainer/serve.mjs --no-open tại thư mục kho mã.'].join('\n') }
        } catch { return { kind: 'error', text: 'map_failed: Trình dựng Project Flow Explainer không trả kết quả hợp lệ.' } }
      }
      let run
      try {
        run = await runCore({
          pythonPath: settings.pythonPath,
          coreRoot: (typeof core === 'function' ? core() : core).root,
          script: (typeof core === 'function' ? core() : core).script,
          repository: root,
          request,
          outputDirectory,
          signal,
          timeoutMs: settings.timeoutMs,
          maxOutputBytes: settings.maxOutputBytes,
        })
      } catch (error) {
        return { kind: 'error', text: `core_spawn_failed: ${error?.message ?? String(error)}` }
      }
      if (run.aborted) return { kind: 'error', text: 'ABORTED: core đã bị dừng theo lệnh huỷ.' }
      if (run.timedOut) {
        return {
          kind: 'error',
          text: `core_timeout: core vượt quá ${settings.timeoutMs} ms.\n`
            + 'Thu hẹp mô tả luồng, hoặc tăng config.timeoutMs.',
        }
      }
      const line = run.stdout.trim().split('\n').filter(Boolean).pop() ?? ''
      let payload
      try {
        payload = JSON.parse(line)
      } catch {
        const tail = run.stderr.trim().split('\n').slice(-2).join(' ').slice(0, 300)
        return { kind: 'error', text: `core_failed: core không trả JSON hợp lệ. ${tail}` }
      }
      if (payload.status === 'error') {
        return {
          kind: 'error',
          text: `${payload.code}: ${payload.message}${payload.hint ? '\n' + payload.hint : ''}`,
        }
      }
      const relative = (value) => {
        if (typeof value !== 'string' || value === '') return ''
        return path.relative(root, value).split(path.sep).join('/')
      }
      const counts = payload.counts ?? {}
      const lines = [
        `Sơ đồ: ${payload.flow_id}`,
        `${counts.verified ?? 0} bước đã kiểm chứng · ${counts.partial ?? 0} một phần · `
          + `${counts.inferred ?? 0} suy luận`,
        `Mở file: ${relative(payload.paths?.flow_html)}`,
        `Dữ liệu: ${relative(payload.paths?.flow_json)} · Giải thích: ${relative(payload.paths?.overview)}`,
      ]
      const related = Array.isArray(payload.related) ? payload.related.length : 0
      if (related > 0) lines.push(`Ngoài luồng: ${related} file chỉ khớp từ khoá`)
      const firstLimit = Array.isArray(payload.limits) ? payload.limits[0] : undefined
      if (firstLimit !== undefined) lines.push(`Giới hạn: ${firstLimit}`)
      if (Array.isArray(payload.warnings) && payload.warnings.length > 0) {
        lines.push(`Cảnh báo: ${payload.warnings[0]}`)
      }
      lines.push('Phân tích tĩnh: chưa chạy code của repository, không dùng network.')
      return { kind: 'success', text: lines.join('\n') }
    },
  }
}