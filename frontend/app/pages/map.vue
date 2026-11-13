<script setup lang="ts">
import type { TimelineInstant, TrainDetails } from '../../shared/types/train'
import type { Station, StationResponse } from '../../shared/types/station'
const stationMap = ref<{ openSettings: () => void }>()
const selectedKey = ref<number | null>(null)
const selectedTrain = shallowRef<TrainDetails | null>(null)
const timelineInstant = shallowRef<TimelineInstant>()
const followTrain = ref(false)
watch(() => selectedTrain.value?.id, () => { followTrain.value = false })
const { data, status, error, refresh } = await useFetch<StationResponse>('/api/stations', { lazy: true })
const stations = computed(() => data.value?.stations ?? [])
const selected = computed(() => stations.value.find(station => station.key === selectedKey.value))
const format = (value: number) => new Intl.NumberFormat('en-GB').format(value)
function selectStation(station: Station) { selectedTrain.value = null; selectedKey.value = station.key }
function selectTrain(train: TrainDetails | null) { selectedTrain.value = train; if (train) selectedKey.value = null }
function scheduleTime(seconds: number) {
  const day = Math.floor(seconds / 86400)
  const value = ((seconds % 86400) + 86400) % 86400
  return `${String(Math.floor(value / 3600)).padStart(2, '0')}:${String(Math.floor(value / 60) % 60).padStart(2, '0')}${day ? ` (${day > 0 ? '+' : ''}${day}d)` : ''}`
}
function duration(seconds: number) {
  const minutes = Math.max(0, Math.round(seconds / 60))
  return minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${minutes} min`
}
function kilometers(meters: number | null) {
  return meters === null ? 'Route unavailable' : `${(meters / 1000).toLocaleString('en-GB', { maximumFractionDigits: 1 })} km`
}
const trainJourney = computed(() => {
  const train = selectedTrain.value
  if (!train) return null
  const origin = train.stops[0]!, destination = train.stops.at(-1)!
  return { origin, destination, duration: destination.arrival - origin.departure,
    elapsed: train.seconds - origin.departure, remaining: destination.arrival - train.seconds }
})
const timeProgress = computed(() => {
  const journey = trainJourney.value
  return journey && journey.duration > 0 ? Math.max(0, Math.min(100, journey.elapsed / journey.duration * 100)) : 0
})
const distanceProgress = computed(() => {
  const train = selectedTrain.value
  return train?.distanceMeters && train.travelledMeters !== null
    ? Math.max(0, Math.min(100, train.travelledMeters / train.distanceMeters * 100)) : 0
})
</script>

<template>
  <div class="atlas-app">
    <AppHeader show-settings @open-settings="stationMap?.openSettings()" />

    <main class="workspace">
      <aside class="explorer" aria-label="Station explorer">

        <UCard v-if="selected" :ui="{ body: 'p-0 sm:p-0' }" class="selected-station" data-testid="selected-station">
          <div class="selected-top"><h2>{{ selected.name }}</h2><UButton aria-label="Close station details" @click="selectedKey = null"><AppIcon name="close" :size="16" /></UButton></div>
          <div class="selected-visits"><strong>{{ format(selected.visits) }}</strong> scheduled stop visits</div>
          <div class="coordinates"><span>LAT <b>{{ selected.latitude.toFixed(5) }}</b></span><span>LON <b>{{ selected.longitude.toFixed(5) }}</b></span></div>
          <StationTimetable :station="selected" :instant="timelineInstant" />
        </UCard>

        <UCard :ui="{ body: 'p-0 sm:p-0' }" v-if="selectedTrain" class="selected-train" aria-label="Train details" data-testid="selected-train">
          <div class="selected-top"><h2>{{ selectedTrain.stops[0]?.name }} → {{ selectedTrain.stops.at(-1)?.name }}</h2><div class="train-detail-actions"><UButton class="camera-lock-button" :aria-pressed="followTrain" :aria-label="followTrain ? 'Stop following train' : 'Follow train with camera'" :title="followTrain ? 'Unlock camera' : 'Lock camera to train'" @click="followTrain = !followTrain"><AppIcon :name="followTrain ? 'camera-locked' : 'camera'" :size="18" /></UButton><UButton aria-label="Close train details" @click="selectedTrain = null"><AppIcon name="close" :size="16" /></UButton></div></div>
          <div v-if="trainJourney" class="train-detail-journey">
            <div class="train-endpoints" aria-label="Origin departure and final arrival">
              <UBadge color="neutral" variant="soft" class="train-endpoint" :title="`Origin departure: ${trainJourney.origin.name} ${scheduleTime(trainJourney.origin.departure)}`">
                <span class="sr-only">Origin departure: </span><span class="train-endpoint-name">{{ trainJourney.origin.name }}</span><time>{{ scheduleTime(trainJourney.origin.departure) }}</time>
              </UBadge>
              <AppIcon name="arrow" :size="14" aria-hidden="true" />
              <UBadge color="neutral" variant="soft" class="train-endpoint" :title="`Final arrival: ${trainJourney.destination.name} ${scheduleTime(trainJourney.destination.arrival)}`">
                <span class="sr-only">Final arrival: </span><span class="train-endpoint-name">{{ trainJourney.destination.name }}</span><time>{{ scheduleTime(trainJourney.destination.arrival) }}</time>
              </UBadge>
            </div>
            <div class="train-journey-progress" role="group" aria-label="Journey time">
              <div class="train-progress-heading"><span>Journey time</span><strong>{{ duration(trainJourney.duration) }}</strong></div>
              <UProgress :model-value="timeProgress" size="lg" color="neutral" :get-value-text="() => `${duration(trainJourney!.elapsed)} elapsed, ${duration(trainJourney!.remaining)} remaining`" />
              <div class="train-progress-caption"><span>{{ duration(trainJourney.elapsed) }} elapsed</span><span>{{ duration(trainJourney.remaining) }} remaining</span></div>
            </div>
            <div class="train-journey-progress" role="group" aria-label="Rail distance (estimated)">
              <div class="train-progress-heading"><span>Rail distance (estimated)</span><strong>{{ kilometers(selectedTrain.distanceMeters) }}</strong></div>
              <UProgress :model-value="distanceProgress" size="lg" color="neutral" :get-value-text="() => selectedTrain!.travelledMeters === null ? 'Route unavailable' : `${kilometers(selectedTrain!.travelledMeters)} travelled, ${kilometers(Math.max(0, selectedTrain!.distanceMeters! - selectedTrain!.travelledMeters))} remaining`" />
              <div v-if="selectedTrain.travelledMeters !== null" class="train-progress-caption"><span>{{ kilometers(selectedTrain.travelledMeters) }} travelled</span><span>{{ kilometers(Math.max(0, selectedTrain.distanceMeters! - selectedTrain.travelledMeters)) }} remaining</span></div>
            </div>
          </div>
          <dl class="train-detail-leg"><div><dt>From</dt><dd>{{ selectedTrain.from.name }} · {{ scheduleTime(selectedTrain.from.departure) }}</dd></div><div><dt>Next stop</dt><dd>{{ selectedTrain.to.name }} · {{ scheduleTime(selectedTrain.to.arrival) }}</dd></div><div><dt>Segment progress</dt><dd>{{ Math.round(selectedTrain.progress * 100) }}%</dd></div></dl>
          <div class="coordinates"><span>LAT <b>{{ selectedTrain.latitude.toFixed(5) }}</b></span><span>LON <b>{{ selectedTrain.longitude.toFixed(5) }}</b></span></div>
          <UCollapsible class="train-stop-details"><UButton color="neutral" variant="ghost" trailing-icon="i-lucide-chevron-down">{{ selectedTrain.stops.length }} scheduled stops</UButton><template #content><ol><li v-for="(stop, index) in selectedTrain.stops" :key="index"><span>{{ stop.name }}</span><time>{{ scheduleTime(stop.arrival) }}</time></li></ol></template></UCollapsible>
        </UCard>
        <div class="list-heading"><h2>Explore stations</h2></div>
        <UAlert v-if="error" class="data-error" color="warning" variant="soft" title="Station data is unavailable" description="Check that Trino and the lakehouse are running, then try again."><template #actions><UButton class="retry-button" @click="refresh()"><AppIcon name="refresh" :size="15" /> Try again</UButton></template></UAlert>
        <div v-else-if="status === 'pending'" class="station-list skeleton-list" role="status" aria-label="Loading stations"><div v-for="n in 6" :key="n" class="skeleton-row"><USkeleton class="h-3 w-4" /><USkeleton class="h-5 flex-1" /><USkeleton class="h-3 w-4" /></div></div>
        <div v-else-if="!stations.length" class="empty-list"><AppIcon name="pin" :size="24" /><h3>No stations available</h3></div>
        <div v-else class="station-list">
          <UButton v-for="(station, index) in stations" :key="station.key" class="station-row" :class="{ selected: selectedKey === station.key }" :aria-pressed="selectedKey === station.key" @click="selectStation(station)">
            <span class="station-rank">{{ String(index + 1).padStart(2, '0') }}</span><span class="station-info"><strong>{{ station.name }}</strong><span>{{ format(station.visits) }} scheduled visits</span></span><AppIcon name="arrow" :size="17" />
          </UButton>
        </div>
        <footer class="explorer-footer">Not live traffic</footer>
      </aside>

      <section class="map-panel" aria-label="Railway network map">
        <ClientOnly><StationMap ref="stationMap" :stations="stations" :selected-key="selectedKey" :selected-train-id="selectedTrain?.id" :follow-train="followTrain" @select="selectStation" @train-select="selectTrain" @timeline="timelineInstant = $event" /><template #fallback><div class="map-loading"><UIcon name="i-lucide-loader-circle" class="animate-spin size-5" aria-hidden="true" /> Preparing your map…</div></template></ClientOnly>
        <div class="map-topline"><div class="map-location"><AppIcon name="pin" :size="17" /><strong>France &amp; connections</strong><span class="location-separator">/</span><span>Station network</span></div></div>
        <div v-if="status === 'pending' && data" class="updating" role="status"><UIcon name="i-lucide-loader-circle" class="animate-spin size-5" aria-hidden="true" /> Updating stations…</div>
      </section>
    </main>
  </div>
</template>
