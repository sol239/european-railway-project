import { queryTrino } from '../utils/trino'
import { validServiceDate } from '../utils/station-query'
import type { TrainSchedule, ScheduledTrain } from '../../shared/types/train'

export default defineCachedEventHandler(async (event): Promise<TrainSchedule> => {
  let date: string | null
  try { date = validServiceDate(getQuery(event).date) } catch { throw createError({ statusCode: 400, statusMessage: 'Use a valid service date' }) }
  if (!date) throw createError({ statusCode: 400, statusMessage: 'A service date is required' })
  const config = useRuntimeConfig(event)
  try {
    // Include yesterday's services for GTFS times beyond 24:00:00.
    const rows = await queryTrino(`SELECT t.trip_key, t.trip_id, d.service_date, f.stop_sequence,
      f.arrival_time, f.departure_time, s.station_key, s.station_name, s.longitude, s.latitude
      FROM railway.gold.fact_stop_time f
      JOIN railway.gold.dim_trip t ON f.trip_key = t.trip_key
      JOIN railway.gold.fact_service_date d ON t.service_id = d.service_id
      JOIN railway.gold.dim_station s ON f.station_key = s.station_key
      WHERE d.service_date BETWEEN DATE '${date}' - INTERVAL '1' DAY AND DATE '${date}'
      AND s.latitude BETWEEN -90 AND 90 AND s.longitude BETWEEN -180 AND 180
      ORDER BY d.service_date, t.trip_key, CAST(f.stop_sequence AS INTEGER)`, { url: config.trinoUrl, user: config.trinoUser })
    const trains = new Map<string, ScheduledTrain>()
    function time(value: unknown) {
      const match = /^(\d+):(\d{2}):(\d{2})/.exec(String(value))
      return match ? Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) : NaN
    }
    for (const row of rows) {
      const offset = String(row.service_date) === date ? 0 : -86400
      const arrival = time(row.arrival_time) + offset
      const departure = time(row.departure_time) + offset
      if (!Number.isFinite(arrival) || !Number.isFinite(departure)) continue
      const id = `${row.service_date}:${row.trip_key}`
      if (!trains.has(id)) trains.set(id, { id, name: String(row.trip_id), stops: [] })
      trains.get(id)!.stops.push({ station: Number(row.station_key), name: String(row.station_name),
        longitude: Number(row.longitude), latitude: Number(row.latitude), arrival, departure })
    }
    return { date, trains: [...trains.values()].filter(t => t.stops.length > 1 && t.stops.at(-1)!.arrival >= 0 && t.stops[0]!.departure <= 86399) }
  } catch (error) {
    console.error('Train schedules unavailable', error instanceof Error ? error.message : error)
    throw createError({ statusCode: 503, statusMessage: 'Train schedules are unavailable' })
  }
}, { maxAge: 300, swr: false })
