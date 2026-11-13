from pandas import DataFrame


def build_fact_stop_time(
    stop_times_df: DataFrame,
    trips_df: DataFrame,
    stops_df: DataFrame,
    dim_trip: DataFrame,
    dim_route: DataFrame,
    dim_station: DataFrame,
) -> DataFrame:
    """Resolve station visits to dimension keys; fail for unresolved keys."""
    trip_keys = dim_trip[["trip_id", "trip_key"]].copy()
    trip_routes = trips_df[["trip_id", "route_id"]].copy()
    trip_keys = trip_keys.merge(
        trip_routes, on="trip_id", how="left", validate="one_to_one"
    )
    route_keys = dim_route[["route_id", "route_key"]].copy()
    station_keys = dim_station[["station_id", "station_key"]].copy()
    stop_station_map = stops_df[["stop_id", "parent_station"]].copy()
    stop_station_map["station_id"] = stop_station_map["parent_station"].mask(
        stop_station_map["parent_station"].isna()
        | stop_station_map["parent_station"].eq(""),
        stop_station_map["stop_id"],
    )
    stop_station_map = stop_station_map.merge(
        station_keys, on="station_id", how="left", validate="many_to_one"
    )
    fact_stop_time = (
        stop_times_df.merge(trip_keys, on="trip_id", how="left", validate="many_to_one")
        .merge(route_keys, on="route_id", how="left", validate="many_to_one")
        .merge(
            stop_station_map[["stop_id", "station_key"]],
            on="stop_id", how="left", validate="many_to_one",
        )
    )
    for key in ["trip_key", "route_key", "station_key"]:
        if fact_stop_time[key].isna().any():
            raise ValueError(f"Unresolved {key} for {fact_stop_time[key].isna().sum()} stop visits")
        fact_stop_time[key] = fact_stop_time[key].astype("int64")

    fact_stop_time = fact_stop_time[
        ["trip_key", "route_key", "station_key", "arrival_time", "departure_time",
         "stop_sequence", "stop_headsign", "pickup_type", "drop_off_type"]
    ]
    return fact_stop_time
