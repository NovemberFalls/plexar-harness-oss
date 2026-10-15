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

import React, { useCallback, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'

type Status =
  | { type: 'connecting'; message: string }
  | { type: 'connected'; message: string }
  | { type: 'error'; message: string }
  | { type: 'error'; versionMismatch: { extensionVersion: string } }

const SUPPORTED_PROTOCOL_VERSION = 2

// Client name comes from the URL and never changes for the lifetime of this page.
const clientInfo = (() => {
  try {
    return JSON.parse(new URLSearchParams(window.location.search).get('client') || '{}').name || 'unknown'
  } catch {
    return 'unknown'
  }
})()

const ConnectApp: React.FC = () => {
  const [status, setStatus] = useState<Status | null>(null)

  const setError = useCallback((message: string) => {
    setStatus({ type: 'error', message })
  }, [])

  useEffect(() => {
    const runAsync = async () => {
      const params = new URLSearchParams(window.location.search)
      const relayUrl = params.get('mcpRelayUrl')

      if (!relayUrl) {
        setError('Missing mcpRelayUrl parameter in URL.')
        return
      }

      try {
        const host = new URL(relayUrl).hostname
        if (host !== '127.0.0.1' && host !== '[::1]') {
          setError(`Plexar Browser Bridge only allows loopback connections (127.0.0.1 or [::1]). Received host: ${host}`)
          return
        }
      } catch (e) {
        setError(`Invalid mcpRelayUrl parameter in URL: ${relayUrl}. ${e}`)
        return
      }

      setStatus({
        type: 'connecting',
        message: `Connecting "${clientInfo}"…`,
      })

      const parsedVersion = parseInt(params.get('protocolVersion') ?? '', 10)
      const requestedVersion = isNaN(parsedVersion) ? 1 : parsedVersion
      if (requestedVersion > SUPPORTED_PROTOCOL_VERSION) {
        const extensionVersion = chrome.runtime.getManifest().version
        setStatus({
          type: 'error',
          versionMismatch: {
            extensionVersion,
          },
        })
        return
      }
      if (requestedVersion < SUPPORTED_PROTOCOL_VERSION) {
        setError('The client uses an unsupported protocol version. Update Plexar Harness to the latest version.')
        return
      }
      // Plexar change: no approval step. The relay is loopback-only (checked above) and this page
      // cannot be opened by websites (no web_accessible_resources), so the connection starts at once
      // and this page's own tab becomes the agent's first tab in the Plexar group. The person's other
      // tabs are reachable only if they drag them into that group.
      await chrome.runtime.sendMessage({ type: 'connectionRequested', mcpRelayUrl: relayUrl })
      await handleConnectToTab()
    }
    void runAsync()
    // Ping the background every 20s so the MV3 service worker (which holds the
    // pending connection state) stays above its 30s idle timeout.
    const keepalive = setInterval(() => {
      chrome.runtime.sendMessage({ type: 'keepalive' }).catch(() => {})
    }, 20_000)
    return () => clearInterval(keepalive)
  }, [])

  const handleConnectToTab = useCallback(async () => {
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'connectToTab',
        clientName: clientInfo,
      })

      if (response?.success) {
        setStatus({ type: 'connected', message: `"${clientInfo}" is working in this tab. Your other tabs are not shared.` })
      } else {
        // Plexar change: the client gave up or exited before the connection; its connect page closes with it.
        window.close()
      }
    } catch {
      // The background worker could not reach the client's relay; the same applies.
      window.close()
    }
  }, [])

  return (
    <div className='app-container'>
      <div className='content-wrapper'>
        {status && (
          <div className='status-container'>
            <StatusBanner status={status} />
          </div>
        )}

      </div>
    </div>
  )
}

const VersionMismatchError: React.FC<{ extensionVersion: string }> = ({ extensionVersion }) => {
  const readmeUrl = 'https://plexar.tech/harness/browser'
  return (
    <div>
      Plexar Harness requires a newer Plexar Browser Bridge version (current version: {extensionVersion}).{' '}
      See <a href={readmeUrl} target='_blank' rel='noopener noreferrer'>installation instructions</a> for how to update.
    </div>
  )
}

const StatusBanner: React.FC<{ status: Status }> = ({ status }) => {
  return (
    <div className={`status-banner ${status.type}`}>
      {'versionMismatch' in status ? (
        <VersionMismatchError
          extensionVersion={status.versionMismatch.extensionVersion}
        />
      ) : (
        status.message
      )}
    </div>
  )
}

// Initialize the React app
const container = document.getElementById('root')
if (container) {
  const root = createRoot(container)
  root.render(<ConnectApp />)
}
