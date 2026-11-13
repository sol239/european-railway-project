-- Shows the busiest stations
SELECT
    fst.station_key,
    ds.station_name,
    COUNT(*) AS station_train_passes
FROM railway.gold.fact_stop_time fst
         JOIN railway.gold.dim_station ds ON fst.station_key = ds.station_key
GROUP BY fst.station_key, ds.station_name
ORDER BY station_train_passes DESC
