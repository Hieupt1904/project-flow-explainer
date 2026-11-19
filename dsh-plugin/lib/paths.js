/**
 * Path, config and core-location policy for the adapter.
 *
 * Every rule here exists so the tool cannot read or write outside what the
 * profile explicitly allows, and so a package installed from a tarball can
 * still find its core.
 */
import { accessSync, constants, existsSync, lstatSync, realpathSync, statSync } from 'node:fs'
import path from 'node:path'

export const ARTIFACT_SUBPATH = path.join('artifacts', 'flows')

export class InputError extends Error {
  /**
   * @param {string} code - stable machine code, surfaced to the caller.
   * @param {string} message - what went wrong, in the user's language.
   * @param {string} [hint] - how to fix it.
   */
  constructor(code, message, hint) {
    super(message)
    this.name = 'InputError'
    this.code = code
    this.hint = hint || ''
  }
}

/** Return true when `target` is `root` itself or lives under it. */
export function isInside(root, target) {
  const relative = path.relative(path.resolve(root), path.resolve(target))
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative))
}

function canonicalExisting(input, label) {
  try {
    return realpathSync(input)
  } catch (error) {
    throw new InputError('path_unreadable', `Không đọc được ${label}: ${input}`,
      String(error?.message || error))
  }
}

/**
 * Canonicalize the configured roots; missing entries are dropped, but an
 * entirely unusable configuration is a hard error (deny-by-default).
 * @param {unknown} allowedRoots
 * @returns {string[]}
 */
export function resolveAllowedRoots(allowedRoots) {
  if (allowedRoots === undefined || allowedRoots === null) {
    throw new InputError(
      'allowed_roots_unconfigured',
      'Chưa cấu hình allowedRoots nên tool từ chối phân tích mọi đường dẫn.',
      'Thêm vào profile patch: config.allowedRoots: ["/duong/dan/workspace", ...]. '
      + 'Tool chỉ đọc repository nằm trong các root này.',
    )
  }
  if (!Array.isArray(allowedRoots)) {
    throw new InputError('allowed_roots_invalid', 'allowedRoots phải là mảng chuỗi đường dẫn.')
  }
  if (allowedRoots.length === 0) {
    throw new InputError(
      'allowed_roots_unconfigured',
      'allowedRoots rỗng nên tool từ chối phân tích mọi đường dẫn (deny-by-default).',
      'Khai báo ít nhất một thư mục gốc trong config.allowedRoots của profile patch.',
    )
  }
  const resolved = []
  for (const entry of allowedRoots) {
    if (typeof entry !== 'string' || entry.trim() === '') {
      throw new InputError('allowed_roots_invalid', 'allowedRoots chứa phần tử không phải chuỗi đường dẫn.')
    }
    if (!path.isAbsolute(entry)) {
      throw new InputError('allowed_roots_invalid',
        `allowedRoots phải là đường dẫn tuyệt đối: ${entry}`)
    }
    if (!existsSync(entry)) continue
    try {
      const stat = statSync(entry)
      if (!stat.isDirectory()) continue
      resolved.push(realpathSync(entry))
    } catch {
      /* unreadable entry: ignored, deny-by-default still holds */
    }
  }
  if (resolved.length === 0) {
    throw new InputError(
      'allowed_roots_unconfigured',
      'Không root nào trong allowedRoots tồn tại và đọc được.',
      `Đã cấu hình: ${JSON.stringify(allowedRoots)}`,
    )
  }
  return [...new Set(resolved)]
}

/**
 * Canonicalize a repository path and prove it is readable and allowed.
 * @param {unknown} input - caller-supplied path.
 * @param {{allowedRoots?: unknown}} options - profile configuration.
 * @returns {{root: string, allowedRoots: string[]}}
 */
export function resolveRepository(input, options = {}) {
  const allowedRoots = resolveAllowedRoots(options.allowedRoots)
  if (typeof input !== 'string' || input.trim() === '') {
    throw new InputError('repository_path_missing', 'Thiếu repository_path.',
      'Truyền đường dẫn tuyệt đối tới thư mục repository, ví dụ /home/ban/du-an.')
  }
  if (!path.isAbsolute(input)) {
    throw new InputError('repository_path_relative',
      `repository_path phải là đường dẫn tuyệt đối: ${input}`,
      'Dùng đường dẫn bắt đầu bằng / (không dùng ~ hoặc đường dẫn tương đối).')
  }
  if (!existsSync(input)) {
    throw new InputError('repository_not_found', `Không thấy thư mục repository: ${input}`,
      'Kiểm tra lại đường dẫn; tool không tự clone hay tải repository.')
  }
  const root = canonicalExisting(input, 'repository')
  let stat
  try {
    stat = statSync(root)
  } catch (error) {
    throw new InputError('repository_unreadable', `Không đọc được thư mục: ${root}`,
      String(error?.message || error))
  }
  if (!stat.isDirectory()) {
    throw new InputError('repository_not_directory', `Đường dẫn không phải thư mục: ${root}`)
  }
  try {
    accessSync(root, constants.R_OK | constants.X_OK)
  } catch {
    throw new InputError('repository_unreadable', `Không có quyền đọc thư mục: ${root}`)
  }
  const match = allowedRoots.find((allowed) => isInside(allowed, root))
  if (!match) {
    throw new InputError('repository_outside_allowed_roots',
      `repository_path nằm ngoài allowedRoots: ${root}`,
      `allowedRoots hiện tại: ${allowedRoots.join(', ')}`)
  }
  return { root, allowedRoots }
}

/**
 * The only accepted artifact root is `<repo>/artifacts/flows`; nothing else —
 * not the repo root, not src, not docs, not tmp, not a sibling directory.
 * @param {string} root - canonical repository root.
 * @param {unknown} outputDirectory - caller-supplied directory (absolute or repo-relative).
 * @returns {string}
 */
export function resolveArtifactRoot(root, outputDirectory) {
  const expected = path.join(root, ARTIFACT_SUBPATH)
  // A symlinked artifacts/ or flows/ would escape the repo after the prefix
  // check, so refuse it before looking at the caller's argument at all.
  let probe = root
  for (const part of ARTIFACT_SUBPATH.split(path.sep)) {
    probe = path.join(probe, part)
    let link = false
    try {
      link = lstatSync(probe).isSymbolicLink()
    } catch {
      link = false
    }
    if (link) {
      const target = realpathSync(probe)
      if (!isInside(root, target)) {
        throw new InputError('artifact_symlink_escape',
          `Thư mục artifact là symlink ra ngoài repository: ${probe} → ${target}`)
      }
    }
  }
  if (outputDirectory === undefined || outputDirectory === null || outputDirectory === '') {
    return expected
  }
  if (typeof outputDirectory !== 'string' || outputDirectory.includes('\0')) {
    throw new InputError('invalid_artifact_root', 'output_directory không hợp lệ.',
      `Chỉ chấp nhận ${ARTIFACT_SUBPATH}.`)
  }
  const candidate = path.isAbsolute(outputDirectory)
    ? outputDirectory
    : path.join(root, outputDirectory)
  const normalised = path.resolve(candidate)
  const expectedReal = existsSync(expected) ? realpathSync(expected) : expected
  const candidateReal = existsSync(normalised) ? realpathSync(normalised) : normalised
  if (candidateReal !== expectedReal) {
    throw new InputError('invalid_artifact_root',
      `output_directory không hợp lệ: ${outputDirectory}`,
      `Artifact chỉ được ghi vào ${ARTIFACT_SUBPATH} trong repository đã duyệt; `
      + 'không chấp nhận repo root, src, docs, tmp hay thư mục ngoài repo.')
  }
  return expected
}

/**
 * Find the core: explicit config → env → bundled vendor copy → dev checkout.
 * A packaged install (tarball) only has the vendor copy, so the parent
 * directory is a convenience for development, never an assumption.
 * @param {{coreRoot?: string, packageRoot: string, env?: NodeJS.ProcessEnv}} options
 * @returns {{root: string, script: string, source: string}}
 */
export function resolveCoreRoot({ coreRoot, packageRoot, env = process.env }) {
  const candidates = []
  if (typeof coreRoot === 'string' && coreRoot.trim() !== '') {
    const configured = path.resolve(coreRoot)
    const script = path.join(configured, 'scripts', 'build_flow.py')
    const template = path.join(configured, 'assets', 'workflow_template.html')
    if (!existsSync(script) || !existsSync(template)) {
      // An explicit coreRoot that is wrong is a configuration bug: fail loudly
      // instead of silently falling back to another copy.
      throw new InputError('core_not_found',
        `config.coreRoot không chứa core hợp lệ: ${configured}`,
        'Cần có scripts/build_flow.py và assets/workflow_template.html trong thư mục này.')
    }
    return { root: configured, script, source: 'config' }
  }
  if (typeof env.PFE_CORE_ROOT === 'string' && env.PFE_CORE_ROOT.trim() !== '') {
    candidates.push({ root: path.resolve(env.PFE_CORE_ROOT), source: 'env' })
  }
  candidates.push({ root: path.join(packageRoot, 'vendor', 'core'), source: 'vendor' })
  candidates.push({ root: path.resolve(packageRoot, '..'), source: 'checkout' })
  for (const candidate of candidates) {
    const script = path.join(candidate.root, 'scripts', 'build_flow.py')
    const template = path.join(candidate.root, 'assets', 'workflow_template.html')
    if (existsSync(script) && existsSync(template)) {
      return { ...candidate, script }
    }
  }
  throw new InputError(
    'core_not_found',
    'Không tìm thấy core (scripts/build_flow.py + assets/workflow_template.html).',
    `Đã thử: ${candidates.map((item) => `${item.root} (${item.source})`).join(', ')}. `
    + 'Cài bundle đã pack (có vendor/core) hoặc đặt config.coreRoot trỏ tới checkout của repo.',
  )
}
