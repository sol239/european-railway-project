import pandas as pd
from pandas import DataFrame


def build_dim_trips(
    trips_df: DataFrame,
    existing_dim: DataFrame | None = None,
) -> DataFrame:
    """Build trip attributes, retaining keys and updating existing trips."""
    trips_df = trips_df.drop(columns=["shape_id", "route_id"], errors="ignore").astype("string").copy()

    for column in trips_df.columns:
        trips_df[column] = trips_df[column].str.strip()

    trips_df = (
        trips_df.dropna(subset=["trip_id"])
        .drop_duplicates(subset=["trip_id"])
        .reset_index(drop=True)
    )
    if existing_dim is None:
        dim_trips = trips_df.copy()
        dim_trips.insert(0, "trip_key", range(1, len(dim_trips) + 1))
    else:
        dim_trips = existing_dim.copy()
        new_trips = trips_df[~trips_df["trip_id"].isin(dim_trips["trip_id"])].copy()
        next_key = int(dim_trips["trip_key"].max()) + 1 if not dim_trips.empty else 1
        new_trips.insert(0, "trip_key", range(next_key, next_key + len(new_trips)))
        dim_trips = pd.concat([dim_trips, new_trips], ignore_index=True)
        dim_trips = dim_trips.set_index("trip_id")
        dim_trips.update(trips_df.set_index("trip_id"))
        dim_trips = dim_trips.reset_index()

    dim_trips["trip_key"] = dim_trips["trip_key"].astype("int64")
    dim_trips = dim_trips[["trip_key", *trips_df.columns]]
    return dim_trips
