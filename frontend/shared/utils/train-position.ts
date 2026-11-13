import type { ScheduledTrain } from '../types/train'
import type { RailwayFeature } from '../types/railway'
export type Point = [number, number]
export function distance(a: Point, b: Point) {
  const r = Math.PI / 180
  const lat = (b[1] - a[1]) * r, lon = (b[0] - a[0]) * r
  const h = Math.sin(lat / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(lon / 2) ** 2
  return 6371000 * 2 * Math.asin(Math.sqrt(Math.min(1, h)))
}
export function trainLeg(train: ScheduledTrain, seconds: number) {
  if (seconds < train.stops[0]!.departure || seconds > train.stops.at(-1)!.arrival) return null
  for (let i = 0; i < train.stops.length - 1; i++) {
    const from = train.stops[i]!, to = train.stops[i + 1]!
    if (seconds <= to.departure || i === train.stops.length - 2) {
      const duration = to.arrival - from.departure
      return { index: i, from, to, progress: duration > 0 ? Math.max(0, Math.min(1, (seconds - from.departure) / duration)) : 1 }
    }
  }
  return null
}
export function samplePath(path: Point[], meters: number, cumulative?: number[]) {
  let remaining = Math.max(0, meters), start = 1
  if (cumulative && path.length > 1) {
    let low = 1, high = path.length - 1
    while (low < high) {
      const mid = (low + high) >>> 1
      if (cumulative[mid]! < remaining) low = mid + 1
      else high = mid
    }
    start = low
    remaining -= cumulative[start - 1]!
  }
  for (let i = start; i < path.length; i++) {
    const a = path[i - 1]!, b = path[i]!, length = distance(a, b)
    if (remaining <= length) {
      const t = length ? remaining / length : 0
      return { point: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t] as Point,
        heading: Math.atan2((b[0] - a[0]) * Math.cos(a[1] * Math.PI / 180), b[1] - a[1]) }
    }
    remaining -= length
  }
  const last = path.at(-1)!, before = path.at(-2) ?? last
  return { point: last, heading: Math.atan2((last[0] - before[0]) * Math.cos(last[1] * Math.PI / 180), last[1] - before[1]) }
}
// A* over the published operating rail geometry. Unconnected station pairs
// remain unavailable rather than drawing trains on invented straight routes.
export function railRouter(features: RailwayFeature[]) {
  const points: Point[] = [], edges: Map<number, number>[] = [], ids = new Map<string, number>()
  const endpoints = new Set<number>()
  const segments: [number, number][] = []
  const node = (p: number[]) => {
    const key = `${p[0]},${p[1]}`
    if (!ids.has(key)) { ids.set(key, points.length); points.push([p[0]!, p[1]!]); edges.push(new Map()) }
    return ids.get(key)!
  }
  for (const f of features) {
    if (f.properties.mnemo !== 'EXPLOITE') continue
    const lines = f.geometry.type === 'LineString' ? [f.geometry.coordinates] : f.geometry.coordinates
    for (const line of lines) {
      endpoints.add(node(line[0]!)); endpoints.add(node(line.at(-1)!))
      for (let i = 1; i < line.length; i++) {
        const a = node(line[i - 1]!), b = node(line[i]!)
        if (a === b) continue
        const length = distance(points[a]!, points[b]!)
        edges[a]!.set(b, length); edges[b]!.set(a, length)
        segments.push([a, b])
      }
    }
  }
  // RFN is cartographic geometry: junction endpoints can miss another line's
  // vertex or end in the middle of its segment. Repair only endpoint contacts
  // within 20 m, never arbitrary crossings or gaps between distant rails.
  const parent = points.map((_, i) => i)
  function root(i: number): number {
    while (parent[i] !== i) { parent[i] = parent[parent[i]!]!; i = parent[i]! }
    return i
  }
  function connect(a: number, b: number) {
    const length = distance(points[a]!, points[b]!)
    edges[a]!.set(b, length); edges[b]!.set(a, length)
    parent[root(a)] = root(b)
  }
  for (const [a, b] of segments) parent[root(a)] = root(b)
  const segmentNodes = segments.map(([a, b]) => [{ id: a, t: 0 }, { id: b, t: 1 }])
  function splitSegment(index: number, t: number, point: Point) {
    const nodes = segmentNodes[index]!
    const existing = nodes.find(n => Math.abs(n.t - t) < 1e-10)
    if (existing) return existing.id
    const id = node(point)
    if (parent[id] === undefined) parent[id] = id
    const next = nodes.findIndex(n => n.t > t)
    const before = nodes[next - 1]!.id, after = nodes[next]!.id
    edges[before]!.delete(after); edges[after]!.delete(before)
    connect(before, id); connect(id, after)
    nodes.splice(next, 0, { id, t })
    return id
  }
  const cellSize = 0.001
  const cells = new Map<string, number[]>()
  for (let i = 0; i < segments.length; i++) {
    const [a, b] = segments[i]!.map(id => points[id]!) as [Point, Point]
    for (let x = Math.floor(Math.min(a[0], b[0]) / cellSize); x <= Math.floor(Math.max(a[0], b[0]) / cellSize); x++) {
      for (let y = Math.floor(Math.min(a[1], b[1]) / cellSize); y <= Math.floor(Math.max(a[1], b[1]) / cellSize); y++) {
        const key = `${x},${y}`
        if (!cells.has(key)) cells.set(key, [])
        cells.get(key)!.push(i)
      }
    }
  }
  for (const endpoint of endpoints) {
    const p = points[endpoint]!, cos = Math.cos(p[1] * Math.PI / 180)
    const x = Math.floor(p[0] / cellSize), y = Math.floor(p[1] / cellSize)
    let best: { index: number; t: number; point: Point } | undefined, nearest = 20
    const candidates = new Set<number>()
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      for (const i of cells.get(`${x + dx},${y + dy}`) ?? []) candidates.add(i)
    }
    for (const i of candidates) {
      const [a, b] = segments[i]!
      if (a === endpoint || b === endpoint) continue
      const start = points[a]!, end = points[b]!
      const vx = (end[0] - start[0]) * cos, vy = end[1] - start[1]
      const t = Math.max(0, Math.min(1, (((p[0] - start[0]) * cos * vx) + (p[1] - start[1]) * vy) / (vx * vx + vy * vy)))
      const point: Point = [start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1])]
      const d = distance(p, point)
      if (d < nearest) { nearest = d; best = { index: i, t, point } }
    }
    if (!best) continue
    // Split the target edge at the contact, retaining its original geometry.
    const junction = splitSegment(best.index, best.t, best.point)
    connect(endpoint, junction)
  }
  const components = points.map((_, i) => root(i))
  // Snap to the closest point on a segment, not the closest stored vertex.
  // Sparse vertices otherwise put stations on a nearby, unrelated line (Niort).
  const stationCells = new Map<string, number[]>()
  const snapCell = 0.025
  segments.forEach(([a, b], i) => {
    const start = points[a]!, end = points[b]!
    for (let x = Math.floor(Math.min(start[0], end[0]) / snapCell); x <= Math.floor(Math.max(start[0], end[0]) / snapCell); x++) {
      for (let y = Math.floor(Math.min(start[1], end[1]) / snapCell); y <= Math.floor(Math.max(start[1], end[1]) / snapCell); y++) {
        const key = `${x},${y}`
        if (!stationCells.has(key)) stationCells.set(key, [])
        stationCells.get(key)!.push(i)
      }
    }
  })
  const snaps = new Map<string, number | null>(), cache = new Map<string, Point[] | null>()
  function snap(p: Point) {
    const key = p.join(',')
    if (snaps.has(key)) return snaps.get(key)!
    let best: { index: number; a: number; t: number; point: Point } | undefined, nearest = 2000
    const x = Math.floor(p[0] / snapCell), y = Math.floor(p[1] / snapCell)
    const cos = Math.cos(p[1] * Math.PI / 180)
    const lonCells = Math.ceil(2000 / (111195 * cos) / snapCell)
    const candidates = new Set<number>()
    for (let dx = -lonCells; dx <= lonCells; dx++) for (let dy = -1; dy <= 1; dy++) {
      for (const i of stationCells.get(`${x + dx},${y + dy}`) ?? []) candidates.add(i)
    }
    for (const i of candidates) {
      const [a, b] = segments[i]!, start = points[a]!, end = points[b]!
      const vx = (end[0] - start[0]) * cos, vy = end[1] - start[1]
      const t = Math.max(0, Math.min(1, ((p[0] - start[0]) * cos * vx + (p[1] - start[1]) * vy) / (vx * vx + vy * vy)))
      const point: Point = [start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1])]
      const d = distance(p, point)
      if (d < nearest) { nearest = d; best = { index: i, a, t, point } }
    }
    if (!best) { snaps.set(key, null); return null }
    const id = splitSegment(best.index, best.t, best.point)
    components[id] = components[best.a]!
    snaps.set(key, id); return id
  }
  return (a: Point, b: Point): Point[] | null => {
    const key = `${a}:${b}`
    if (cache.has(key)) return cache.get(key)!
    const start = snap(a), end = snap(b)
    if (start === null || end === null || components[start] !== components[end]) { cache.set(key, null); return null }
    if (start === end) { const path = [points[start]!]; cache.set(key, path); return path }
    const costs = new Map([[start, 0]]), previous = new Map<number, number>()
    const heap: { id: number; score: number; cost: number }[] = []
    function push(v: typeof heap[number]) {
      heap.push(v); let i = heap.length - 1
      while (i > 0) { const p = (i - 1) >> 1; if (heap[p]!.score <= v.score) break; heap[i] = heap[p]!; i = p } heap[i] = v
    }
    function pop() {
      const first = heap[0]!, last = heap.pop()!
      if (heap.length) { let i = 0; while (i * 2 + 1 < heap.length) { let c = i * 2 + 1; if (c + 1 < heap.length && heap[c + 1]!.score < heap[c]!.score) c++; if (heap[c]!.score >= last.score) break; heap[i] = heap[c]!; i = c } heap[i] = last } return first
    }
    push({ id: start, score: 0, cost: 0 })
    while (heap.length) {
      const current = pop()
      if (current.cost !== costs.get(current.id)) continue
      if (current.id === end) {
        const route = [points[end]!]; let id = end
        while (id !== start) { id = previous.get(id)!; route.push(points[id]!) }
        route.reverse(); cache.set(key, route); return route
      }
      for (const [next, length] of edges[current.id]!) {
        const cost = current.cost + length
        if (cost >= (costs.get(next) ?? Infinity)) continue
        costs.set(next, cost); previous.set(next, current.id)
        push({ id: next, cost, score: cost + distance(points[next]!, points[end]!) })
      }
    }
    cache.set(key, null); return null
  }
}
