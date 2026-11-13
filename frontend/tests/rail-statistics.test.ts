import { describe, expect, it } from 'vitest'
import { operatingRailLength } from '../server/utils/rail-statistics'
import { distance } from '../shared/utils/train-position'
import type { RailwayFeature } from '../shared/types/railway'

describe('operating rail length', () => {
  it('sums operating LineString and MultiLineString segments without joining separate lines', () => {
    const features = [
      { properties: { mnemo: 'EXPLOITE' }, geometry: { type: 'LineString', coordinates: [[0, 0], [0.01, 0], [0.02, 0]] } },
      { properties: { mnemo: 'EXPLOITE' }, geometry: { type: 'MultiLineString', coordinates: [[[1, 1], [1.01, 1]], [[2, 2], [2.01, 2]]] } },
      { properties: { mnemo: 'FERME' }, geometry: { type: 'LineString', coordinates: [[0, 0], [3, 0]] } },
    ] as RailwayFeature[]
    const expected = distance([0, 0], [0.01, 0]) + distance([0.01, 0], [0.02, 0])
      + distance([1, 1], [1.01, 1]) + distance([2, 2], [2.01, 2])
    expect(operatingRailLength(features)).toBeCloseTo(expected, 6)
    expect(operatingRailLength([])).toBe(0)
  })
})
