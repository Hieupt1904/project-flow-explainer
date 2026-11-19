/**
 * Input validation for the knowledge tools.
 *
 * The runtime validates the JSON schema before execute(); these checks are the
 * second line of defence for a direct `execute()` call (tests, another plugin,
 * a future caller). Every rejection carries a stable code and a hint, and none
 * of them can surface a raw TypeError.
 */
import { InputError } from './paths.js'

export function assertObject(args, toolName) {
  if (args === undefined || args === null) {
    throw new InputError('invalid_arguments',
      `${toolName}: thiếu tham số (nhận được ${args === null ? 'null' : 'undefined'}).`,
      'Truyền object có repository_path và các trường bắt buộc.')
  }
  if (typeof args !== 'object' || Array.isArray(args)) {
    throw new InputError('invalid_arguments',
      `${toolName}: tham số phải là object, nhận được ${Array.isArray(args) ? 'array' : typeof args}.`,
      'Truyền object JSON.')
  }
  return args
}

/**
 * Reject keys the tool does not declare.
 *
 * `ToolsService.register()` does not validate arguments, so the declared
 * `additionalProperties: false` is not enforced by the runtime — only a caller
 * built on `defineTool` gets that for free. This plugin builds its definitions
 * by hand, so it enforces the same rule here. Unknown keys are a silent
 * misconfiguration (a typo like `repositry_path` otherwise looks like a missing
 * argument), so fail loudly with a stable code.
 * @param {object} args - already asserted object.
 * @param {string[]} allowed - declared parameter names.
 * @param {string} toolName - tool name for the message.
 * @returns {object} the same object.
 */
export function rejectUnknownKeys(args, allowed, toolName) {
  const unknown = Object.keys(args).filter((key) => !allowed.includes(key))
  if (unknown.length > 0) {
    throw new InputError('unknown_arguments',
      `${toolName}: tham số không được khai báo: ${unknown.join(', ')}.`,
      `Tham số hợp lệ: ${allowed.join(', ')}.`)
  }
  return args
}

export function requiredString(args, key, toolName, { allowEmpty = false } = {}) {
  const value = args[key]
  if (value === undefined || value === null) {
    throw new InputError(`${key}_missing`, `${toolName}: thiếu ${key}.`,
      `Truyền ${key} dạng chuỗi.`)
  }
  if (typeof value !== 'string') {
    throw new InputError(`${key}_invalid_type`,
      `${toolName}: ${key} phải là chuỗi, nhận được ${typeof value}.`,
      `Truyền ${key} dạng chuỗi.`)
  }
  const trimmed = value.trim()
  if (!allowEmpty && trimmed === '') {
    throw new InputError(`${key}_missing`, `${toolName}: ${key} rỗng.`,
      `Mô tả rõ nội dung cho ${key}.`)
  }
  return trimmed
}

export function optionalString(args, key, toolName) {
  const value = args[key]
  if (value === undefined || value === null) return undefined
  if (typeof value !== 'string') {
    throw new InputError(`${key}_invalid_type`,
      `${toolName}: ${key} phải là chuỗi, nhận được ${typeof value}.`,
      `Bỏ trống hoặc truyền ${key} dạng chuỗi.`)
  }
  return value
}

export function integerInRange(args, key, toolName, { min, max, fallback }) {
  const value = args[key]
  if (value === undefined || value === null) return fallback
  if (typeof value !== 'number' || !Number.isFinite(value) || !Number.isInteger(value)) {
    throw new InputError(`${key}_invalid_type`,
      `${toolName}: ${key} phải là số nguyên, nhận được ${typeof value}.`,
      `Truyền ${key} trong khoảng ${min}..${max}.`)
  }
  if (value < min || value > max) {
    throw new InputError(`${key}_out_of_range`,
      `${toolName}: ${key} phải trong khoảng ${min}..${max}, nhận được ${value}.`,
      `Dùng giá trị trong khoảng ${min}..${max}.`)
  }
  return value
}

export function booleanFlag(args, key, toolName, fallback = false) {
  const value = args[key]
  if (value === undefined || value === null) return fallback
  if (typeof value !== 'boolean') {
    throw new InputError(`${key}_invalid_type`,
      `${toolName}: ${key} phải là boolean, nhận được ${typeof value}.`,
      `Truyền ${key} là true hoặc false.`)
  }
  return value
}

export function stringArray(args, key, toolName, { max = 200 } = {}) {
  const value = args[key]
  if (value === undefined || value === null) return []
  if (!Array.isArray(value)) {
    throw new InputError(`${key}_invalid_type`,
      `${toolName}: ${key} phải là mảng chuỗi, nhận được ${typeof value}.`,
      `Truyền ${key} là mảng đường dẫn tương đối.`)
  }
  if (value.length > max) {
    throw new InputError(`${key}_too_many`,
      `${toolName}: ${key} có ${value.length} phần tử, tối đa ${max}.`,
      'Chia nhỏ lần phân tích.')
  }
  return value.map((item) => {
    if (typeof item !== 'string') {
      throw new InputError(`${key}_invalid_type`,
        `${toolName}: phần tử của ${key} phải là chuỗi.`,
        'Truyền đường dẫn tương đối trong repository.')
    }
    return item.trim()
  }).filter(Boolean)
}

export function enumValue(args, key, toolName, allowed, fallback) {
  const value = args[key]
  if (value === undefined || value === null) return fallback
  if (typeof value !== 'string' || !allowed.includes(value)) {
    throw new InputError(`${key}_invalid`,
      `${toolName}: ${key} phải là một trong ${allowed.join('|')}, nhận được ${String(value)}.`,
      `Chọn ${allowed.join(' hoặc ')}.`)
  }
  return value
}

export function filtersObject(args, toolName) {
  const value = args.filters
  if (value === undefined || value === null) return {}
  if (typeof value !== 'object' || Array.isArray(value)) {
    throw new InputError('filters_invalid_type',
      `${toolName}: filters phải là object.`,
      'Truyền filters: { language, kind, flow_id }.')
  }
  const output = {}
  for (const key of ['language', 'kind', 'flow_id']) {
    if (value[key] === undefined || value[key] === null) continue
    if (typeof value[key] !== 'string') {
      throw new InputError('filters_invalid_type',
        `${toolName}: filters.${key} phải là chuỗi.`, 'Truyền chuỗi.')
    }
    output[key] = value[key]
  }
  return output
}
