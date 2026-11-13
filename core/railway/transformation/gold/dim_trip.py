import pandas as pd
from pandas import DataFrame


def build_dim_trip(
    trips_df: DataFrame,
    existing_dim: DataFrame | None = None,
) -> DataFrame:
    """Build trip attributes, retaining keys and updating existing trips."""
    trips_df = trips_df.drop(columns=["shape_id", "route_id"], errors="ignore").copy()

    if existing_dim is None:
        dim_trip = trips_df.copy()
        dim_trip.insert(0, "trip_key", range(1, len(dim_trip) + 1))
    else:
        dim_trip = existing_dim.copy()
        new_trips = trips_df[~trips_df["trip_id"].isin(dim_trip["trip_id"])].copy()
        next_key = int(dim_trip["trip_key"].max()) + 1 if not dim_trip.empty else 1
        new_trips.insert(0, "trip_key", range(next_key, next_key + len(new_trips)))
        dim_trip = pd.concat([dim_trip, new_trips], ignore_index=True)
        dim_trip = dim_trip.set_index("trip_id")
        dim_trip.update(trips_df.set_index("trip_id"))
        dim_trip = dim_trip.reset_index()

    dim_trip["trip_key"] = dim_trip["trip_key"].astype("int64")
    dim_trip = dim_trip[["trip_key", *trips_df.columns]]
    return dim_trip
