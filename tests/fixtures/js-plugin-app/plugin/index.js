import { flowCommand } from './lib/command.js'

export const name = 'demo-plugin'
export const inject = ['commands']

export function apply(ctx, config = {}) {
  ctx.inject(['commands'], (scoped) => {
    scoped.commands.register(flowCommand({ name: '/demo' }))
  })
}
