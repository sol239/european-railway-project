export function validServiceDate(value: unknown): string | null {
  if (value === undefined || value === '') return null
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Use a service date in YYYY-MM-DD format')
  const date = new Date(`${value}T00:00:00Z`)
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) throw new Error('Invalid service date')
  return value
}

export function stationQuery(date: string | null): string {
  // Keep this utility safe even when called outside the API handler.
  const serviceDate = validServiceDate(date ?? undefined)
  const filter = serviceDate ? `WHERE EXISTS (
    SELECT 1 FROM railway.gold.dim_trip t
    JOIN railway.gold.fact_service_date d ON t.service_id = d.service_id
    WHERE t.trip_key = f.trip_key AND d.service_date = DATE '${serviceDate}'
  )` : ''
  return `WITH visits AS (
    SELECT f.station_key, count(*) AS visits
    FROM railway.gold.fact_stop_time f
    ${filter}
    GROUP BY f.station_key
  )
  SELECT s.station_key, s.station_name, s.latitude, s.longitude, coalesce(v.visits, 0) AS visits
  FROM railway.gold.dim_station s
  LEFT JOIN visits v ON s.station_key = v.station_key
  WHERE s.latitude BETWEEN -90 AND 90 AND s.longitude BETWEEN -180 AND 180
  ORDER BY visits DESC, s.station_key`
}
