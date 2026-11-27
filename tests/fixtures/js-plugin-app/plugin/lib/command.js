import { runCore } from './runner.js'

export function flowCommand(options) {
  return {
    name: options.name,
    async handler(arg) {
      return runCore(arg)
    },
  }
}
