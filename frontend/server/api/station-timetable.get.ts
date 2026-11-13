import type { StationTimetable } from '../../shared/types/station-timetable'
import { queryTrino } from '../utils/trino'
import { validServiceDate } from '../utils/station-query'
import { buildStationTimetable, stationTimetableQuery } from '../utils/station-timetable'

export default defineCachedEventHandler(async (event): Promise<StationTimetable> => {
  const query = getQuery(event)
  const station = typeof query.station === 'string' && /^[1-9]\d*$/.test(query.station) ? Number(query.station) : NaN
  let date: string | null
  try {
    date = validServiceDate(query.date)
    if (!date || !Number.isSafeInteger(station) || station > 2147483647) throw new Error('Invalid station or date')
  } catch { throw createError({ statusCode: 400, statusMessage: 'Use a valid station and service date.' }) }
  const config = useRuntimeConfig(event)
  try {
    const rows = await queryTrino(stationTimetableQuery(station, date), { url: config.trinoUrl, user: config.trinoUser })
    return buildStationTimetable(station, date, rows)
  } catch (error) {
    console.error('Station timetable unavailable:', error instanceof Error ? error.message : 'Unknown error')
    throw createError({ statusCode: 503, statusMessage: 'Station timetable is unavailable.' })
  }
}, { maxAge: 300, swr: false })
