import type { StationResponse } from '../../shared/types/station'
import { queryTrino } from '../utils/trino'
import { validServiceDate, stationQuery } from '../utils/station-query'

export default defineCachedEventHandler(async (event): Promise<StationResponse> => {
  let date: string | null
  try { date = validServiceDate(getQuery(event).date) }
  catch { throw createError({ statusCode: 400, statusMessage: 'Use a valid service date in YYYY-MM-DD format' }) }
  const config = useRuntimeConfig(event)
  const options = { url: config.trinoUrl, user: config.trinoUser }
  try {
    const [rows, coverage] = await Promise.all([
      queryTrino(stationQuery(date), options),
      queryTrino('SELECT min(service_date) AS first_date, max(service_date) AS last_date FROM railway.gold.fact_service_date', options),
    ])
    return {
      stations: rows.map(row => ({
        key: Number(row.station_key), name: String(row.station_name),
        latitude: Number(row.latitude), longitude: Number(row.longitude), visits: Number(row.visits),
      })),
      coverage: {
        firstDate: coverage[0]?.first_date ? String(coverage[0].first_date) : null,
        lastDate: coverage[0]?.last_date ? String(coverage[0].last_date) : null,
      },
      selectedDate: date,
      updatedAt: new Date().toISOString(),
    }
  } catch (error) {
    console.error('Station data unavailable:', error instanceof Error ? error.message : 'Unknown error')
    throw createError({ statusCode: 503, statusMessage: 'Station data is unavailable. Check that Trino and the lakehouse are running.' })
  }
}, { maxAge: 60, swr: false })
