from pandas import DataFrame


def build_fact_stop_times(
    stop_times_df: DataFrame,
    trips_df: DataFrame,
    stops_df: DataFrame,
    dim_trips: DataFrame,
    dim_routes: DataFrame,
    dim_station: DataFrame,
) -> DataFrame:
    """Resolve station visits to dimension keys; fail for unresolved keys."""
    stop_times_df = stop_times_df.drop(columns=["shape_dist_traveled"], errors="ignore").astype("string").copy()
    for column in stop_times_df.columns:
        stop_times_df[column] = stop_times_df[column].str.strip()

    trip_keys = dim_trips[["trip_id", "trip_key"]].copy()
    trip_routes = trips_df[["trip_id", "route_id"]].astype("string").copy()
    for column in trip_routes.columns:
        trip_routes[column] = trip_routes[column].str.strip()
    trip_routes = trip_routes.dropna(subset=["trip_id"]).drop_duplicates("trip_id")
    trip_keys = trip_keys.merge(
        trip_routes, on="trip_id", how="left", validate="one_to_one"
    )
    route_keys = dim_routes[["route_id", "route_key"]].copy()
    station_keys = dim_station[["station_id", "station_key"]].copy()
    stop_station_map = stops_df[["stop_id", "parent_station"]].astype("string").copy()
    for column in stop_station_map.columns:
        stop_station_map[column] = stop_station_map[column].str.strip()
    stop_station_map["station_id"] = stop_station_map["parent_station"].mask(
        stop_station_map["parent_station"].isna()
        | stop_station_map["parent_station"].eq(""),
        stop_station_map["stop_id"],
    )
    stop_station_map = stop_station_map.merge(
        station_keys, on="station_id", how="left", validate="many_to_one"
    )
    fact_stop_times = (
        stop_times_df.merge(trip_keys, on="trip_id", how="left", validate="many_to_one")
        .merge(route_keys, on="route_id", how="left", validate="many_to_one")
        .merge(
            stop_station_map[["stop_id", "station_key"]],
            on="stop_id", how="left", validate="many_to_one",
        )
    )
    for key in ["trip_key", "route_key", "station_key"]:
        if fact_stop_times[key].isna().any():
            raise ValueError(f"Unresolved {key} for {fact_stop_times[key].isna().sum()} stop visits")
        fact_stop_times[key] = fact_stop_times[key].astype("int64")

    fact_stop_times = fact_stop_times[
        ["trip_key", "route_key", "station_key", "arrival_time", "departure_time",
         "stop_sequence", "stop_headsign", "pickup_type", "drop_off_type"]
    ]
    return fact_stop_times
