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
import { runCore } from './core-runner.js'
import {
  InputError, resolveArtifactRoot, resolveRepository,
} from './paths.js'

export const COMMAND_NAME = 'project-flow-explainer'

const USAGE = 'Cách dùng: /project-flow-explainer <mô tả luồng>'
  + '\nVí dụ: /project-flow-explainer từ lúc bấm xuất báo cáo đến khi nhận được file'
  + '\nThiếu gì: cần repository hiện tại nằm trong allowedRoots của plugin.'

/** Split `<request>` from optional `--repo <path>` so a person can target another repo. */
function parseInput(rawInput) {
  let text = String(rawInput ?? '').trim()
  let repo
  const match = text.match(/(?:^|\s)--repo(?:=|\s+)(\S+)/)
  if (match !== null) {
    repo = match[1]
    text = (text.slice(0, match.index) + text.slice(match.index + match[0].length)).trim()
  }
  return { request: text, repository: repo }
}

/**
 * Resolve the repository for a command invocation.
 *
 * A slash command runs outside a tool execution, so there is no `exec.cwd`. The
 * session's working directory is the closest honest answer; `process.cwd()` is
 * only a fallback and is never treated as a repository without passing the same
 * allowed-roots policy the tools use.
 * @param {object} ctx - plugin context (for the working-directory service).
 * @param {object|undefined} agent - invoking agent.
 * @param {string|undefined} explicit - `--repo` value when the user supplied one.
 * @param {AbortSignal|undefined} signal - cancellation from the UI request.
 * @param {object} settings - live plugin settings, read at call time.
 */
async function repositoryFor(ctx, agent, explicit, signal, settings) {
  const allowedRoots = settings.allowedRoots
  if (typeof explicit === 'string' && explicit !== '') {
    return resolveRepository(explicit, { allowedRoots })
  }
  let candidate
  try {
    if (agent !== undefined && typeof ctx.workingDirectory?.ensure === 'function') {
      candidate = await ctx.workingDirectory.ensure(agent, signal)
    }
  } catch {
    candidate = undefined
  }
  if (typeof candidate !== 'string' || candidate === '') candidate = process.cwd()
  return resolveRepository(candidate, { allowedRoots })
}

/**
 * Build the command definition for one mount.
 * @param {object} options - plugin settings plus the resolved core.
 * @returns {object} a definition accepted by `ctx.commands.register()`.
 */
export function flowCommand({ ctx, settings, core }) {
  return {
    name: COMMAND_NAME,
    description: 'Dựng sơ đồ luồng từ repository hiện tại: flow.html mở offline + flow.json + overview.md',
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
      let root
      let outputDirectory
      try {
        root = (await repositoryFor(ctx, agent, repository, signal, settings)).root
        outputDirectory = resolveArtifactRoot(root)
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
      let run
      try {
        run = await runCore({
          pythonPath: settings.pythonPath,
          coreRoot: core.root,
          script: core.script,
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
