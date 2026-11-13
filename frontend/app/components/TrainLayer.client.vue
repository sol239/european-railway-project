<script setup lang="ts">
import type { Viewer, Entity } from 'cesium'
import type { RailwayResponse } from '../../shared/types/railway'
import type { TimelineInstant, TrainSchedule, TrainStop, TrainDetails } from '../../shared/types/train'
import { samplePath } from '../../shared/utils/train-position'
import type { RailTrack, RoutePair, RoutingRequest, RoutingResponse } from '../../shared/types/routing'
import { trainLeg } from '../../shared/utils/train-position'
const props = defineProps<{ viewer: Viewer; railway: RailwayResponse; instant: TimelineInstant; theme: 'light' | 'neon'; mode: '2D' | '3D'; selectedId?: string; follow?: boolean }>()
const emit = defineEmits<{ select: [details: TrainDetails | null]; state: [state: 'loading' | 'ready' | 'error'] }>()
const details = new Map<string, TrainDetails>()
function selectEntity(entity: Entity) {
  const train = details.get(entity.id)
  if (!train) return false
  emit('select', withJourneyDistance(train)); return true
}
defineExpose({ selectEntity, reload: () => loadSchedule(props.instant.date) })
import * as cesium from 'cesium'
const source = new cesium.CustomDataSource('scheduled-trains')
const selectionSource = new cesium.CustomDataSource('selected-train-route')
const mutedTrainColor = cesium.Color.WHITE.withAlpha(0.2)
const schedule = shallowRef<TrainSchedule>()
const loading = ref(false), failed = ref(false), shown = ref(0), unmatched = ref(0)
let disposed = false, controller: AbortController | undefined
let removeCamera: (() => void) | undefined
let removeMorph: (() => void) | undefined
const worker = new Worker(new URL('../workers/rail-routing.worker.ts', import.meta.url), { type: 'module' })
let requestId = 0
let workerFailure: Error | undefined
const requests = new Map<number, { resolve: (response: RoutingResponse) => void; reject: (error: Error) => void }>()
function request(message: Omit<Extract<RoutingRequest, { type: 'init' }>, 'id'> | Omit<Extract<RoutingRequest, { type: 'routes' }>, 'id'>) {
  return new Promise<RoutingResponse>((resolve, reject) => {
    if (workerFailure) { reject(workerFailure); return }
    const id = ++requestId
    requests.set(id, { resolve, reject })
    worker.postMessage({ ...message, id })
  })
}
worker.onmessage = (event: MessageEvent<RoutingResponse>) => {
  const response = event.data, pending = requests.get(response.id)
  requests.delete(response.id)
  if (response.error) pending?.reject(new Error(response.error))
  else pending?.resolve(response)
}
worker.onerror = () => {
  workerFailure = new Error('Rail routing worker failed')
  for (const pending of requests.values()) pending.reject(workerFailure)
  requests.clear()
  if (!disposed) { failed.value = true; emit('state', 'error') }
}
// Attach a rejection handler immediately, even if schedule loading has not finished.
const graphReady = request({ type: 'init', features: props.railway.features })
void graphReady.catch(() => {})
const routes = new Map<string, RailTrack | null>()
const pendingRoutes = new Map<string, Promise<void>>()
const cars = new Map<string, Entity[]>()
const images = new Map<string, string>()
const routeKey = (from: TrainStop, to: TrainStop) => `${from.longitude},${from.latitude}:${to.longitude},${to.latitude}`
function trackBetween(from: TrainStop, to: TrainStop) {
  return routes.get(routeKey(from, to))
}
async function prepareRoutes() {
  await graphReady
  if (disposed) return
  const pairs = new Map<string, RoutePair>(), waiting = new Set<Promise<void>>()
  function add(from: TrainStop, to: TrainStop) {
    const key = routeKey(from, to)
    if (routes.has(key)) return
    const pending = pendingRoutes.get(key)
    if (pending) { waiting.add(pending); return }
    pairs.set(key, { key, from: [from.longitude, from.latitude], to: [to.longitude, to.latitude] })
  }
  for (const train of schedule.value?.trains ?? []) {
    const leg = trainLeg(train, props.instant.seconds)
    if (leg) add(leg.from, leg.to)
    if (train.id === props.selectedId) {
      for (let i = 1; i < train.stops.length; i++) add(train.stops[i - 1]!, train.stops[i]!)
    }
  }
  if (pairs.size) {
    const batch = request({ type: 'routes', pairs: [...pairs.values()] }).then(response => {
      for (const { key, track } of response.tracks ?? []) routes.set(key, track)
    }).finally(() => { for (const key of pairs.keys()) pendingRoutes.delete(key) })
    for (const key of pairs.keys()) pendingRoutes.set(key, batch)
    waiting.add(batch)
  }
  await Promise.all(waiting)
}
async function refresh() {
  try {
    await prepareRoutes()
    if (!disposed) { render(); renderSelection() }
  } catch { if (!disposed) { failed.value = true; emit('state', 'error') } }
}
const journeyLengths = new Map<string, number[] | null>()
function withJourneyDistance(detail: TrainDetails): TrainDetails {
  if (!journeyLengths.has(detail.id)) {
    const lengths: number[] = []
    for (let i = 1; i < detail.stops.length; i++) {
      const track = trackBetween(detail.stops[i - 1]!, detail.stops[i]!)
      if (!track) {
        if (!routes.has(routeKey(detail.stops[i - 1]!, detail.stops[i]!))) return detail
        journeyLengths.set(detail.id, null); break
      }
      lengths.push(track.length)
    }
    if (!journeyLengths.has(detail.id)) journeyLengths.set(detail.id, lengths)
  }
  const lengths = journeyLengths.get(detail.id)
  if (!lengths) return detail
  const index = detail.stops.indexOf(detail.from)
  return { ...detail, distanceMeters: lengths.reduce((sum, length) => sum + length, 0),
    travelledMeters: lengths.slice(0, index).reduce((sum, length) => sum + length, 0) + detail.segmentMeters * detail.progress }
}
function trainImage() {
  const color = props.theme === 'neon' ? '#fff0ac' : '#392856'
  if (images.has(color)) return images.get(color)!
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = 96
  const c = canvas.getContext('2d')!; c.scale(4, 4)
  c.beginPath()
  // The point is the front of the train; billboard rotation turns it along the track.
  c.moveTo(12, 2)
  c.lineTo(19, 9)
  c.lineTo(19, 22)
  c.lineTo(5, 22)
  c.lineTo(5, 9)
  c.closePath(); c.fillStyle = color; c.fill()
  c.strokeStyle = props.theme === 'neon' ? '#101d30' : '#ffffff'; c.lineWidth = 1.3; c.stroke()
  const image = canvas.toDataURL(); images.set(color, image); return image
}
let selectionVersion = ''
function renderSelection() {
  if (disposed || props.viewer.isDestroyed()) return
  const version = `${props.selectedId}:${props.theme}:${schedule.value?.date}:${routes.size}`
  if (selectionVersion === version) return
  selectionVersion = version
  selectionSource.entities.removeAll()
  const train = schedule.value?.trains.find(train => train.id === props.selectedId)
  if (!train) { props.viewer.scene.requestRender(); return }
  const color = cesium.Color.fromCssColorString(props.theme === 'neon' ? '#fff0ac' : '#392856')
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = 64
  const context = canvas.getContext('2d')!
  context.beginPath(); context.arc(32, 32, 24, 0, Math.PI * 2)
  context.fillStyle = props.theme === 'neon' ? '#101d30' : '#ffffff'; context.fill()
  context.strokeStyle = color.toCssColorString(); context.lineWidth = 9; context.stroke()
  context.beginPath(); context.arc(32, 32, 8, 0, Math.PI * 2); context.fillStyle = color.toCssColorString(); context.fill()
  const stopImage = canvas.toDataURL()
  const seen = new Set<number>()
  for (const stop of train.stops) {
    if (seen.has(stop.station)) continue
    seen.add(stop.station)
    selectionSource.entities.add({ id: String(stop.station), name: stop.name,
      position: cesium.Cartesian3.fromDegrees(stop.longitude, stop.latitude, 80),
      billboard: { image: stopImage, width: 18, height: 18, disableDepthTestDistance: Infinity },
    })
  }
  for (let i = 1; i < train.stops.length; i++) {
    const track = trackBetween(train.stops[i - 1]!, train.stops[i]!)
    if (!track) continue
    selectionSource.entities.add({ id: `selected-route:${i}`, polyline: {
      positions: track.path.map(p => cesium.Cartesian3.fromDegrees(p[0], p[1], 60)),
      width: 3, clampToGround: false, material: color,
    } })
  }
  props.viewer.scene.requestRender()
}
let lastFollow: { position: cesium.Cartesian3; mode: string } | undefined
function syncTracking() {
  if (disposed || props.viewer.isDestroyed()) return
  const target = props.follow && props.selectedId ? cars.get(props.selectedId)?.[0] : undefined
  const position = target?.position?.getValue(cesium.JulianDate.now())
  if (!position) { lastFollow = undefined; return }
  if (lastFollow?.mode === props.mode && cesium.Cartesian3.equalsEpsilon(lastFollow.position, position, 0, 0.01)) return
  const camera = props.viewer.camera
  camera.cancelFlight()
  if (props.mode === '2D') {
    const location = cesium.Cartographic.fromCartesian(position)
    camera.setView({ destination: cesium.Cartesian3.fromRadians(location.longitude, location.latitude,
      lastFollow ? camera.positionCartographic.height : 25000) })
  } else {
    camera.lookAt(position, new cesium.HeadingPitchRange(camera.heading,
      Math.min(camera.pitch, -0.3), lastFollow ? Math.max(camera.positionCartographic.height, 1000) : 25000))
    camera.lookAtTransform(cesium.Matrix4.IDENTITY)
  }
  lastFollow = { position: cesium.Cartesian3.clone(position), mode: props.mode }
  props.viewer.scene.requestRender()
}
function render() {
  if (disposed || props.viewer.isDestroyed()) return
  source.entities.suspendEvents()
  try {
    details.clear()
    const active = new Set<string>(); let skipped = 0
    const flat = props.mode === '2D'
    for (const train of schedule.value?.trains ?? []) {
      const leg = trainLeg(train, props.instant.seconds)
      if (!leg) continue
      const track = trackBetween(leg.from, leg.to)
      if (!track) { skipped++; continue }
      active.add(train.id)
      let consist = cars.get(train.id)
      if (!consist) {
        consist = [source.entities.add({
          id: `train:${train.id}`, name: train.name,
          description: `Timetable estimate: ${leg.from.name} → ${leg.to.name}`,
          billboard: { image: trainImage(), width: 16, height: 16, disableDepthTestDistance: Infinity },
        })]
        cars.set(train.id, consist)
      }
      const entity = consist[0]!
      const at = samplePath(track.path, track.length * leg.progress, track.cumulative)
      const detail: TrainDetails = { id: train.id, name: train.name, date: props.instant.date, seconds: props.instant.seconds, stops: train.stops, from: leg.from, to: leg.to, progress: leg.progress, longitude: at.point[0], latitude: at.point[1], distanceMeters: null, travelledMeters: null, segmentMeters: track.length }
      details.set(entity.id, detail)
      if (props.selectedId === train.id) emit('select', withJourneyDistance(detail))
      const billboard = entity.billboard!
      const scale = props.selectedId === train.id ? 1.4 : 1, image = trainImage()
      const now = props.viewer.clock.currentTime
      if (billboard.scale?.getValue(now) !== scale) billboard.scale = new cesium.ConstantProperty(scale)
      if (billboard.image?.getValue(now) !== image) billboard.image = new cesium.ConstantProperty(image)
      const color = props.selectedId && props.selectedId !== train.id ? mutedTrainColor : cesium.Color.WHITE
      if (!cesium.Color.equals(billboard.color?.getValue(now), color)) billboard.color = new cesium.ConstantProperty(color)
      const position = cesium.Cartesian3.fromDegrees(at.point[0], at.point[1], flat ? 40 : 80)
      if (entity.position instanceof cesium.ConstantPositionProperty) entity.position.setValue(position)
      else entity.position = new cesium.ConstantPositionProperty(position)
      const rotation = -at.heading + (flat ? 0 : props.viewer.camera.heading)
      if (billboard.rotation instanceof cesium.ConstantProperty) billboard.rotation.setValue(rotation)
      else billboard.rotation = new cesium.ConstantProperty(rotation)

    }
    for (const [id, consist] of cars) if (!active.has(id)) { consist.forEach(entity => source.entities.remove(entity)); cars.delete(id) }
    if (props.selectedId && !active.has(props.selectedId)) emit('select', null)
    syncTracking()
    shown.value = active.size; unmatched.value = skipped
  } finally { source.entities.resumeEvents() }
  props.viewer.scene.requestRender()
}
async function loadSchedule(date: string) {
  emit('state', 'loading')
  controller?.abort(); controller = new AbortController()
  const current = controller
  loading.value = true; failed.value = false; schedule.value = undefined; render()
  try {
    const result = await $fetch<TrainSchedule>('/api/trains', { query: { date }, signal: current.signal })
    if (!disposed && controller === current) {
      schedule.value = result
      journeyLengths.clear()
      await prepareRoutes()
      if (disposed || controller !== current) return
      render(); renderSelection()
      await nextTick()
      if (!disposed && controller === current) emit('state', 'ready')
    }
  } catch { if (!current.signal.aborted) { failed.value = true; emit('state', 'error') } }
  finally { if (controller === current) loading.value = false }
}
watch(() => props.instant.date, loadSchedule, { immediate: true })
watch([() => props.selectedId, () => props.theme], () => {
  render()
  renderSelection()
  void refresh()
})
watch(() => props.follow, syncTracking)
watch(() => props.instant.seconds, refresh)
watch(() => props.mode, render)
onMounted(async () => {
  await props.viewer.dataSources.add(selectionSource)
  await props.viewer.dataSources.add(source)
  if (disposed) { if (!props.viewer.isDestroyed()) props.viewer.dataSources.remove(source, true); if (!props.viewer.isDestroyed()) props.viewer.dataSources.remove(selectionSource, true); return }
  removeCamera = props.viewer.camera.moveEnd.addEventListener(() => { if (props.mode === '3D') render() })
  removeMorph = props.viewer.scene.morphComplete.addEventListener(() => {
    lastFollow = undefined
    render()
  })
  render(); renderSelection()
})
onBeforeUnmount(() => {
  disposed = true; controller?.abort(); removeCamera?.(); removeMorph?.()
  worker.terminate()
  for (const pending of requests.values()) pending.reject(new Error('Train layer disposed'))
  requests.clear()
  if (!props.viewer.isDestroyed()) {
    if (props.viewer.trackedEntity?.id.startsWith('train:')) props.viewer.trackedEntity = undefined
    props.viewer.dataSources.remove(selectionSource, true)
    props.viewer.dataSources.remove(source, true)
  }
})
</script>
<template>
  <div class="train-status" role="status" :data-train-count="shown">
    <template v-if="loading">Loading train schedules…</template>
    <template v-else-if="failed">Train schedules unavailable.</template>
    <template v-else>{{ shown }} trains · timetable estimates<span v-if="unmatched"> · {{ unmatched }} without a connected rail route</span></template>
  </div>
</template>
