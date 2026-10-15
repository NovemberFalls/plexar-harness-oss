/** Chromium browser tools from the pinned Playwright MCP server. @module */

import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'
import { BrowserMcpConfig, mountSessionMcp, validateBrowserMcpConfig } from '@deepseek-ai/dsh-experimental-browser-use-runtime/mcp'

/** Cordis identity for the Playwright MCP browser provider. */
export const name = 'experimental-browser-use-playwright-mcp'

/** Services required for scoped MCP startup and prompt readiness checks. */
export const inject = ['browserUse', 'agents', 'tools', 'systemPrompt']

/** Fixed Chromium launch or existing-browser attachment settings. */
export type Config = BrowserMcpConfig

/** Validate the launch or attachment configuration before activation. */
export const Config: typeof BrowserMcpConfig = BrowserMcpConfig

/**
 * Expose Playwright's upstream tools in each live Session's scope.
 * The pinned npm server runs under the current Node executable; browser state is not persisted by DSH.
 * @param ctx - provider context supplying browser use, Agents, and tools.
 * @param config - validated browser choice and optional tool timeout.
 */
export function apply(ctx: Context, config: Config): void {
  validateBrowserMcpConfig(config)
  const { args, env } = playwrightMcpLaunch(config)
  mountSessionMcp(ctx, {
    name: 'playwright-mcp',
    exclusive: config.mode === 'attach',
    command: process.execPath,
    args,
    env,
    ...config.toolCallTimeoutMs === undefined ? {} : { toolCallTimeoutMs: config.toolCallTimeoutMs },
  })
}

/** Name of the upstream environment variable holding the CDP endpoint to attach to. */
export const CDP_ENDPOINT_ENV = 'PLAYWRIGHT_MCP_CDP_ENDPOINT'

/**
 * Server arguments and environment for one browser choice, run under `process.execPath`.
 * @param config - validated launch or attachment choice.
 * @param options.endpointInEnv - in attach mode, pass the endpoint as `PLAYWRIGHT_MCP_CDP_ENDPOINT` in the child
 *   environment instead of `--cdp-endpoint`, so process listings of other local users do not show it; default false.
 * @returns the pinned server entry plus its arguments, and the environment clearing upstream options.
 */
export function playwrightMcpLaunch(
  config: Config,
  options: { endpointInEnv?: boolean } = {},
): { args: string[]; env: Record<string, string> } {
  const cli = join(dirname(fileURLToPath(import.meta.resolve('@playwright/mcp/package.json'))), 'cli.js')
  // Upstream environment options can otherwise replace the configured browser
  // mode or import an unrelated profile. Empty values mean absent to its parser.
  const endpointInEnv = config.mode === 'attach' && options.endpointInEnv === true
  const env: Record<string, string> = Object.fromEntries(Object.keys(process.env)
    .filter(key => key.toUpperCase().startsWith('PLAYWRIGHT_MCP_'))
    .filter(key => !(endpointInEnv && key.toUpperCase() === CDP_ENDPOINT_ENV))
    .map(key => [key, '']))
  const args = [cli, '--browser', 'chromium']
  if (config.mode === 'attach') {
    if (endpointInEnv) {
      env[CDP_ENDPOINT_ENV] = config.endpoint
    } else {
      args.push('--cdp-endpoint', config.endpoint)
    }
  } else {
    args.push('--isolated')
    if (config.headless) args.push('--headless')
    if (config.executablePath !== undefined) args.push('--executable-path', config.executablePath)
  }
  return { args, env }
}
