-- One scheduled trip per active service date; stops must not multiply counts.
-- Filter dim_route.route_type = 2 when restricting this to rail services.
WITH trip_routes AS (
    SELECT DISTINCT trip_key, route_key FROM fact_stop_time
)
SELECT r.route_key, r.route_short_name, r.route_long_name,
       s.service_date, COUNT(*) AS scheduled_departures
FROM dim_trip AS t
JOIN fact_service_date AS s USING (service_id)
JOIN trip_routes AS tr USING (trip_key)
JOIN dim_route AS r USING (route_key)
GROUP BY r.route_key, r.route_short_name, r.route_long_name, s.service_date
ORDER BY s.service_date, r.route_key;
