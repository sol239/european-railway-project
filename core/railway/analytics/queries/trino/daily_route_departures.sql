-- Counts scheduled trips for each route and active service date.
-- Each trip is counted once per date, regardless of its number of stops.
-- Only trips with at least one recorded stop are included.
-- Add WHERE r.route_type = 2 to restrict results to rail services.
WITH trip_routes AS (
    SELECT DISTINCT trip_key, route_key FROM railway.gold.fact_stop_time
)
SELECT r.route_key, r.route_short_name, r.route_long_name,
       s.service_date, COUNT(*) AS scheduled_departures
FROM railway.gold.dim_trip AS t
JOIN railway.gold.fact_service_date AS s ON t.service_id = s.service_id
JOIN trip_routes AS tr ON t.trip_key = tr.trip_key
JOIN railway.gold.dim_route AS r ON tr.route_key = r.route_key
GROUP BY r.route_key, r.route_short_name, r.route_long_name, s.service_date
ORDER BY s.service_date, r.route_key
