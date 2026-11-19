/**
 * Invoke the Python core as a child process.
 *
 * Contract: arguments are always passed as an array (never a shell string),
 * stdout carries one JSON object, stderr carries human diagnostics. The child
 * is killed on abort or timeout; it inherits a minimal environment.
 *
 * Two entry points share one implementation:
 *   runCli  - arbitrary subcommand args (index/search/context-pack/impact/...)
 *   runCore - the original flow call, kept for backward compatibility
 */
import { spawn } from 'node:child_process'

export const DEFAULT_MAX_OUTPUT = 1024 * 1024

class Capture {
  constructor(limit) {
    this.limit = limit
    this.chunks = []
    this.size = 0
    this.truncated = false
  }

  push(chunk) {
    if (this.size >= this.limit) {
      this.truncated = true
      return
    }
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk))
    const room = this.limit - this.size
    const slice = buffer.length > room ? buffer.subarray(0, room) : buffer
    if (slice.length < buffer.length) this.truncated = true
    this.chunks.push(slice)
    this.size += slice.length
  }

  text() {
    return Buffer.concat(this.chunks).toString('utf8')
  }
}

/**
 * Run one CLI subcommand.
 * @param {object} options
 * @param {string} options.pythonPath - interpreter.
 * @param {string} options.coreRoot - directory holding the core (cwd).
 * @param {string} options.script - absolute path of tools/pfe_cli.py.
 * @param {string[]} options.args - argv tail (subcommand + flags).
 * @param {AbortSignal} [options.signal] - caller cancellation.
 * @param {number} [options.timeoutMs] - cooperative budget.
 * @param {number} [options.maxOutputBytes] - capture cap per stream.
 */
export function runCli(options) {
  const {
    pythonPath, coreRoot, script, args, signal, timeoutMs, maxOutputBytes,
  } = options
  const argv = [script, ...args]
  const limit = Number.isFinite(maxOutputBytes) && maxOutputBytes > 0
    ? Math.floor(maxOutputBytes)
    : DEFAULT_MAX_OUTPUT
  const stdout = new Capture(limit)
  const stderr = new Capture(limit)

  return new Promise((resolve) => {
    let aborted = false
    let timedOut = false
    let settled = false

    const child = spawn(pythonPath, argv, {
      cwd: coreRoot,
      shell: false,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        PATH: process.env.PATH ?? '/usr/local/bin:/usr/bin:/bin',
        HOME: process.env.HOME ?? '',
        LANG: process.env.LANG ?? 'C.UTF-8',
        PYTHONIOENCODING: 'utf-8',
        PYTHONDONTWRITEBYTECODE: '1',
      },
    })

    const finish = (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      if (signal) signal.removeEventListener('abort', onAbort)
      resolve({
        code,
        stdout: stdout.text(),
        stderr: stderr.text(),
        timedOut,
        aborted,
        truncated: stdout.truncated || stderr.truncated,
        argv,
      })
    }

    const kill = () => {
      try {
        child.kill('SIGTERM')
      } catch {
        /* already gone */
      }
      const hard = setTimeout(() => {
        try {
          child.kill('SIGKILL')
        } catch {
          /* already gone */
        }
      }, 2000)
      hard.unref?.()
    }

    const onAbort = () => {
      aborted = true
      kill()
    }

    const timer = Number.isFinite(timeoutMs) && timeoutMs > 0
      ? setTimeout(() => {
        timedOut = true
        kill()
      }, Math.floor(timeoutMs))
      : null
    timer?.unref?.()

    if (signal) {
      if (signal.aborted) {
        aborted = true
        kill()
      } else {
        signal.addEventListener('abort', onAbort, { once: true })
      }
    }

    child.stdout.on('data', (chunk) => stdout.push(chunk))
    child.stderr.on('data', (chunk) => stderr.push(chunk))
    child.on('error', (error) => {
      stderr.push(`spawn_error: ${error?.message ?? error}\n`)
      finish(null)
    })
    child.on('close', (code, signalName) => {
      if (signalName && code === null && !aborted && !timedOut) {
        stderr.push(`terminated_by_signal: ${signalName}\n`)
      }
      finish(code)
    })
  })
}

/**
 * Run `build_flow.py --json` for one request (legacy shape, still used by the
 * flow tool so its behaviour and tests stay stable).
 */
export function runCore(options) {
  const {
    pythonPath, coreRoot, script, repository, request,
    outputDirectory, slug, signal, timeoutMs, maxOutputBytes,
  } = options

  const argv = [script, '--repo', repository, '--request', request, '--json']
  if (outputDirectory) argv.push('--out-dir', outputDirectory)
  if (slug) argv.push('--slug', slug)

  return runCli({
    pythonPath, coreRoot, script, args: argv.slice(1),
    signal, timeoutMs, maxOutputBytes,
  })
}
