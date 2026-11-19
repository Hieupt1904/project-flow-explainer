/**
 * Path policy for the adapter.
 *
 * The core enforces the same rules in Python; this module exists so a bad
 * argument fails before any process starts, and so a deployment can pin the
 * roots it is willing to read.
 */
import { existsSync, realpathSync, statSync, accessSync, constants } from 'node:fs'
import path from 'node:path'

export class InputError extends Error {
  constructor(message, hint) {
    super(message)
    this.name = 'InputError'
    this.hint = hint || ''
  }
}

/** Return true when `target` is `root` itself or lives under it. */
export function isInside(root, target) {
  const relative = path.relative(path.resolve(root), path.resolve(target))
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative))
}

/**
 * Canonicalize a repository path and prove it is readable and allowed.
 * @param {unknown} input - caller-supplied path.
 * @param {{allowedRoots?: string[]}} [options] - deployment pin; empty means any readable path.
 * @returns {{root: string, display: string}}
 */
export function resolveRepository(input, options = {}) {
  if (typeof input !== 'string' || input.trim() === '') {
    throw new InputError(
      'Thiếu repository_path.',
      'Truyền đường dẫn tuyệt đối tới thư mục repository, ví dụ /home/ban/du-an.',
    )
  }
  if (!path.isAbsolute(input)) {
    throw new InputError(
      `repository_path phải là đường dẫn tuyệt đối: ${input}`,
      'Dùng đường dẫn bắt đầu bằng / (không dùng ~ hoặc đường dẫn tương đối).',
    )
  }
  if (!existsSync(input)) {
    throw new InputError(
      `Không thấy thư mục repository: ${input}`,
      'Kiểm tra lại đường dẫn; tool không tự clone hay tải repository.',
    )
  }
  let root
  try {
    root = realpathSync(input)
  } catch (error) {
    throw new InputError(`Không đọc được đường dẫn: ${input}`, String(error?.message || error))
  }
  let stat
  try {
    stat = statSync(root)
  } catch (error) {
    throw new InputError(`Không đọc được thư mục: ${root}`, String(error?.message || error))
  }
  if (!stat.isDirectory()) {
    throw new InputError(`Đường dẫn không phải thư mục: ${root}`)
  }
  try {
    accessSync(root, constants.R_OK | constants.X_OK)
  } catch {
    throw new InputError(`Không có quyền đọc thư mục: ${root}`)
  }
  const allowed = Array.isArray(options.allowedRoots) ? options.allowedRoots.filter(Boolean) : []
  if (allowed.length > 0) {
    const match = allowed.find((entry) => {
      try {
        return isInside(realpathSync(entry), root)
      } catch {
        return false
      }
    })
    if (!match) {
      throw new InputError(
        `repository_path nằm ngoài phạm vi được phép: ${root}`,
        `Profile này chỉ cho phép: ${allowed.join(', ')}`,
      )
    }
  }
  return { root, display: root }
}

/**
 * Artifacts must stay inside the analysed repository. Returns the absolute
 * candidate directory; the core creates and re-checks it.
 * @param {string} root - canonical repository root.
 * @param {unknown} outputDirectory - caller-supplied directory (absolute or repo-relative).
 */
export function resolveArtifactRoot(root, outputDirectory) {
  if (outputDirectory === undefined || outputDirectory === null || outputDirectory === '') {
    return undefined
  }
  if (typeof outputDirectory !== 'string') {
    throw new InputError('output_directory phải là chuỗi đường dẫn.')
  }
  if (outputDirectory.includes('\0')) {
    throw new InputError('output_directory chứa ký tự không hợp lệ.')
  }
  const candidate = path.isAbsolute(outputDirectory)
    ? outputDirectory
    : path.join(root, outputDirectory)
  const normalised = path.resolve(candidate)
  if (!isInside(root, normalised)) {
    throw new InputError(
      `output_directory phải nằm trong repository đã duyệt: ${outputDirectory}`,
      `Artifact chỉ được ghi dưới ${path.join(root, 'artifacts')}.`,
    )
  }
  return normalised
}

/** Locate the core repository that owns scripts/build_flow.py. */
export function resolveCoreRoot(candidate) {
  const roots = []
  if (candidate) roots.push(path.resolve(candidate))
  if (roots.length === 0) {
    throw new InputError(
      'Không xác định được coreRoot.',
      'Cấu hình coreRoot trong profile patch trỏ tới thư mục chứa scripts/build_flow.py.',
    )
  }
  for (const root of roots) {
    const script = path.join(root, 'scripts', 'build_flow.py')
    if (existsSync(script)) return { root, script }
  }
  throw new InputError(
    `Không thấy scripts/build_flow.py trong: ${roots.join(', ')}`,
    'Kiểm tra coreRoot trong cordis.patch.yml của profile.',
  )
}
