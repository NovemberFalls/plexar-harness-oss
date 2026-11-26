import { describe, expect, it } from 'vitest'
import { clampWidth, computeColumns } from '../src/client/columns.ts'

describe('clampWidth', () => {
  it('clamps into the range and rounds', () => {
    expect(clampWidth(250.4, 240, 420)).toBe(250)
    expect(clampWidth(100, 240, 420)).toBe(240)
    expect(clampWidth(9999, 240, 420)).toBe(420)
  })
})

describe('computeColumns', () => {
  it('gives each edge column its preference when the center has enough room', () => {
    expect(computeColumns(1920, 280, 864)).toEqual({ sidebar: 280, center: 776, rightbar: 864 })
  })

  it('keeps only the left rail when both panels are closed', () => {
    expect(computeColumns(1920, 0, 0)).toEqual({ sidebar: 56, center: 1864, rightbar: 0 })
  })

  it('clamps sidebar preferences and limits the right panel to 70% of the frame', () => {
    expect(computeColumns(3000, 9999, 9999)).toEqual({ sidebar: 420, center: 480, rightbar: 2100 })
    expect(computeColumns(1920, 1, 1)).toEqual({ sidebar: 264, center: 1356, rightbar: 300 })
  })

  it.each([
    [1300, 280, 620, 400],
    [1100, 280, 420, 400],
    [1120, 420, 300, 400],
    [1119, 420, 0, 699],
    [1024, 420, 0, 604],
    [756, 0, 300, 400],
    [755, 0, 0, 699],
    [455, 0, 0, 399],
    [20, 0, 0, 0],
  ])('solves frame %i and sidebar %i to right %i and center %i', (viewport, sidebar, rightbar, center) => {
    expect(computeColumns(viewport, sidebar, 864)).toEqual({ sidebar: sidebar || 56, center, rightbar })
  })

  it('does not reduce the wide sidebar to keep a normal right panel open', () => {
    expect(computeColumns(1024, 420, 500)).toEqual({ sidebar: 420, center: 604, rightbar: 0 })
  })

  it('restores a still-open preference when the frame widens', () => {
    expect(computeColumns(1100, 280, 864).rightbar).toBe(420)
    expect(computeColumns(1920, 280, 864).rightbar).toBe(864)
  })

  it('leaves a closed right track closed when the frame widens', () => {
    expect(computeColumns(755, 0, 0).rightbar).toBe(0)
    expect(computeColumns(1920, 0, 0).rightbar).toBe(0)
  })
})

describe('computeColumns with the environment rail', () => {
  it('reserves the rail before the right column bids', () => {
    expect(computeColumns(1920, 280, 864, 56, 280)).toEqual({ sidebar: 280, center: 496, rightbar: 864, envbar: 280 })
    expect(computeColumns(1500, 280, 864, 56, 280)).toEqual({ sidebar: 280, center: 400, rightbar: 540, envbar: 280 })
  })

  it('takes the rail track when the right panel cannot fit beside it', () => {
    expect(computeColumns(1200, 280, 864, 56, 280)).toEqual({ sidebar: 280, center: 640, rightbar: 0, envbar: 280 })
  })

  it('gives the rail no track when the center would drop below its minimum, leaving the three-column solve', () => {
    expect(computeColumns(959, 280, 864, 56, 280)).toEqual(computeColumns(959, 280, 864))
    expect(computeColumns(960, 280, 0, 56, 280)).toEqual({ sidebar: 280, center: 400, rightbar: 0, envbar: 280 })
  })

  it('is the three-column solve exactly while hidden', () => {
    for (const viewport of [455, 1024, 1300, 1920]) {
      expect(computeColumns(viewport, 280, 864, 56, 0)).toEqual(computeColumns(viewport, 280, 864))
      expect(computeColumns(viewport, 280, 864, 56, 0)).not.toHaveProperty('envbar')
    }
  })
})
