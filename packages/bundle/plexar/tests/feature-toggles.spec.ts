/** Which tools the Features `off` setting hides. */

import { describe, expect, it } from 'vitest'
import { hiddenTools } from '../src/feature-toggles.ts'

const FEATURES = { shell: ['bash', 'pwsh'], files: ['read', 'write'], jobs: ['job_output', 'bash'] }

describe('hiddenTools', () => {
  it('hides nothing when every feature is on', () => {
    expect(hiddenTools(FEATURES, [])).toEqual({ tools: [], unknown: [] })
  })

  it('hides every tool of each off feature once', () => {
    expect(hiddenTools(FEATURES, ['shell', 'jobs']).tools).toEqual(['bash', 'pwsh', 'job_output'])
  })

  it('reports an off feature the configuration does not define', () => {
    expect(hiddenTools(FEATURES, ['voice', 'shell'])).toEqual({ tools: ['bash', 'pwsh'], unknown: ['voice'] })
  })
})
