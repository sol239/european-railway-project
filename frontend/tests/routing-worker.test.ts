import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RailwayFeature } from '../shared/types/railway'
import type { RoutingRequest, RoutingResponse } from '../shared/types/routing'

async function startWorker() {
  vi.resetModules()
  const responses: RoutingResponse[] = []
  const scope = {
    onmessage: undefined as ((event: { data: RoutingRequest }) => void) | undefined,
    postMessage: (response: RoutingResponse) => responses.push(response),
  }
  vi.stubGlobal('self', scope)
  await import('../app/workers/rail-routing.worker')
  return (data: RoutingRequest) => {
    scope.onmessage!({ data })
    return responses.at(-1)!
  }
}
const line = (coordinates: number[][]) => ({
  geometry: { type: 'LineString', coordinates }, properties: { mnemo: 'EXPLOITE' },
}) as RailwayFeature

afterEach(() => vi.unstubAllGlobals())

describe('routing worker protocol', () => {
  it('reports requests made before graph initialization', async () => {
    const send = await startWorker()
    expect(send({ id: 1, type: 'routes', pairs: [] })).toEqual({ id: 1, error: 'Rail graph is not initialized' })
  })
  it('returns indexed paths and null for disconnected pairs in one batch', async () => {
    const send = await startWorker()
    expect(send({ id: 1, type: 'init', features: [line([[0, 0], [0.02, 0]]), line([[1, 1], [1.01, 1]])] })).toEqual({ id: 1, tracks: [] })
    const response = send({ id: 2, type: 'routes', pairs: [
      { key: 'connected', from: [0, 0], to: [0.02, 0] },
      { key: 'disconnected', from: [0, 0], to: [1, 1] },
    ] })
    expect(response.id).toBe(2)
    expect(response.error).toBeUndefined()
    const track = response.tracks![0]!.track!
    expect(track.path).toEqual([[0, 0], [0.02, 0]])
    expect(track.cumulative).toEqual([0, track.length])
    expect(track.length).toBeGreaterThan(2000)
    expect(response.tracks![1]).toEqual({ key: 'disconnected', track: null })
  })
})
