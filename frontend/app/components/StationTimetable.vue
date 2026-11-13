<script setup lang="ts">
import type { Station } from '../../shared/types/station'
import type { TimelineInstant } from '../../shared/types/train'
import type { StationTimetable } from '../../shared/types/station-timetable'

const props = defineProps<{ station: Station; instant?: TimelineInstant }>()
const timetable = shallowRef<StationTimetable>()
const tab = ref<'departures' | 'arrivals'>('departures')
const showAll = ref(false)
const loading = ref(false), failed = ref(false)
let controller: AbortController | undefined

async function load() {
  controller?.abort()
  timetable.value = undefined
  failed.value = false
  const date = props.instant?.date
  if (!date) { loading.value = true; return }
  controller = new AbortController()
  const current = controller
  const station = props.station.key
  loading.value = true
  try {
    const result = await $fetch<StationTimetable>('/api/station-timetable', { query: { station, date }, signal: current.signal })
    if (controller === current && !current.signal.aborted) timetable.value = result
  } catch {
    if (controller === current && !current.signal.aborted) failed.value = true
  } finally {
    if (controller === current) loading.value = false
  }
}
watch([() => props.station.key, () => props.instant?.date], load, { immediate: true })
onBeforeUnmount(() => { controller?.abort(); controller = undefined })
const entries = computed(() => {
  const rows = timetable.value?.[tab.value] ?? []
  if (showAll.value) return rows
  const now = props.instant?.seconds ?? 0
  return rows.filter(entry => entry.time >= now)
})
const dateLabel = computed(() => {
  const date = props.instant?.date
  return date ? new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${date}T00:00:00Z`)) : ''
})
function time(seconds: number) {
  return `${String(Math.floor(seconds / 3600)).padStart(2, '0')}:${String(Math.floor(seconds / 60) % 60).padStart(2, '0')}`
}
</script>

<template>
  <section class="station-timetable" aria-label="Station timetable">
    <div class="station-timetable-heading"><h3>Timetable</h3><span>{{ dateLabel }}</span></div>
    <div class="station-timetable-toolbar">
      <div class="station-timetable-tabs" role="group" aria-label="Timetable type">
        <UButton :variant="tab === 'departures' ? 'solid' : 'ghost'" color="neutral" size="xs" :aria-pressed="tab === 'departures'" @click="tab = 'departures'">Departures</UButton>
        <UButton :variant="tab === 'arrivals' ? 'solid' : 'ghost'" color="neutral" size="xs" :aria-pressed="tab === 'arrivals'" @click="tab = 'arrivals'">Arrivals</UButton>
      </div>
      <UButton color="neutral" variant="ghost" size="xs" @click="showAll = !showAll">{{ showAll ? 'Show upcoming' : 'Show all day' }}</UButton>
    </div>
    <p v-if="loading" class="station-timetable-status" role="status">Loading timetable…</p>
    <div v-else-if="failed" class="station-timetable-status" role="alert">Timetable unavailable. <UButton color="neutral" variant="link" size="xs" @click="load">Try again</UButton></div>
    <p v-else-if="!entries.length" class="station-timetable-status">No {{ showAll ? '' : 'upcoming ' }}{{ tab }} for this date.</p>
    <ol v-else class="station-timetable-list" :aria-label="`${showAll ? 'All' : 'Upcoming'} ${tab}`">
      <li v-for="entry in entries" :key="entry.id"><time>{{ time(entry.time) }}</time><span><small>{{ tab === 'departures' ? 'To' : 'From' }}</small> {{ entry.station || 'Unknown station' }}</span></li>
    </ol>
    <p class="station-timetable-note">Scheduled times · {{ showAll ? 'all day' : 'from timeline time' }}</p>
  </section>
</template>
