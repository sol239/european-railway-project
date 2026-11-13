import { describe, expect, it } from 'vitest'
import { buildStationTimetable, stationTimetableQuery } from '../server/utils/station-timetable'

const visit = (overrides: Record<string, unknown> = {}) => ({
  service_date: '2026-11-13', trip_key: 8, stop_sequence: 2, first_sequence: 1, last_sequence: 3,
  arrival_time: '13:05:00', departure_time: '13:07:00', pickup_type: '0', drop_off_type: '0',
  origin: 'Poitiers', destination: 'La Rochelle', ...overrides,
})

describe('station timetable', () => {
  it('sorts arrivals and departures with their correct trip endpoints', () => {
    const result = buildStationTimetable(1, '2026-11-13', [visit(), visit({ trip_key: 9, arrival_time: '10:00:00', departure_time: '10:02:00' })])
    expect(result.arrivals.map(row => [row.time, row.station])).toEqual([[36000, 'Poitiers'], [47100, 'Poitiers']])
    expect(result.departures.map(row => [row.time, row.station])).toEqual([[36120, 'La Rochelle'], [47220, 'La Rochelle']])
  })
  it('places overnight services on the calendar day and excludes out-of-day times', () => {
    const result = buildStationTimetable(1, '2026-11-13', [
      visit({ service_date: '2026-11-12', arrival_time: '24:40:00', departure_time: '24:42:00' }),
      visit({ trip_key: 9, service_date: '2026-11-11', arrival_time: '48:10:00', departure_time: '48:12:00' }),
      visit({ trip_key: 10, arrival_time: '24:00:00', departure_time: '24:05:00' }),
      visit({ trip_key: 11, service_date: '2026-11-12', arrival_time: '23:50:00', departure_time: '23:55:00' }),
    ])
    expect(result.arrivals.map(row => row.time)).toEqual([600, 2400])
    expect(result.departures.map(row => row.time)).toEqual([720, 2520])
  })
  it('excludes terminal events, prohibited pickup and drop-off, and invalid times', () => {
    const result = buildStationTimetable(1, '2026-11-13', [
      visit({ trip_key: 1, stop_sequence: 1 }), visit({ trip_key: 2, stop_sequence: 3 }),
      visit({ trip_key: 3, pickup_type: '1' }), visit({ trip_key: 4, drop_off_type: '1' }),
      visit({ trip_key: 5, arrival_time: '13:99:00', departure_time: null }),
    ])
    expect(result.arrivals.map(row => row.id)).toEqual(['2026-11-13:2:3', '2026-11-13:3:2'])
    expect(result.departures.map(row => row.id)).toEqual(['2026-11-13:1:1', '2026-11-13:4:2'])
  })
  it('rejects invalid station keys and dates before building SQL', () => {
    expect(() => stationTimetableQuery(1, "2026-11-13' OR 1=1")).toThrow()
    expect(() => stationTimetableQuery(1.5, '2026-11-13')).toThrow()
    expect(() => stationTimetableQuery(-1, '2026-11-13')).toThrow()
    expect(stationTimetableQuery(543, '2026-11-13')).toContain('WHERE f.station_key = 543')
  })
})
