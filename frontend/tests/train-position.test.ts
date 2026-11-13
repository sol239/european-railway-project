import { describe, expect, it } from 'vitest'
import { distance, railRouter, samplePath, trainLeg } from '../shared/utils/train-position'
import type { ScheduledTrain } from '../shared/types/train'
import type { RailwayFeature } from '../shared/types/railway'
const stop = (station: number, arrival: number, departure: number) => ({ station, arrival, departure, name: String(station), longitude: station, latitude: 0 })
const train: ScheduledTrain = { id: 't', name: 'Train', stops: [stop(0, 0, 100), stop(1, 200, 250), stop(2, 350, 350)] }
describe('scheduled train progress', () => {
  it('interpolates between stops and holds at a scheduled dwell', () => {
    expect(trainLeg(train, 99)).toBeNull()
    expect(trainLeg(train, 150)?.progress).toBe(0.5)
    expect(trainLeg(train, 225)?.progress).toBe(1)
    expect(trainLeg(train, 300)?.progress).toBe(0.5)
    expect(trainLeg(train, 351)).toBeNull()
  })
  it('samples distance along bends and clamps trailing wagons at the start', () => {
    const path: [number, number][] = [[0, 0], [1, 0], [1, 1]]
    expect(samplePath(path, distance(path[0]!, path[1]!)*1.5).point[0]).toBe(1)
    expect(samplePath(path, -30).point).toEqual([0, 0])
  })
  it('routes on connected rails and refuses disconnected geometry', () => {
    const feature = (coordinates: number[][]) => ({ geometry: { type: 'LineString', coordinates }, properties: { mnemo: 'EXPLOITE' } }) as RailwayFeature
    const route = railRouter([feature([[0, 0], [0.01, 0], [0.01, 0.01]]), feature([[1, 1], [1.01, 1]])])
    expect(route([0, 0], [0.01, 0.01])).toEqual([[0, 0], [0.01, 0], [0.01, 0.01]])
    expect(route([0, 0], [1, 1])).toBeNull()
  })
})

const feature = (coordinates: number[][], mnemo = 'EXPLOITE') => ({ geometry: { type: 'LineString', coordinates }, properties: { mnemo } }) as RailwayFeature

describe('rail topology and station snapping', () => {
  it('snaps Niort to the nearest segment instead of a vertex on another line', () => {
    const route = railRouter([
      feature([[-0.453204923775185, 46.32076396663528], [-0.455400700149877, 46.31809722093717], [-0.457035755181723, 46.31618807750838]]),
      feature([[-0.453585675154395, 46.32009753560348], [-0.454162311493481, 46.31934441532711], [-0.455397454189046, 46.31788822568623]]),
    ])
    const path = route([-0.454639, 46.319491], [-0.457035755181723, 46.31618807750838])
    expect(path).not.toBeNull()
    expect(path!.at(-1)).toEqual([-0.457035755181723, 46.31618807750838])
    expect(path!.some(p => p[0] === -0.454162311493481)).toBe(false)
  })
  it('joins an endpoint to the middle of a nearby segment', () => {
    const route = railRouter([feature([[0, 0], [0.02, 0]]), feature([[0.01, 0.00005], [0.01, 0.01]])])
    const path = route([0, 0], [0.01, 0.01])
    expect(path).toContainEqual([0.01, 0])
    expect(path).toContainEqual([0.01, 0.00005])
  })
  it('closes tiny endpoint gaps across coordinate rounding boundaries', () => {
    const route = railRouter([feature([[0, 0], [0.010049, 0]]), feature([[0.010051, 0], [0.02, 0]])])
    expect(route([0, 0], [0.02, 0])).not.toBeNull()
  })
  it('keeps interior crossings, distant gaps and closed infrastructure disconnected', () => {
    const crossing = railRouter([feature([[-0.01, 0], [0.01, 0]]), feature([[0, -0.01], [0, 0.01]])])
    expect(crossing([-0.01, 0], [0, 0.01])).toBeNull()
    const gap = railRouter([feature([[0, 0], [0.01, 0]]), feature([[0.011, 0], [0.02, 0]])])
    expect(gap([0, 0], [0.02, 0])).toBeNull()
    const closed = railRouter([feature([[0, 0], [0.01, 0]]), feature([[0.01, 0], [0.02, 0]], 'FERME')])
    expect(closed([0, 0], [0.04, 0])).toBeNull()
  })
  it('routes directly between projections on the same sparse segment', () => {
    const route = railRouter([feature([[0, 0], [0.1, 0]])])
    const a: [number, number] = [0.04, 0.0001], b: [number, number] = [0.06, 0.0001]
    const path = route(a, b)!
    expect(path[0]![0]).toBeCloseTo(0.04)
    expect(path.at(-1)![0]).toBeCloseTo(0.06)
    const length = path.slice(1).reduce((sum, p, i) => sum + distance(path[i]!, p), 0)
    expect(length).toBeCloseTo(distance([0.04, 0], [0.06, 0]), 5)
    expect(route(b, a)!).toHaveLength(2)
    expect(route(a, a)).toHaveLength(1)
  })
  it('samples indexed distances like a full scan, including overruns', () => {
    const path: [number, number][] = [[0, 0], [0.01, 0], [0.01, 0.01], [0.02, 0.01]]
    const cumulative = [0]
    for (let i = 1; i < path.length; i++) cumulative.push(cumulative[i - 1]! + distance(path[i - 1]!, path[i]!))
    for (const meters of [-10, 0, 100, 1500, cumulative[2]!, cumulative.at(-1)!, 10000]) {
      const indexed = samplePath(path, meters, cumulative), scanned = samplePath(path, meters)
      expect(indexed.point[0]).toBeCloseTo(scanned.point[0], 10)
      expect(indexed.point[1]).toBeCloseTo(scanned.point[1], 10)
      expect(indexed.heading).toBe(scanned.heading)
    }
  })
})
