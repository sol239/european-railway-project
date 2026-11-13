import { distance, railRouter } from '../../shared/utils/train-position'
import type { RoutingRequest, RoutingResponse, RailTrack } from '../../shared/types/routing'

let route: ReturnType<typeof railRouter> | undefined
self.onmessage = (event: MessageEvent<RoutingRequest>) => {
  const request = event.data
  try {
    if (request.type === 'init') {
      route = railRouter(request.features)
      self.postMessage({ id: request.id, tracks: [] } satisfies RoutingResponse)
      return
    }
    if (!route) throw new Error('Rail graph is not initialized')
    const tracks = request.pairs.map(({ key, from, to }) => {
      const path = route!(from, to)
      let track: RailTrack | null = null
      if (path) {
        const cumulative = [0]
        for (let i = 1; i < path.length; i++) cumulative.push(cumulative[i - 1]! + distance(path[i - 1]!, path[i]!))
        track = { path, cumulative, length: cumulative.at(-1)! }
      }
      return { key, track }
    })
    self.postMessage({ id: request.id, tracks } satisfies RoutingResponse)
  } catch (error) {
    self.postMessage({ id: request.id, error: error instanceof Error ? error.message : String(error) } satisfies RoutingResponse)
  }
}
