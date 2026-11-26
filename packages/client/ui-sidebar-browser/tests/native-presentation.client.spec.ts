// @vitest-environment jsdom
/** A native pane paints above the DOM, so placement must follow the measured box in both directions. */
import { afterEach, expect, it, vi } from 'vitest'
import { NativePanePresentation } from '../src/client/native/NativePanePresentation.ts'
import { fakeEnvironment, nativeFixture, setBox } from './native-harness.client.ts'

const target = { kind: 'https' as const, url: 'https://example.test/', title: 'Example' }
const hidden = { x: 0, y: 0, width: 0, height: 0, visible: false }
const fixtures: ReturnType<typeof nativeFixture>[] = []
afterEach(async () => {
  for (const h of fixtures.splice(0)) await h.dispose()
  vi.restoreAllMocks()
})

async function shown() {
  const h = nativeFixture()
  fixtures.push(h)
  const unmount = h.mount()
  h.frame.loadUrl(target)
  await vi.waitFor(() => { expect(h.pending()).toBe(1) })
  return { h, unmount }
}

it('sends bounds on mount, coalesced per frame and not resent when unchanged', async () => {
  const { h } = await shown()
  h.observe()
  window.dispatchEvent(new Event('resize'))
  expect(h.pending()).toBe(1)
  h.flush()
  expect(h.bridge.setBounds.mock.calls).toEqual([['browser-pane-1', { x: 10, y: 20, width: 300, height: 400, visible: true }]])
  h.observe()
  document.dispatchEvent(new Event('scroll'))
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenCalledOnce()
  setBox(h.host, { x: 10, y: 60, width: 300, height: 360 })
  h.host.dispatchEvent(new Event('scroll'))
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenLastCalledWith('browser-pane-1', { x: 10, y: 60, width: 300, height: 360, visible: true })
})

it('hides the pane when a retained body is hidden and shows it again when it returns', async () => {
  const { h } = await shown()
  h.flush()
  // A hidden retained Sidebar body collapses to an empty box without unmounting.
  setBox(h.host, { x: 0, y: 0, width: 0, height: 0 })
  h.observe()
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenLastCalledWith('browser-pane-1', hidden)
  setBox(h.host, { x: 10, y: 20, width: 300, height: 400 })
  h.observe()
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenLastCalledWith('browser-pane-1', { x: 10, y: 20, width: 300, height: 400, visible: true })
  setBox(h.host, { x: 2000, y: 20, width: 300, height: 400 })
  h.observe()
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenLastCalledWith('browser-pane-1', hidden)
  setBox(h.host, { x: 10, y: 20, width: 300, height: 400 })
  h.host.remove()
  h.observe()
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenCalledTimes(4)
  document.body.append(h.host)
  h.observe()
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenCalledTimes(5)
  expect(h.bridge.setBounds).toHaveBeenLastCalledWith('browser-pane-1', { x: 10, y: 20, width: 300, height: 400, visible: true })
})

it('hides on unmount, stops tracking, and places the pane again on remount', async () => {
  const { h, unmount } = await shown()
  h.flush()
  unmount()
  expect(h.bridge.setBounds).toHaveBeenLastCalledWith('browser-pane-1', hidden)
  expect(h.observers.size).toBe(0)
  h.observe()
  window.dispatchEvent(new Event('resize'))
  expect(h.pending()).toBe(0)
  h.mount()
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenLastCalledWith('browser-pane-1', { x: 10, y: 20, width: 300, height: 400, visible: true })
  expect(h.bridge.open).toHaveBeenCalledOnce()
  await h.frame.dispose()
  expect(h.bridge.setBounds).toHaveBeenLastCalledWith('browser-pane-1', hidden)
  expect(h.observers.size).toBe(0)
})

it('sends nothing without a pane and works without observer support', () => {
  const observation = fakeEnvironment()
  const setBounds = vi.fn(async () => {})
  const presentation = new NativePanePresentation(setBounds, { mounted: vi.fn(), unmounted: vi.fn() },
    { ...observation.environment, ResizeObserver: undefined, IntersectionObserver: undefined })
  const host = document.createElement('div')
  host.id = 'native-presentation-bare'
  setBox(host, { x: 0, y: 0, width: 50, height: 50 })
  document.body.append(host)
  try {
    const unmount = presentation.mount(host.id)
    observation.flush()
    expect(setBounds).not.toHaveBeenCalled()
    presentation.setPane('browser-pane-3')
    observation.flush()
    expect(setBounds).toHaveBeenCalledExactlyOnceWith('browser-pane-3', { x: 0, y: 0, width: 50, height: 50, visible: true })
    unmount()
    expect(setBounds).toHaveBeenLastCalledWith('browser-pane-3', hidden)
    expect(() => presentation.mount('missing')).toThrow()
  } finally {
    host.remove()
  }
})

it('follows a position-only move on the next frame and sends nothing while still', async () => {
  const { h } = await shown()
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenCalledOnce()
  expect(h.pending()).toBe(1)
  h.flush()
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenCalledOnce()
  setBox(h.host, { x: 90, y: 20, width: 300, height: 400 })
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenLastCalledWith('browser-pane-1', { x: 90, y: 20, width: 300, height: 400, visible: true })
  expect(h.bridge.setBounds).toHaveBeenCalledTimes(2)
})

it('requests no frame after hide, unmount or dispose, and resumes when shown again', async () => {
  const { h, unmount } = await shown()
  h.flush()
  setBox(h.host, { x: 0, y: 0, width: 0, height: 0 })
  h.flush()
  expect(h.bridge.setBounds).toHaveBeenLastCalledWith('browser-pane-1', hidden)
  expect(h.pending()).toBe(0)
  setBox(h.host, { x: 10, y: 20, width: 300, height: 400 })
  h.observe()
  h.flush()
  expect(h.pending()).toBe(1)
  unmount()
  expect(h.pending()).toBe(0)
  h.mount()
  h.flush()
  expect(h.pending()).toBe(1)
  await h.frame.dispose()
  expect(h.pending()).toBe(0)
  h.observe()
  window.dispatchEvent(new Event('resize'))
  expect(h.pending()).toBe(0)
})
