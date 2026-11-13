import type { StationTimetable, StationTimetableEntry } from '../../shared/types/station-timetable'
import { validServiceDate } from './station-query'

export function stationTimetableQuery(station: number, date: string): string {
  if (!Number.isSafeInteger(station) || station < 1 || station > 2147483647 || !validServiceDate(date)) throw new Error('Invalid station or date')
  return `WITH station_trips AS (
    SELECT DISTINCT trip_key FROM railway.gold.fact_stop_time WHERE station_key = ${station}
  ), endpoints AS (
    SELECT f.trip_key, min_by(s.station_name, CAST(f.stop_sequence AS INTEGER)) AS origin,
      max_by(s.station_name, CAST(f.stop_sequence AS INTEGER)) AS destination,
      min(CAST(f.stop_sequence AS INTEGER)) AS first_sequence,
      max(CAST(f.stop_sequence AS INTEGER)) AS last_sequence
    FROM railway.gold.fact_stop_time f
    JOIN station_trips st ON st.trip_key = f.trip_key
    JOIN railway.gold.dim_station s ON s.station_key = f.station_key
    GROUP BY f.trip_key
  ), dates AS (
    SELECT DISTINCT service_id, service_date FROM railway.gold.fact_service_date
    WHERE service_date BETWEEN DATE '${date}' - INTERVAL '2' DAY AND DATE '${date}'
  )
  SELECT f.trip_key, f.stop_sequence, f.arrival_time, f.departure_time, f.pickup_type, f.drop_off_type,
    d.service_date, e.origin, e.destination, e.first_sequence, e.last_sequence
  FROM railway.gold.fact_stop_time f
  JOIN railway.gold.dim_trip t ON f.trip_key = t.trip_key
  JOIN dates d ON t.service_id = d.service_id
  JOIN endpoints e ON f.trip_key = e.trip_key
  WHERE f.station_key = ${station}`
}

function seconds(value: unknown): number | null {
  const match = /^(\d+):([0-5]\d):([0-5]\d)$/.exec(String(value ?? ''))
  return match ? Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) : null
}

export function buildStationTimetable(station: number, date: string, rows: Record<string, unknown>[]): StationTimetable {
  const arrivals: StationTimetableEntry[] = [], departures: StationTimetableEntry[] = []
  const selectedDay = Date.parse(`${date}T00:00:00Z`)
  for (const row of rows) {
    const day = Date.parse(`${String(row.service_date).slice(0, 10)}T00:00:00Z`)
    if (!Number.isFinite(day)) continue
    const offset = (day - selectedDay) / 1000
    const sequence = Number(row.stop_sequence)
    const id = `${row.service_date}:${row.trip_key}:${row.stop_sequence}`
    const arrival = seconds(row.arrival_time), departure = seconds(row.departure_time)
    if (arrival !== null && arrival + offset >= 0 && arrival + offset < 86400
      && sequence > Number(row.first_sequence) && String(row.drop_off_type ?? '') !== '1') {
      arrivals.push({ id, time: arrival + offset, station: String(row.origin ?? '') })
    }
    if (departure !== null && departure + offset >= 0 && departure + offset < 86400
      && sequence < Number(row.last_sequence) && String(row.pickup_type ?? '') !== '1') {
      departures.push({ id, time: departure + offset, station: String(row.destination ?? '') })
    }
  }
  const sort = (a: StationTimetableEntry, b: StationTimetableEntry) => a.time - b.time || a.id.localeCompare(b.id)
  return { station, date, arrivals: arrivals.sort(sort), departures: departures.sort(sort) }
}
