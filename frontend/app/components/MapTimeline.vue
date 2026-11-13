<script setup lang="ts">
import type { TimelineInstant } from '../../shared/types/train'
const emit = defineEmits<{ change: [instant: TimelineInstant] }>()
const date = ref('')
const seconds = ref(0)
const live = ref(true)
const playing = ref(true)
let lastTick = 0
let elapsed = 0
let clock: ReturnType<typeof setInterval> | undefined
const timeLabel = computed(() => {
  const value = Math.round(seconds.value)
  return [Math.floor(value / 3600), Math.floor(value / 60) % 60, value % 60]
    .map(part => String(part).padStart(2, '0')).join(':')
})
function syncClock() {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Prague', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date())
  const get = (type: string) => parts.find(part => part.type === type)!.value
  date.value = `${get('year')}-${get('month')}-${get('day')}`
  seconds.value = Number(get('hour')) * 3600 + Number(get('minute')) * 60 + Number(get('second'))
}
watch([date, seconds, live], () => { if (date.value) emit('change', { date: date.value, seconds: seconds.value, live: live.value }) })
function pauseTimeline() {
  playing.value = false
  live.value = false
  elapsed = 0
}
function togglePlayback() {
  if (playing.value) { if (live.value) syncClock(); pauseTimeline(); return }
  lastTick = performance.now()
  elapsed = 0
  playing.value = true
}
function goLive() { live.value = true; playing.value = true; elapsed = 0; syncClock() }
function tick() {
  const now = performance.now()
  const delta = now - lastTick
  lastTick = now
  if (!playing.value) return
  if (live.value) { syncClock(); return }
  elapsed += delta
  const advance = Math.floor(elapsed / 1000)
  if (!advance) return
  elapsed -= advance * 1000
  const total = seconds.value + advance
  const days = Math.floor(total / 86400)
  if (days) {
    const day = new Date(`${date.value}T00:00:00Z`)
    day.setUTCDate(day.getUTCDate() + days)
    date.value = day.toISOString().slice(0, 10)
  }
  seconds.value = total % 86400
}
onMounted(() => {
  syncClock()
  lastTick = performance.now()
  clock = setInterval(tick, 250)
})
onBeforeUnmount(() => clearInterval(clock))
</script>

<template>
  <section class="map-timeline" aria-label="Map timeline">
    <div class="timeline-toolbar">
      <label class="timeline-date"><AppIcon name="calendar" :size="16" /><UInput v-model="date" type="date" aria-label="Timeline date" @input="pauseTimeline" /></label>
      <div class="timeline-clock"><time>{{ timeLabel }}</time><span>Europe/Prague</span></div>
      <UButton type="button" class="timeline-playback" :aria-label="playing ? 'Pause timeline' : 'Play timeline'" :title="playing ? 'Pause timeline' : 'Play timeline'" @click="togglePlayback"><UIcon :name="playing ? 'i-lucide-pause' : 'i-lucide-play'" /></UButton>
      <UButton type="button" class="timeline-live" :aria-pressed="live" @click="goLive"><i :class="{ active: live }" />{{ live ? 'Live' : 'Now' }}</UButton>
    </div>
    <USlider v-model="seconds" class="timeline-slider" :min="0" :max="86399" :step="1" aria-label="Timeline time" :aria-valuetext="timeLabel" @update:model-value="pauseTimeline" />
    <div class="timeline-ticks" aria-hidden="true"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div>
  </section>
</template>
