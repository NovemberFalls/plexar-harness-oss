/**
 * `plexar-harness export`: print one session as plain text, `USER:` / `ASSISTANT:` turns, for
 * `plexar slice` and other readers. Reads the log through the harness's own frame scanner and
 * event codec, so format versions stay the harness's concern. Reference: docs/plexar/09-session-export.md.
 * Run through the tsx loader by `plexar-harness.mjs`; argv: `<session-id> [--tools]`.
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { zstdDecompressSync } from 'node:zlib'
import { scanZstdFrames } from '@deepseek-ai/dsh-session-persistence-jsonl/src/zstd.ts'
import { scanLog } from '@deepseek-ai/dsh-session-persistence-jsonl/src/format.ts'

/** Export text format version, printed as the first line so readers can refuse an unknown one. */
const EXPORT_VERSION = 'plexar-export-1'
const LOG_NAME = /^session\.v(\d+)\.jsonl(\.zstd)?$/

interface Block { type: string; text?: string; name?: string; arguments?: string }
interface LoggedEvent { type: string; data?: Record<string, unknown> }

/** Newest-generation log file for a session id, searched across every project folder. */
function findLog(sessionId: string): string {
  const root = join(process.env.DSH_HOME ?? join(homedir(), '.dsh'), 'sessions')
  for (const project of existsSync(root) ? readdirSync(root) : []) {
    const dir = join(root, project, sessionId)
    if (!existsSync(dir)) continue
    const logs = readdirSync(dir)
      .map(name => ({ name, match: LOG_NAME.exec(name) }))
      .filter(entry => entry.match !== null)
      .sort((a, b) => Number(b.match![1]) - Number(a.match![1]))
    if (logs.length > 0) return join(dir, logs[0].name)
  }
  throw new Error(`no session log for ${sessionId} under ${root}`)
}

function readEvents(path: string): LoggedEvent[] {
  let bytes = readFileSync(path)
  if (path.endsWith('.zstd')) {
    const { frames } = scanZstdFrames(bytes)
    bytes = Buffer.concat(frames.map(f => zstdDecompressSync(bytes.subarray(f.start, f.end))))
  }
  return scanLog(bytes).events.map(event => ({
    type: event.type,
    data: 'data' in event ? (event.data as Record<string, unknown>) : undefined,
  }))
}

function textOf(content: unknown): string {
  return Array.isArray(content)
    ? (content as Block[]).filter(b => b.type === 'text' && b.text).map(b => b.text).join('')
    : ''
}

/**
 * Render a session's events as transcript lines.
 * @param events - the session's durable events in log order.
 * @param tools - also print one `TOOL:` line per tool call and one `COMMAND:` line per harness slash command.
 * @returns the transcript, one blank line between turns.
 */
function render(events: LoggedEvent[], tools: boolean): string {
  const turns: string[] = []
  for (const event of events) {
    const data = event.data ?? {}
    if (event.type === 'user/message' && (data.source as { kind?: string } | undefined)?.kind === 'user') {
      const text = textOf(data.content).trim()
      if (text) turns.push(`USER: ${text}`)
    } else if (event.type === 'command/run' && tools) {
      turns.push(`COMMAND: /${String(data.name)}${data.args ? String(data.args) : ''}`)
    } else if (event.type === 'assistant/message') {
      const message = data.message as { content?: Block[] } | undefined
      const text = textOf(message?.content).trim()
      if (tools) {
        for (const block of message?.content ?? []) {
          if (block.type === 'tool-call') turns.push(`TOOL: ${block.name} ${block.arguments ?? ''}`)
        }
      }
      if (text) turns.push(`ASSISTANT: ${text}`)
    }
  }
  return turns.join('\n\n')
}

const [sessionId, ...flags] = process.argv.slice(2)
if (!sessionId) {
  process.stderr.write('usage: plexar-harness export <session-id> [--tools]\n')
  process.exit(2)
}
try {
  process.stdout.write(`# ${EXPORT_VERSION} session ${sessionId}\n\n${render(readEvents(findLog(sessionId)), flags.includes('--tools'))}\n`)
} catch (error) {
  process.stderr.write(`plexar-harness export: ${(error as Error).message}\n`)
  process.exit(1)
}
