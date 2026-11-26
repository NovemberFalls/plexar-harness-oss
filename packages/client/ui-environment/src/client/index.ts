/**
 * Environment rail plugin, browser half: occupies the frame's `envbar` column
 * with the rail, puts its show/hide toggle in the conversation header, and
 * restores the viewer's remembered choice on start. The rail's body is a
 * `session-maybe` child of the rail, so it follows the current Session.
 *
 * Jobs and Workspaces are read through optional services: a profile without
 * either still renders the rail, with those sections empty. The Branch section
 * asks this package's Host half, and reads any failure as no branch.
 */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { HostObservable } from '@deepseek-ai/dsh-client-ui-slots'
// Type-only: the ctx.remote merge, including this package's own namespace.
import type { ClientRemote } from '@deepseek-ai/dsh-api-remotes/client'
// Type-only: the ctx.jobs and ctx.workspaces service merges.
import type {} from '@deepseek-ai/dsh-api-job-controller/client'
import type {} from '@deepseek-ai/dsh-api-workspace-controller/client'
// Type-only: the ctx.locale, ctx.slots and ctx.layout merges, and the header seat.
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import type {} from '@deepseek-ai/dsh-client-ui-layout/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import {
  EnvironmentPanel, EnvironmentRail, EnvironmentToggle,
  type EnvironmentPanelInjected, type EnvironmentRailInjected, type EnvironmentToggleInjected,
} from './EnvironmentRail.tsx'
import { RailState } from './rail-state.ts'
import { en, NS, zh, type EnvironmentKey } from './locales.ts'

export type {
  EnvironmentPanelInjected, EnvironmentPanelProps, EnvironmentRailInjected, EnvironmentRailProps,
  EnvironmentToggleInjected, EnvironmentToggleProps,
} from './EnvironmentRail.tsx'
export type { EnvironmentKey } from './locales.ts'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface SlotMap {
    /**
     * The environment rail's body, bound to the current Session when there is
     * one. Declared by this package's `envbar` entry, so it exists while the
     * rail is mounted. OCCUPIED by the rail's own panel.
     */
    'envbar.session': { kind: 'single'; scope: 'session-maybe' }
  }

  interface LocaleNamespaceMap {
    /** Environment rail copy. */
    'environment': EnvironmentKey
  }
}

/** Required services; jobs, workspaces and this package's Remote namespace are optional. */
export const inject = ['slots', 'locale', 'layout', 'remote']

/**
 * A source over a service that may be absent: absence reads as undefined and
 * subscribes to nothing.
 * @param read - looks the service's source up at call time.
 * @returns a stable source the renderer can bind once.
 */
function optionalSource<T>(read: () => HostObservable<T> | undefined): HostObservable<T | undefined> {
  return {
    getSnapshot: () => read()?.getSnapshot(),
    subscribe: listener => read()?.subscribe(listener) ?? (() => {}),
  }
}

/**
 * Client plugin body: dictionaries, the remembered choice, the rail with its
 * Session-bound body, and the header toggle.
 * @param ctx - client root context.
 */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'ui-environment: dictionaries')
  const rail = new RailState(ctx.layout)
  rail.restore()

  const readBranch = async (sessionId: SessionId): Promise<string | null> => {
    try {
      // Read as an optional service: a declared `ctx.remote.environmentRail`
      // would hold the whole rail back in a profile without the Host half.
      const remote = ctx.get('remote.environmentRail') as ClientRemote['environmentRail'] | undefined
      if (remote === undefined) return null
      const result = await remote.branch(sessionId)
      return result.ok ? result.value.branch : null
    } catch (_unavailable) {
      // The Host half is absent from this profile, or the call failed.
      return null
    }
  }
  const railInjected: EnvironmentRailInjected = { close: () => { rail.close() } }
  const panelInjected: EnvironmentPanelInjected = {
    hooks: {
      railShown: rail.shown,
      workspaceList: optionalSource(() => ctx.get('workspaces')?.list),
      jobRows: optionalSource(() => ctx.get('jobs')?.state),
    },
    watchRows: sessionId => ctx.get('jobs')?.watchRows(sessionId) ?? (() => {}),
    readBranch,
  }
  const toggleInjected: EnvironmentToggleInjected = {
    hooks: { railShown: rail.shown },
    toggle: () => { rail.toggle() },
  }

  ctx.slots.inject('envbar', function* () {
    yield ctx.slots.register({
      name: 'envbar',
      locale: NS,
      children: { 'envbar.session': { kind: 'single', scope: 'session-maybe' } },
      inject: () => railInjected,
    }, EnvironmentRail)
    yield ctx.slots.register({
      name: 'envbar.session',
      locale: NS,
      inject: () => panelInjected,
    }, EnvironmentPanel)
  })
  ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register({
    name: 'conversation.session.header.actions',
    id: 'environment',
    // After the job list (20) and the subagent catalog (30): a view control
    // reads after the Session's own activity.
    order: 40,
    locale: NS,
    inject: () => toggleInjected,
  }, EnvironmentToggle))
}
