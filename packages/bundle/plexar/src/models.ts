/**
 * Host service backing the generated `ctx.remote.plexarModels` namespace: the signed-in person's
 * full Plexar model roster (chat and classifier, serving and not), for the Models settings page.
 *
 * The launcher (`cli/plexar-harness.mjs`) sets `PLEXAR_HARNESS_ALL_MODELS` from `checkGate()`'s
 * `allModels` (the unfiltered `/api/harness/me` `models` array) before starting the Host; this
 * module parses and validates that once at load. It is a read of the same launch-time snapshot
 * `cordis.patch.yml`'s `llm-pi-ai` model list reads from `PLEXAR_HARNESS_MODELS`, not a live rig
 * call, so it carries no per-request cost and never blocks a session on network conditions.
 * @module @plexar/dsh-plexar/models
 */

import { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'

/** One model row projected for the settings page: only the fields it renders. */
export interface ModelRow {
  readonly id: string
  readonly name: string
  readonly serving: boolean
  readonly contextWindow: number | null
  readonly input: readonly string[] | null
}

/**
 * The signed-in person's Plexar model roster, split into chat models and classifiers.
 * `source` is `'unavailable'` when the launcher had no models to read (not signed in, the rig was
 * unreachable at launch, or the checkout predates this field), in which case both lists are empty.
 */
export interface PlexarModelsView {
  readonly source: 'plexar' | 'unavailable'
  readonly chat: readonly ModelRow[]
  readonly classifiers: readonly ModelRow[]
}

/** One `/api/harness/me` `models[]` entry, as far as this module reads it. */
interface RawModel {
  readonly id: unknown
  readonly kind: unknown
  readonly serving: unknown
  readonly name: unknown
  readonly context_window: unknown
  readonly input: unknown
}

/** Validate one parsed JSON value as a well-formed model entry; malformed entries are dropped. */
function readModel(entry: unknown): (RawModel & { readonly id: string; readonly kind: 'chat' | 'classifier'; readonly serving: boolean }) | undefined {
  if (typeof entry !== 'object' || entry === null) return undefined
  const raw = entry as RawModel
  if (typeof raw.id !== 'string' || raw.id.length === 0) return undefined
  if (raw.kind !== 'chat' && raw.kind !== 'classifier') return undefined
  if (typeof raw.serving !== 'boolean') return undefined
  return { ...raw, id: raw.id, kind: raw.kind, serving: raw.serving }
}

/** Project one validated model entry into its settings-page row. */
function toRow(model: NonNullable<ReturnType<typeof readModel>>): ModelRow {
  const name = typeof model.name === 'string' && model.name.length > 0 ? model.name : model.id
  const contextWindow = typeof model.context_window === 'number' ? model.context_window : null
  const input = Array.isArray(model.input) && model.input.every((v): v is string => typeof v === 'string') ? model.input : null
  return { id: model.id, name, serving: model.serving, contextWindow, input }
}

/** Chat models: serving first, then by name. */
function sortChat(rows: readonly ModelRow[]): ModelRow[] {
  return [...rows].sort((a, b) => (b.serving === a.serving ? a.name.localeCompare(b.name) : Number(b.serving) - Number(a.serving)))
}

/** Classifiers: by name. */
function sortClassifiers(rows: readonly ModelRow[]): ModelRow[] {
  return [...rows].sort((a, b) => a.name.localeCompare(b.name))
}

/**
 * Parse and validate `PLEXAR_HARNESS_ALL_MODELS` (JSON text, as `cli/auth.mjs`'s `checkGate()`
 * produces it) into a {@link PlexarModelsView}. Absent, unparsable, or non-array input, and each
 * malformed entry within an otherwise valid array, are dropped rather than thrown: a partial or
 * missing roster degrades the settings page to its empty state instead of failing Host load.
 * @param raw - `process.env['PLEXAR_HARNESS_ALL_MODELS']`, or any equivalent JSON text.
 * @returns the validated, sorted view.
 */
export function parseAllModels(raw: string | undefined): PlexarModelsView {
  if (raw === undefined) return { source: 'unavailable', chat: [], classifiers: [] }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch (error) {
    // Malformed launch-time env value: no readable roster, so the page shows its empty state.
    void error
    return { source: 'unavailable', chat: [], classifiers: [] }
  }
  if (!Array.isArray(parsed)) return { source: 'unavailable', chat: [], classifiers: [] }
  const models = parsed.map(readModel).filter((m): m is NonNullable<typeof m> => m !== undefined)
  if (models.length === 0) return { source: 'unavailable', chat: [], classifiers: [] }
  const chat = sortChat(models.filter(m => m.kind === 'chat').map(toRow))
  const classifiers = sortClassifiers(models.filter(m => m.kind === 'classifier').map(toRow))
  return { source: 'plexar', chat, classifiers }
}

/**
 * Host service backing the generated `ctx.remote.plexarModels` namespace: reports the model
 * roster parsed from `PLEXAR_HARNESS_ALL_MODELS` at load.
 */
export class PlexarModels extends TypertRemoteService {
  static inject: string[] = []

  static Config: z<Record<never, never>> = z.object({})

  private readonly view: PlexarModelsView

  /** @param ctx - Host context this service registers into. */
  constructor(ctx: Context) {
    super(ctx, 'plexarModels', { namespace: 'plexarModels' })
    this.view = parseAllModels(process.env['PLEXAR_HARNESS_ALL_MODELS'])
  }

  /**
   * Read the signed-in person's model roster.
   * @returns the roster parsed at Host load; it does not change over the Host's lifetime.
   */
  @Remote
  list(): Promise<PlexarModelsView> {
    return Promise.resolve(this.view)
  }
}

export default PlexarModels
