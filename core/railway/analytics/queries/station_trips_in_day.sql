-- Shows trips on the 24th October at the station-543 = Strasbourg
SELECT
    fst.station_key,
    dt.trip_key,
    fsd.service_date,
    fst.arrival_time,
    fst.departure_time
FROM fact_stop_time fst
         JOIN dim_trip dt USING (trip_key)
         JOIN fact_service_date fsd USING (service_id)
WHERE fst.station_key = 543
  AND fsd.service_date = '2026-10-24';