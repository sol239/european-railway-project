<script setup lang="ts">
import type { Station } from '../../shared/types/station'
import type { TimelineInstant, TrainDetails } from '../../shared/types/train'
import type { RailwayResponse } from '../../shared/types/railway'
import type { Viewer, CustomDataSource, ScreenSpaceEventHandler, Entity, Cartesian2 } from 'cesium'

const props = defineProps<{ stations: Station[]; selectedKey: number | null; selectedTrainId?: string; followTrain?: boolean }>()
const emit = defineEmits<{ select: [station: Station]; trainSelect: [details: TrainDetails | null]; timeline: [instant: TimelineInstant] }>()
const container = ref<HTMLElement>()
const ready = ref(false)
const trainState = ref<'loading' | 'ready' | 'error'>('loading')
const fullyReady = computed(() => ready.value && railwaysReady.value && trainState.value === 'ready')
const loadingFailed = computed(() => railsError.value || trainState.value === 'error')
function retryLoading() {
  if (railsError.value) void changeRailways()
  if (trainState.value === 'error') trainLayer.value?.reload()
}
const trainLayer = ref<{ selectEntity: (entity: Entity) => boolean; reload: () => void }>()
const railwayGeometry = shallowRef<RailwayResponse>()
const timelineInstant = shallowRef<TimelineInstant>()
function updateTimeline(instant: TimelineInstant) {
  timelineInstant.value = instant
  emit('timeline', instant)
}
const settingsOpen = ref(false)
function openSettings() { settingsOpen.value = true }
function closeSettings() { settingsOpen.value = false }
defineExpose({ openSettings })
const mapError = ref('')
const imageryWarning = ref(false)
const mode = ref<'2D' | '3D'>('2D')
const resolution = ref(1)
const railsMode = ref<'off' | 'operating' | 'all'>('operating')
const railsLoading = ref(false)
const railsError = ref(false)
const railwaysReady = ref(false)
const railSegmentCount = ref(0)
const theme = ref<'light' | 'neon'>('light')
const neon = computed(() => theme.value === 'neon')
const stationIndex = computed(() => new Map(props.stations.map(station => [String(station.key), station])))
const flat = computed(() => mode.value === '2D')
let viewer: Viewer | undefined
let basemap: import('cesium').ImageryLayer | undefined
let basemapTheme: 'light' | 'neon' | undefined
let source: CustomDataSource | undefined
let railwaySource: import('cesium').GeoJsonDataSource | undefined
let railsController: AbortController | undefined
let handler: ScreenSpaceEventHandler | undefined
let cesium: typeof import('cesium')
let disposed = false
let hoverPickTimer: ReturnType<typeof setTimeout> | undefined
let hoverPosition: Cartesian2 | undefined
const stationImages = new Map<string, string>()

function stationImage(active: boolean, hasVisits: boolean) {
  const color = neon.value
    ? active ? '#ff65ce' : hasVisits ? '#69edff' : '#488498'
    : active ? '#2d7765' : hasVisits ? '#173a33' : '#78988a'
  const cached = stationImages.get(color)
  if (cached) return cached
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 96
  const context = canvas.getContext('2d')!
  context.scale(4, 4)
  context.beginPath()
  context.arc(12, 12, 10, 0, Math.PI * 2)
  context.fillStyle = color
  context.fill()
  context.strokeStyle = neon.value ? '#101d30' : '#ffffff'
  context.lineWidth = 2
  context.stroke()
  const image = canvas.toDataURL('image/png')
  stationImages.set(color, image)
  return image
}
function clearCursor() {
  clearTimeout(hoverPickTimer)
  hoverPickTimer = undefined
  hoverPosition = undefined
  if (viewer && !viewer.isDestroyed()) viewer.canvas.style.cursor = ''
}

function applyRailways() {
  if (!viewer || !railwaySource) return
  railwaySource.show = railsMode.value !== 'off'
  const railColor = cesium.Color.fromCssColorString(neon.value ? '#a2e6ee' : '#527d6c')
    .withAlpha(props.selectedTrainId ? 0.2 : 1)
  const railMaterial = new cesium.ColorMaterialProperty(railColor)
  let count = 0
  railwaySource.entities.suspendEvents()
  try {
    for (const entity of railwaySource.entities.values) {
      const operating = entity.properties?.mnemo?.getValue(cesium.JulianDate.now()) === 'EXPLOITE'
      entity.show = railsMode.value === 'all' || (railsMode.value === 'operating' && operating)
      if (entity.polyline) entity.polyline.material = railMaterial
      if (entity.show) count++
    }
  } finally { railwaySource.entities.resumeEvents() }
  railSegmentCount.value = count
  viewer.scene.requestRender()
}
function applyStationFocus() {
  if (!viewer || !source) return
  const color = cesium.Color.WHITE.withAlpha(props.selectedTrainId ? 0.2 : 1)
  source.entities.suspendEvents()
  try {
    for (const entity of source.entities.values) {
      if (entity.billboard) entity.billboard.color = new cesium.ConstantProperty(color)
    }
  } finally { source.entities.resumeEvents() }
  viewer.scene.requestRender()
}
async function changeRailways() {
  if (railwaySource) { applyRailways(); return }
  if (!viewer || railsMode.value === 'off' || railsLoading.value) return
  railsLoading.value = true
  railsError.value = false
  railsController = new AbortController()
  try {
    const collection = await $fetch<RailwayResponse>('/api/railways', { signal: railsController.signal })
    if (disposed) return
    railwayGeometry.value = collection
    const dataSource = await cesium.GeoJsonDataSource.load(collection, {
      stroke: cesium.Color.fromCssColorString(neon.value ? '#a2e6ee' : '#527d6c'), strokeWidth: 1.25,
      clampToGround: false, credit: 'SNCF Réseau · RFN · ODbL',
    })
    if (disposed || !viewer || viewer.isDestroyed()) return
    // The map uses an ellipsoid, so ground classification is unnecessary.
    // Lift ordinary polylines slightly above it to avoid surface stippling.
    const now = cesium.JulianDate.now()
    for (const entity of dataSource.entities.values) {
      const line = entity.polyline
      const positions = line?.positions?.getValue(now)
      if (!line || !positions) continue
      line.positions = new cesium.ConstantProperty(positions.map((position: import('cesium').Cartesian3) => {
        const location = cesium.Cartographic.fromCartesian(position)
        return cesium.Cartesian3.fromRadians(location.longitude, location.latitude, 30)
      }))
    }
    railwaySource = dataSource
    await viewer.dataSources.add(dataSource)
    if (disposed || viewer.isDestroyed()) return
    viewer.dataSources.lowerToBottom(dataSource)
    railwaysReady.value = true
    applyRailways()
  } catch (error) {
    if (!disposed) {
      console.error('Railway layer could not be loaded', error)
      railsError.value = true
    }
  } finally { railsLoading.value = false }
}

function home() {
  if (!viewer) return
  viewer.camera.flyToBoundingSphere(new cesium.BoundingSphere(cesium.Cartesian3.fromDegrees(2.7, 46.6), 1), {
    offset: new cesium.HeadingPitchRange(0, -cesium.Math.PI_OVER_TWO + (flat.value ? 0 : 0.3), 1_700_000),
    duration: 0.9,
  })
}
function zoom(direction: number) {
  if (!viewer) return
  const distance = Math.max(viewer.camera.positionCartographic.height * 0.45, 500)
  if (direction > 0) viewer.camera.zoomIn(distance)
  else viewer.camera.zoomOut(distance)
  viewer.scene.requestRender()
}
function changeMode() {
  if (!viewer) return
  viewer.camera.cancelFlight()
  if (flat.value) viewer.scene.morphTo2D(0)
  else viewer.scene.morphTo3D(0)
  home()
}
function changeResolution() {
  if (!viewer) return
  // Basemap refinement is independent of the device-aware canvas resolution.
  // On the ellipsoid globe, screen-space error controls tile refinement and
  // therefore imagery detail independently of canvas resolution.
  viewer.scene.globe.maximumScreenSpaceError = 2 / resolution.value
  viewer.scene.requestRender()
}
function renderStations() {
  if (!viewer || !source) return
  const maximum = Math.max(...props.stations.map(station => station.visits), 1)
  source.entities.suspendEvents()
  source.entities.removeAll()
  for (const station of props.stations) {
    const active = station.key === props.selectedKey
    const size = active ? 14 : Math.round(6 + 5 * Math.sqrt(station.visits / maximum))
    source.entities.add({
      id: String(station.key), name: station.name,
      position: cesium.Cartesian3.fromDegrees(station.longitude, station.latitude, 0),
      // Billboards project their world position correctly in both 2D and 3D.
      // PointPrimitive screen-space positions in this Cesium version use an
      // already-projected position in 2D, producing stale or displaced groups.
      billboard: {
        image: stationImage(active, station.visits > 0),
        color: cesium.Color.WHITE.withAlpha(props.selectedTrainId ? 0.2 : 1),
        width: size, height: size,
        horizontalOrigin: cesium.HorizontalOrigin.CENTER,
        verticalOrigin: cesium.VerticalOrigin.CENTER,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    })
  }
  source.entities.resumeEvents()
  viewer.scene.requestRender()
}
function imageryProvider(style: 'Light' | 'Dark', layer: 'Base' | 'Reference') {
  const provider = new cesium.UrlTemplateImageryProvider({
    url: `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${style}_Gray_${layer}/MapServer/tile/{z}/{y}/{x}`,
    credit: new cesium.Credit('Esri, HERE, Garmin, © OpenStreetMap contributors', true),
    maximumLevel: 16,
  })
  if (style === 'Dark' && layer === 'Base') {
    // Tint base tiles only. Reference labels, station sprites and rail lines
    // keep their native colors and antialiased edges.
    const requestImage = provider.requestImage.bind(provider)
    provider.requestImage = (x, y, level, request) => {
      const pending = requestImage(x, y, level, request)
      if (!pending) return undefined
      return pending.then(image => {
        if (!(image instanceof HTMLImageElement || image instanceof HTMLCanvasElement
          || image instanceof ImageBitmap || image instanceof OffscreenCanvas)) return image
        const canvas = document.createElement('canvas')
        canvas.width = image.width
        canvas.height = image.height
        const context = canvas.getContext('2d')!
        // Cesium decodes ImageBitmaps flipped for GPU upload. Canvas-backed
        // tiles use the ordinary image upload path, so restore their orientation.
        if (image instanceof ImageBitmap) {
          context.translate(0, canvas.height)
          context.scale(1, -1)
        }
        context.drawImage(image, 0, 0)
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height)
        for (let i = 0; i < pixels.data.length; i += 4) {
          const shade = (pixels.data[i]! + pixels.data[i + 1]! + pixels.data[i + 2]!) / (3 * 64)
          pixels.data[i] = Math.min(255, Math.round(16 * shade))
          pixels.data[i + 1] = Math.min(255, Math.round(29 * shade))
          pixels.data[i + 2] = Math.min(255, Math.round(48 * shade))
        }
        context.putImageData(pixels, 0, 0)
        return canvas
      })
    }
  }
  provider.errorEvent.addEventListener(() => { imageryWarning.value = true })
  return provider
}
function styleBasemap() {
  if (!viewer || basemapTheme === theme.value) return
  viewer.imageryLayers.removeAll()
  imageryWarning.value = false
  const style = neon.value ? 'Dark' : 'Light'
  basemap = viewer.imageryLayers.addImageryProvider(imageryProvider(style, 'Base'))
  // Labels retain the provider's original contrast, independent of map styling.
  viewer.imageryLayers.addImageryProvider(imageryProvider(style, 'Reference'))
  basemapTheme = theme.value
  const background = cesium.Color.fromCssColorString(neon.value ? '#101d30' : '#ffffff')
  viewer.scene.backgroundColor = background
  viewer.scene.globe.baseColor = background
  viewer.scene.requestRender()
}
function changeTheme() {
  styleBasemap()
  applyRailways()
  try { localStorage.setItem('railway-map-theme', theme.value) } catch {}
  stationImages.clear()
  renderStations()
}
watch(theme, () => {
  if (import.meta.client) document.documentElement.dataset.mapTheme = theme.value
  changeTheme()
}, { flush: 'sync' })
watch(() => props.stations, renderStations)
watch(() => props.selectedTrainId, () => { applyRailways(); applyStationFocus() })
watch(() => props.selectedKey, (key) => {
  renderStations()
  const station = props.stations.find(station => station.key === key)
  if (viewer && station) {
    viewer.camera.flyToBoundingSphere(new cesium.BoundingSphere(cesium.Cartesian3.fromDegrees(station.longitude, station.latitude), 1), {
      offset: new cesium.HeadingPitchRange(0, -cesium.Math.PI_OVER_TWO + (flat.value ? 0 : 0.3), 75_000),
      duration: 1.2,
    })
  }
})
onMounted(async () => {
  try {
    try {
      if (localStorage.getItem('railway-map-theme') === 'neon') theme.value = 'neon'
    } catch {}
    document.documentElement.dataset.mapTheme = theme.value
    cesium = await import('cesium')
    if (disposed || !container.value) return
    viewer = new cesium.Viewer(container.value, {
      sceneMode: cesium.SceneMode.SCENE2D,
      baseLayer: false,
      useBrowserRecommendedResolution: false,
      msaaSamples: 1,
      terrainProvider: new cesium.EllipsoidTerrainProvider(),
      animation: false, timeline: false, baseLayerPicker: false, geocoder: false,
      homeButton: false, navigationHelpButton: false, sceneModePicker: false,
      fullscreenButton: false, infoBox: false, selectionIndicator: false,
      skyBox: false, skyAtmosphere: false,
      requestRenderMode: true, maximumRenderTimeChange: Infinity,
      contextOptions: { webgl: { alpha: false } },
    })
    // Preserve antialiased text and sprite edges; palette shaders must not
    // reinterpret partially transparent pixels around markers or labels.
    viewer.scene.postProcessStages.fxaa.enabled = false
    viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 1.5)
    changeResolution()
    styleBasemap()
    viewer.scene.screenSpaceCameraController.enableLook = false
    // Set the final camera before adding map data.
    viewer.camera.lookAt(
      cesium.Cartesian3.fromDegrees(2.7, 46.6),
      new cesium.HeadingPitchRange(0, -cesium.Math.PI_OVER_TWO, 1_700_000),
    )
    viewer.camera.lookAtTransform(cesium.Matrix4.IDENTITY)
    source = new cesium.CustomDataSource('stations')
    await viewer.dataSources.add(source)
    if (disposed) return
    renderStations()
    handler = new cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
    handler.setInputAction((event: { position: import('cesium').Cartesian2 }) => {
      if (!viewer) return
      const picked = viewer.scene.pick(event.position)
      if (!picked?.id) return
      if (trainLayer.value?.selectEntity(picked.id)) return
      const station = props.stations.find(station => String(station.key) === picked.id.id)
      if (station) emit('select', station)
    }, cesium.ScreenSpaceEventType.LEFT_CLICK)
    handler.setInputAction((event: { endPosition: Cartesian2 }) => {
      hoverPosition = event.endPosition
      if (hoverPickTimer) return
      hoverPickTimer = setTimeout(() => {
        hoverPickTimer = undefined
        if (!viewer || viewer.isDestroyed() || !hoverPosition) return
        const picked = viewer.scene.pick(hoverPosition)
        viewer.canvas.style.cursor = stationIndex.value.has(picked?.id?.id) || String(picked?.id?.id).startsWith('train:') ? 'pointer' : ''
      }, 80)
    }, cesium.ScreenSpaceEventType.MOUSE_MOVE)
    ready.value = true
    void changeRailways()
  } catch (error) {
    console.error('Map initialization failed', error)
    mapError.value = 'The map could not start. Enable WebGL in your browser and reload. You can still explore stations in the list.'
  }
})
onBeforeUnmount(() => {
  disposed = true
  railsController?.abort()
  clearCursor()
  stationImages.clear()
  handler?.destroy()
  if (viewer && !viewer.isDestroyed()) viewer.destroy()
})
</script>

<template>
  <div class="map-frame" data-testid="station-map" :data-ready="fullyReady" :aria-busy="!fullyReady && !mapError && !loadingFailed" :data-theme="theme" :data-railways-ready="railwaysReady" :data-railway-segments="railSegmentCount">
    <div ref="container" class="cesium-host" aria-label="Interactive railway station map" @mouseleave="clearCursor" />
    <div v-if="!fullyReady && !mapError" class="map-loading map-startup-loading" :role="loadingFailed ? 'alert' : 'status'">
      <template v-if="loadingFailed"><p>{{ railsError ? 'Railway lines could not be loaded.' : 'Train schedules could not be loaded.' }}</p><UButton class="retry-button" @click="retryLoading">Try again</UButton></template>
      <template v-else><UIcon name="i-lucide-loader-circle" class="animate-spin size-5" aria-hidden="true" /><span>{{ !ready ? 'Preparing your map…' : !railwaysReady ? 'Loading railway lines…' : 'Loading trains…' }}</span></template>
    </div>
    <div v-if="mapError" class="map-failure" role="alert"><AppIcon name="layers" :size="32" /><p>{{ mapError }}</p></div>
    <div v-if="ready" class="map-controls" aria-label="Map controls">
      <UButton icon="i-lucide-house" color="neutral" variant="outline" size="lg" square title="Reset map to France" aria-label="Reset map to France" @click="home" />
      <UFieldGroup orientation="vertical">
        <UButton icon="i-lucide-plus" color="neutral" variant="outline" size="lg" square title="Zoom in" aria-label="Zoom in" @click="zoom(1)" />
        <UButton icon="i-lucide-minus" color="neutral" variant="outline" size="lg" square title="Zoom out" aria-label="Zoom out" @click="zoom(-1)" />
      </UFieldGroup>
    </div>
    <label v-if="ready" class="railways-control"><AppIcon name="rail" :size="16" /><span>Rails</span><USelect v-model="railsMode" aria-label="Railway lines" :items="[{ label: 'Off', value: 'off' }, { label: 'Operating', value: 'operating' }, { label: 'All statuses', value: 'all' }]" :content="{ side: 'bottom', align: 'start' }" :ui="{ content: 'map-select-menu' }" @update:model-value="changeRailways" /></label>
    <div v-if="railsMode !== 'off' && (railsLoading || railsError)" class="railways-notice" :role="railsError ? 'alert' : 'status'"><template v-if="railsLoading"><UIcon name="i-lucide-loader-circle" class="animate-spin size-5" aria-hidden="true" /> Loading railway lines…</template><template v-else>Railway lines could not be loaded.<UButton @click="changeRailways">Retry</UButton></template></div>
    <div v-if="imageryWarning" class="imagery-warning" role="status">Some basemap tiles are unavailable. Station data remains accessible.</div>

    <aside v-if="ready" class="map-legend" aria-label="Map legend">
      <h2>Map legend</h2>
      <ul>
        <li><span class="legend-mark legend-station" aria-hidden="true" />Station</li>
        <li><span class="legend-mark legend-selected-station" aria-hidden="true" />Selected station</li>
        <li><span class="legend-mark legend-train" aria-hidden="true" />Train estimate</li>
        <li><span class="legend-mark legend-route" aria-hidden="true" />Selected train route</li>
        <li><span class="legend-mark legend-rail" aria-hidden="true" />Railway line</li>
      </ul>
    </aside>

    <MapTimeline @change="updateTimeline" />
    <TrainLayer :follow="followTrain" @state="trainState = $event" ref="trainLayer" :selected-id="selectedTrainId" @select="emit('trainSelect', $event)" v-if="ready && viewer && railwayGeometry && timelineInstant" :viewer="viewer" :railway="railwayGeometry" :instant="timelineInstant" :theme="theme" :mode="mode" />
    <UModal v-model:open="settingsOpen" title="Map settings" description="Adjust the map to suit your view. Changes apply immediately." :ui="{ content: 'map-settings-modal', overlay: 'bg-slate-950/60 backdrop-blur-sm', body: 'settings-fields', footer: 'justify-end' }">
      <template #body>
        <UFormField label="Map view" class="settings-field"><USelect v-model="mode" aria-label="Map view" :ui="{ content: 'map-select-menu' }" :items="['2D', '3D']" @update:model-value="changeMode" /></UFormField>
        <UFormField label="Theme" class="settings-field"><USelect v-model="theme" aria-label="Map theme" :ui="{ content: 'map-select-menu' }" :items="[{ label: 'Light', value: 'light' }, { label: 'Neon', value: 'neon' }]" /></UFormField>
        <UFormField label="Map tile detail" class="settings-field"><USelect v-model="resolution" aria-label="Map resolution" :ui="{ content: 'map-select-menu' }" :items="[0.5, 0.75, 1, 1.5, 2, 3].map(value => ({ label: value + '×', value }))" @update:model-value="changeResolution" /></UFormField>
      </template>
      <template #footer><UButton variant="solid" color="primary" @click="closeSettings">Done</UButton></template>
    </UModal>
  </div>
</template>
