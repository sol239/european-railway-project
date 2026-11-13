<script setup lang="ts">
import type { RailStatistics, ScheduleStatistics } from '../../shared/types/statistics'

useHead({ title: 'Railway Atlas · Statistics' })
const { data: schedule, status: scheduleStatus, error: scheduleError, refresh: refreshSchedule } = await useFetch<ScheduleStatistics>('/api/statistics', { lazy: true })
const { data: rail, status: railStatus, error: railError, refresh: refreshRail } = await useFetch<RailStatistics>('/api/rail-statistics', { lazy: true })
const number = (value: number) => new Intl.NumberFormat('en-GB').format(value)
const date = (value: string) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`))
const maxVisits = computed(() => schedule.value?.busiestStations[0]?.visits || 1)
</script>

<template>
  <div class="atlas-app stats-app">
    <AppHeader />
    <main class="statistics-page">
      <div class="statistics-content">
        <div class="statistics-intro">
          <div><p class="stats-eyebrow"><span /> NETWORK OVERVIEW</p><h1>Railway statistics<span>.</span></h1><p class="stats-lede">A closer look at the stations, journeys and infrastructure in the network.</p></div>
          <NuxtLink to="/map" class="stats-map-link">Explore the map <AppIcon name="arrow" :size="16" /></NuxtLink>
        </div>

        <UAlert v-if="scheduleError" class="stats-alert" color="warning" variant="soft" title="Schedule statistics are unavailable" description="Check the data connection and try again."><template #actions><UButton class="retry-button" @click="refreshSchedule()">Try again</UButton></template></UAlert>
        <section class="stats-metrics" aria-label="Network totals">
          <article class="metric-card"><div class="metric-top"><span>STATIONS</span><UIcon name="i-lucide-map-pin" /></div><strong>{{ schedule ? number(schedule.stations) : scheduleStatus === 'pending' ? '—' : 'Unavailable' }}</strong><p>{{ schedule ? `${number(schedule.mappedStations)} with map coordinates` : 'Stations in the schedule' }}</p></article>
          <article class="metric-card"><div class="metric-top"><span>SCHEDULED TRIPS</span><UIcon name="i-lucide-train-front" /></div><strong>{{ schedule ? number(schedule.trips) : scheduleStatus === 'pending' ? '—' : 'Unavailable' }}</strong><p>Distinct trips in the timetable</p></article>
          <article class="metric-card"><div class="metric-top"><span>OPERATING RAIL LENGTH</span><UIcon name="i-lucide-route" /></div><strong>{{ rail ? number(Math.round(rail.operatingLengthMeters / 1000)) : railStatus === 'pending' ? '—' : 'Unavailable' }}<small v-if="rail"> km</small></strong><p>Estimated sum of operating rail geometry</p><button v-if="railError" class="stats-retry" @click="refreshRail()">Retry rail data</button></article>
          <article class="metric-card"><div class="metric-top"><span>ROUTES</span><UIcon name="i-lucide-git-branch" /></div><strong>{{ schedule ? number(schedule.routes) : scheduleStatus === 'pending' ? '—' : 'Unavailable' }}</strong><p>Routes in the timetable</p></article>
        </section>

        <div class="stats-details">
          <section class="stats-panel busiest-panel" aria-labelledby="busiest-heading">
            <div class="stats-panel-heading"><div><p class="stats-eyebrow">SCHEDULE ACTIVITY</p><h2 id="busiest-heading">Busiest stations</h2><p>By scheduled stop visits across the timetable</p></div><span class="stats-panel-icon"><UIcon name="i-lucide-bar-chart-3" /></span></div>
            <div v-if="schedule?.busiestStations.length" class="busiest-list">
              <div v-for="(station, index) in schedule.busiestStations" :key="station.key" class="busiest-row"><span class="busiest-rank">{{ String(index + 1).padStart(2, '0') }}</span><div class="busiest-info"><div><strong>{{ station.name }}</strong><span>{{ number(station.visits) }} visits</span></div><div class="busiest-track"><span :style="{ width: `${station.visits / maxVisits * 100}%` }" /></div></div></div>
            </div>
            <p v-else class="stats-empty">{{ scheduleStatus === 'pending' ? 'Loading stations…' : scheduleError ? 'Station activity is unavailable.' : 'No station visits available.' }}</p>
          </section>
          <section class="stats-panel snapshot-panel" aria-labelledby="snapshot-heading">
            <div class="stats-panel-heading"><div><p class="stats-eyebrow">ABOUT THE DATA</p><h2 id="snapshot-heading">Data snapshot</h2><p>The numbers behind the overview</p></div><span class="stats-panel-icon"><UIcon name="i-lucide-database" /></span></div>
            <dl class="snapshot-list"><div><dt>Scheduled stop visits</dt><dd>{{ schedule ? number(schedule.stopVisits) : '—' }}</dd></div><div><dt>Operating rail segments</dt><dd>{{ rail ? number(rail.operatingSegments) : '—' }}</dd></div><div><dt>Service dates</dt><dd v-if="schedule?.coverage.firstDate && schedule.coverage.lastDate">{{ date(schedule.coverage.firstDate) }} – {{ date(schedule.coverage.lastDate) }}</dd><dd v-else>—</dd></div></dl>
            <div class="stats-note"><UIcon name="i-lucide-info" /><p>Trip and stop totals describe the schedule, without expanding trips over service dates. Rail length sums operating RFN feature geometry; overlapping features may be counted more than once. It is not a sum of trip distances.</p></div>
          </section>
        </div>
      </div>
    </main>
  </div>
</template>
