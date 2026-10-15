/**
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// Forked from microsoft/playwright@b9a34ac7783a1b6c2e1dfff0c08ac744c048fa59 packages/playwright-core/src/tools/mcp/cdpRelay.ts.
// Plexar changes: the connect page belongs to the configured Plexar Browser Bridge extension; the server listens on
// 127.0.0.1 only; each /cdp and /extension path ends in a fresh 256-bit random token; /extension accepts
// only the configured extension origin and /cdp refuses any browser-page origin; the /extension token admits one handshake and
// expires when the connect wait ends; the extension wait takes an explicit
// timeout and reports a miss instead of throwing; the browser opener is injected; one extension connection serves
// many CDP clients, each owning its own tabs. The relay<->extension wire
// protocol (connect URL params mcpRelayUrl, client, protocolVersion, token; protocol v2 messages) is unchanged.
// CDP params and results are untyped JSON relayed between Playwright and the extension, so they stay `any`.

/**
 * WebSocket server that bridges Playwright CDP clients and one Plexar Browser Bridge extension connection.
 *
 * Endpoints (all on 127.0.0.1, each ending in its own random token):
 * - /cdp/<token> - full CDP interface for one Playwright client, created by `addClient`; single use
 * - /extension/<token> - extension connection; single use, and expired once the connect wait ends
 *
 * Every tab the extension reports belongs to one client: a tab the client created, a popup of a tab it owns, or
 * otherwise (the connect page's tab, a tab the person dragged into the group) the oldest connected client; with no
 * client connected the tab waits for the next one. A client sees only its own tabs, and its tabs close when it disconnects.
 * @module @plexar/dsh-plexar/browser-bridge/relay
 */

import { randomBytes } from 'node:crypto'
import { createServer } from 'node:http'
import type { IncomingMessage, Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { WebSocket, WebSocketServer } from 'ws'
import type { RawData } from 'ws'
import { Deferred, logUnhandledError } from './log.ts'
import { ExtensionProtocolV2 } from './relay-v2.ts'
import * as protocol from './protocol.ts'
import type { ExtensionCommandV2, ExtensionEventsV2, Tab } from './protocol.ts'
import type { CDPMessage } from './browser-model.ts'

/** Relay construction options. */
export interface CdpRelayOptions {
  /** Extension id whose connect page is opened and whose origin may use /extension. */
  extensionId: string
  /** Opens the connect page in the person's browser; rejects when no browser can be started. */
  openConnectPage: (url: string) => Promise<void>
}

/** One Playwright client's endpoint on a relay. */
export interface RelayClient {
  /** The CDP WebSocket endpoint; it carries the client's token. */
  endpoint: string
  /** Disconnect the client and close the tabs it owns. Idempotent. */
  close: () => void
}

interface CDPCommand {
  id: number
  sessionId?: string
  method: string
  params?: any
}

/** One Playwright client: its token path, its tab model, and the tabs it owns. */
interface CdpClient {
  readonly path: string
  readonly handler: ExtensionProtocolV2
  readonly tabs: Set<number>
  ws: WebSocket | null
  closed: boolean
}

const token = (): string => randomBytes(32).toString('base64url')

/** Relay between Playwright CDP clients and one extension connection. */
export class CdpRelayServer {
  private readonly _server: Server
  private readonly _wss: WebSocketServer
  private _wsHost = ''
  private readonly _extensionId: string
  private readonly _openConnectPage: (url: string) => Promise<void>
  private readonly _extensionPath: string
  /** Set by the first accepted /extension handshake or the end of the connect wait; later handshakes are refused. */
  private _extensionTokenSpent = false
  private _extensionConnection: ExtensionConnection | null = null
  private _extensionClosed = false
  private readonly _extensionConnectionPromise = new Deferred()
  /** Resolved by the extension's `extension.initialized`, after its initial tabs. */
  private readonly _extensionReady = new Deferred()
  /** Clients by CDP path, in creation order. */
  private readonly _clients = new Map<string, CdpClient>()
  private readonly _owners = new Map<number, CdpClient>()
  /** Tabs reported while no client was connected. */
  private _unclaimed: Tab[] = []

  /** @param options - extension identity and connect-page opener. */
  constructor(options: CdpRelayOptions) {
    this._extensionId = options.extensionId
    this._openConnectPage = options.openConnectPage
    this._extensionPath = `/extension/${token()}`

    void this._extensionConnectionPromise.catch(logUnhandledError)
    void this._extensionReady.catch(logUnhandledError)
    this._server = createServer((_request, response) => {
      response.statusCode = 404
      response.end()
    })
    this._wss = new WebSocketServer({ noServer: true })
    this._server.on('upgrade', (request, socket, head) => {
      const pathname = new URL(request.url ?? '/', 'http://127.0.0.1').pathname
      const client = this._clients.get(pathname)
      if (!this._allowed(pathname, client, request)) {
        socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n')
        return
      }
      this._wss.handleUpgrade(request, socket, head, (ws) => {
        if (client) this._handlePlaywrightConnection(client, ws)
        else this._handleExtensionConnection(ws)
      })
    })
  }

  private _allowed(pathname: string, client: CdpClient | undefined, request: IncomingMessage): boolean {
    const origin = request.headers.origin
    if (client) return origin === undefined && client.ws === null && !client.closed
    if (pathname === this._extensionPath) {
      if (this._extensionTokenSpent || origin !== `chrome-extension://${this._extensionId}`) return false
      this._extensionTokenSpent = true
      return true
    }
    return false
  }

  /** Listen on an ephemeral 127.0.0.1 port. */
  async start(): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      this._server.once('error', reject)
      this._server.listen(0, '127.0.0.1', () => {
        this._server.off('error', reject)
        resolve()
      })
    })
    this._wsHost = `ws://127.0.0.1:${this.address().port}`
  }

  /** @returns the bound address of a started relay. */
  address(): AddressInfo {
    return this._server.address() as AddressInfo
  }

  /** @returns the WebSocket endpoint the extension connects to. */
  extensionEndpoint(): string {
    return `${this._wsHost}${this._extensionPath}`
  }

  /** @returns whether the extension finished its handshake and has not disconnected since. */
  extensionConnected(): boolean {
    return this._extensionReady.isDone() && this._extensionConnection !== null && !this._extensionClosed
  }

  /**
   * The extension connect page for this relay.
   * @param clientName - name shown to the person on the connect page and in the tab group title.
   * @returns the chrome-extension:// connect URL carrying the relay endpoint.
   */
  connectUrl(clientName: string): string {
    const url = new URL(`chrome-extension://${this._extensionId}/connect.html`)
    url.searchParams.set('mcpRelayUrl', this.extensionEndpoint())
    url.searchParams.set('client', JSON.stringify({ name: clientName }))
    url.searchParams.set('protocolVersion', protocol.VERSION.toString())
    return url.toString()
  }

  /**
   * Open the connect page and wait for the extension to connect and finish its handshake.
   * @param clientName - name shown to the person on the connect page and in the tab group title.
   * @param timeoutMs - how long to wait for the extension.
   * @param signal - aborts the wait with its reason.
   * The /extension token expires when this wait ends, whatever the outcome.
   * @returns true once connected; false when the browser could not be opened, the extension
   *   did not connect in time, or it disconnected before its handshake.
   */
  async establishExtensionConnection(clientName: string, timeoutMs: number, signal?: AbortSignal): Promise<boolean> {
    signal?.throwIfAborted()
    try {
      await this._openConnectPage(this.connectUrl(clientName))
    } catch (error) {
      this._extensionTokenSpent = true
      logUnhandledError(error)
      return false
    }
    let timer: NodeJS.Timeout | undefined
    let onAbort: (() => void) | undefined
    const deadline = new Promise<false>((resolve, reject) => {
      timer = setTimeout(() => { resolve(false) }, timeoutMs)
      onAbort = () => { reject(signal?.reason) }
      signal?.addEventListener('abort', onAbort, { once: true })
    })
    const connected = (async () => {
      await this._extensionConnectionPromise
      await this._extensionReady
      return true as const
    })().catch(() => false as const)
    try {
      return await Promise.race([connected, deadline])
    } finally {
      clearTimeout(timer)
      this._extensionTokenSpent = true
      if (onAbort) signal?.removeEventListener('abort', onAbort)
    }
  }

  /**
   * Add a Playwright client with its own CDP endpoint and its own tabs.
   * @returns the client's endpoint and its disconnect.
   */
  addClient(): RelayClient {
    const path = `/cdp/${token()}`
    const handler = new ExtensionProtocolV2(async (method, params) => {
      if (!this._extensionConnection) throw new Error('Extension not connected')
      const result = await this._extensionConnection.send(method as keyof ExtensionCommandV2, params)
      // A tab the client creates is the client's before the extension reports anything about it.
      if (method === 'chrome.tabs.create' && typeof result?.id === 'number') this._claim(result.id, client)
      return result
    })
    const client: CdpClient = { path, handler, tabs: new Set(), ws: null, closed: false }
    this._clients.set(path, client)
    return { endpoint: `${this._wsHost}${path}`, close: () => { this._releaseClient(client) } }
  }

  /** Close every client and the extension connection, then the server. The extension closes the tabs it opened. */
  stop(): void {
    for (const client of [...this._clients.values()]) this._releaseClient(client, false)
    this._closeExtensionConnection('Server stopped')
    for (const client of this._wss.clients) client.terminate()
    this._wss.close()
    this._server.close()
    this._server.closeAllConnections()
  }

  private _handlePlaywrightConnection(client: CdpClient, ws: WebSocket): void {
    if (!this.extensionConnected()) {
      ws.close(1000, 'Extension not connected')
      return
    }
    client.ws = ws
    client.handler.connectOverCDP((msg) => { this._send(client, msg) })
    const unclaimed = this._unclaimed
    this._unclaimed = []
    for (const tab of unclaimed) this._deliverTab(tab, client)
    client.handler.handleExtensionEvent('extension.initialized', [])
    ws.on('message', (data: RawData) => {
      let message: CDPCommand
      try {
        message = JSON.parse(rawText(data)) as CDPCommand
      } catch (error) {
        // A malformed Playwright frame has no id to answer; drop it as upstream does.
        logUnhandledError(error)
        return
      }
      void this._handlePlaywrightMessage(client, message)
    })
    ws.on('close', () => { this._releaseClient(client) })
    ws.on('error', logUnhandledError)
  }

  /** Forget a client and, when `closeTabs`, close the tabs it owns. */
  private _releaseClient(client: CdpClient, closeTabs = true): void {
    if (client.closed) return
    client.closed = true
    this._clients.delete(client.path)
    if (client.ws?.readyState === WebSocket.OPEN) client.ws.close(1000, 'Client released')
    const tabs = [...client.tabs]
    for (const tabId of tabs) this._owners.delete(tabId)
    client.tabs.clear()
    if (closeTabs && tabs.length > 0 && this._extensionConnection && !this._extensionClosed)
      this._extensionConnection.send('chrome.tabs.remove', [tabs]).catch(logUnhandledError)
  }

  private _closeExtensionConnection(reason: string): void {
    this._extensionConnection?.close(reason)
    if (!this._extensionConnectionPromise.isDone()) this._extensionConnectionPromise.reject(new Error(reason))
    if (!this._extensionReady.isDone()) this._extensionReady.reject(new Error(reason))
  }

  private _handleExtensionConnection(ws: WebSocket): void {
    if (this._extensionConnection) {
      ws.close(1000, 'Another extension connection already established')
      return
    }
    this._extensionConnection = new ExtensionConnection(ws)
    this._extensionConnection.onclose = (reason) => {
      this._extensionClosed = true
      if (!this._extensionReady.isDone()) this._extensionReady.reject(new Error(`Extension disconnected before initialization: ${reason}`))
      // The extension closes the tabs it opened; the clients lose their browser.
      for (const client of [...this._clients.values()]) this._releaseClient(client, false)
    }
    this._extensionConnection.onmessage = (method, params) => { this._onExtensionEvent(method, params) }
    this._extensionConnectionPromise.resolve()
  }

  private _onExtensionEvent<M extends keyof ExtensionEventsV2>(method: M, params: ExtensionEventsV2[M]['params']): void {
    switch (method) {
      case 'extension.initialized':
        this._extensionReady.resolve()
        return
      case 'chrome.tabs.onCreated': {
        const [tab] = params as ExtensionEventsV2['chrome.tabs.onCreated']['params']
        if (tab.id === undefined) return
        const owner = this._owners.get(tab.id)
          ?? (tab.openerTabId === undefined ? undefined : this._owners.get(tab.openerTabId))
          ?? [...this._clients.values()].find(client => client.ws !== null)
        if (owner) this._deliverTab(tab, owner)
        else this._unclaimed.push(tab)
        return
      }
      case 'chrome.tabs.onRemoved': {
        const [tabId] = params as ExtensionEventsV2['chrome.tabs.onRemoved']['params']
        this._unclaimed = this._unclaimed.filter(tab => tab.id !== tabId)
        const owner = this._owners.get(tabId)
        this._owners.delete(tabId)
        owner?.tabs.delete(tabId)
        owner?.handler.handleExtensionEvent(method, params)
        return
      }
      case 'chrome.debugger.onEvent':
      case 'chrome.debugger.onDetach': {
        const [source] = params as ExtensionEventsV2['chrome.debugger.onDetach']['params']
        if (source.tabId !== undefined) this._owners.get(source.tabId)?.handler.handleExtensionEvent(method, params)
        return
      }
      default:
        // Events a newer extension adds have no handler here.
        return
    }
  }

  private _claim(tabId: number, client: CdpClient): void {
    this._owners.set(tabId, client)
    client.tabs.add(tabId)
  }

  private _deliverTab(tab: Tab, client: CdpClient): void {
    this._claim(tab.id!, client)
    client.handler.handleExtensionEvent('chrome.tabs.onCreated', [tab])
  }

  private async _handlePlaywrightMessage(client: CdpClient, message: CDPCommand): Promise<void> {
    const { id, sessionId, method, params } = message
    const session = sessionId === undefined ? {} : { sessionId }
    try {
      const result: unknown = await this._handleCDPCommand(client, method, params, sessionId)
      this._send(client, { id, ...session, result })
    } catch (error) {
      this._send(client, { id, ...session, error: { message: error instanceof Error ? error.message : String(error) } })
    }
  }

  private async _handleCDPCommand(client: CdpClient, method: string, params: any, sessionId: string | undefined): Promise<any> {
    switch (method) {
      case 'Browser.getVersion':
        return { protocolVersion: '1.3', product: 'Chrome/Extension-Bridge', userAgent: 'CDP-Bridge-Server/1.0.0' }
      case 'Browser.setDownloadBehavior':
        return {}
      default:
        break
    }
    const handled = await client.handler.handleCDPCommand(method, params, sessionId)
    if (handled) return handled.result
    return await client.handler.forwardToExtension(method, params, sessionId)
  }

  private _send(client: CdpClient, message: CDPMessage): void {
    if (client.ws?.readyState === WebSocket.OPEN) client.ws.send(JSON.stringify(message))
  }
}

function rawText(data: RawData): string {
  if (Array.isArray(data)) return Buffer.concat(data).toString()
  return (data instanceof ArrayBuffer ? Buffer.from(new Uint8Array(data)) : data).toString()
}

interface ExtensionResponse {
  id?: number
  method?: string
  params?: any
  result?: any
  error?: string
}

interface PendingCall {
  resolve: (result: any) => void
  reject: (error: Error) => void
  error: Error
}

class ExtensionConnection {
  private readonly _ws: WebSocket
  private readonly _callbacks = new Map<number, PendingCall>()
  private _lastId = 0

  onmessage?: <M extends keyof ExtensionEventsV2>(method: M, params: ExtensionEventsV2[M]['params']) => void
  onclose?: (reason: string) => void

  constructor(ws: WebSocket) {
    this._ws = ws
    this._ws.on('message', (data: RawData) => { this._onMessage(data) })
    this._ws.on('close', (_code: number, reason: Buffer) => { this._onClose(reason) })
    this._ws.on('error', () => { this._dispose() })
  }

  async send<M extends keyof ExtensionCommandV2>(method: M, params: ExtensionCommandV2[M]['params']): Promise<any> {
    if (this._ws.readyState !== WebSocket.OPEN) throw new Error(`Unexpected WebSocket state: ${this._ws.readyState}`)
    const id = ++this._lastId
    this._ws.send(JSON.stringify({ id, method, params }))
    const error = new Error(`Protocol error: ${method}`)
    return new Promise((resolve, reject) => {
      this._callbacks.set(id, { resolve, reject, error })
    })
  }

  close(message: string): void {
    if (this._ws.readyState === WebSocket.OPEN) this._ws.close(1000, message)
  }

  private _onMessage(event: RawData): void {
    let parsedJson: ExtensionResponse
    try {
      parsedJson = JSON.parse(rawText(event)) as ExtensionResponse
    } catch (error) {
      // Malformed JSON from the extension ends the connection, as upstream does.
      logUnhandledError(error)
      this._ws.close()
      return
    }
    try {
      this._handleParsedMessage(parsedJson)
    } catch (error) {
      // A failing event handler ends the connection, as upstream does.
      logUnhandledError(error)
      this._ws.close()
    }
  }

  private _handleParsedMessage(object: ExtensionResponse): void {
    const callback = object.id === undefined ? undefined : this._callbacks.get(object.id)
    if (object.id !== undefined && callback !== undefined) {
      this._callbacks.delete(object.id)
      if (object.error) {
        callback.error.message = object.error
        callback.reject(callback.error)
      } else {
        callback.resolve(object.result)
      }
    } else if (object.id === undefined && object.method !== undefined) {
      this.onmessage?.(object.method as keyof ExtensionEventsV2, object.params)
    }
  }

  private _onClose(reason: Buffer): void {
    this._dispose()
    this.onclose?.(reason.toString())
  }

  private _dispose(): void {
    for (const callback of this._callbacks.values()) callback.reject(new Error('WebSocket closed'))
    this._callbacks.clear()
  }
}
