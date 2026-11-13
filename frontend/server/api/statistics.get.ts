import type { ScheduleStatistics } from '../../shared/types/statistics'
import { queryTrino } from '../utils/trino'

export default defineCachedEventHandler(async (event): Promise<ScheduleStatistics> => {
  const config = useRuntimeConfig(event)
  const options = { url: config.trinoUrl, user: config.trinoUser }
  try {
    const [totals, busiest] = await Promise.all([
      queryTrino(`SELECT
        (SELECT count(*) FROM railway.gold.dim_station) AS stations,
        (SELECT count(*) FROM railway.gold.dim_station WHERE latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180) AS mapped_stations,
        (SELECT count(*) FROM railway.gold.dim_trip) AS trips,
        (SELECT count(*) FROM railway.gold.dim_route) AS routes,
        (SELECT count(*) FROM railway.gold.fact_stop_time) AS stop_visits,
        (SELECT min(service_date) FROM railway.gold.fact_service_date) AS first_date,
        (SELECT max(service_date) FROM railway.gold.fact_service_date) AS last_date`, options),
      queryTrino(`SELECT s.station_key, s.station_name, count(*) AS visits
        FROM railway.gold.fact_stop_time f
        JOIN railway.gold.dim_station s ON f.station_key = s.station_key
        GROUP BY s.station_key, s.station_name
        ORDER BY visits DESC, s.station_key LIMIT 5`, options),
    ])
    const row = totals[0]
    if (!row) throw new Error('Statistics query returned no totals')
    return {
      stations: Number(row.stations), mappedStations: Number(row.mapped_stations),
      trips: Number(row.trips), routes: Number(row.routes), stopVisits: Number(row.stop_visits),
      coverage: { firstDate: row.first_date ? String(row.first_date) : null, lastDate: row.last_date ? String(row.last_date) : null },
      busiestStations: busiest.map(station => ({ key: Number(station.station_key), name: String(station.station_name), visits: Number(station.visits) })),
    }
  } catch (error) {
    console.error('Statistics unavailable:', error instanceof Error ? error.message : 'Unknown error')
    throw createError({ statusCode: 503, statusMessage: 'Schedule statistics are unavailable.' })
  }
}, { maxAge: 60, swr: false })
