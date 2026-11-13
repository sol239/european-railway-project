-- Shows scheduled trips at Strasbourg (station 543) on November 12, 2026.
SELECT
    fst.station_key,
    dt.trip_key,
    fsd.service_date,
    fst.arrival_time,
    fst.departure_time
FROM fact_stop_time fst
         JOIN dim_trip dt ON fst.trip_key = dt.trip_key
         JOIN fact_service_date fsd ON dt.service_id = fsd.service_id
WHERE fst.station_key = 543
  AND fsd.service_date = DATE '2026-11-12'
ORDER BY fst.arrival_time, fst.departure_time
