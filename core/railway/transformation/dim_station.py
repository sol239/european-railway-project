import pandas as pd
from pandas import DataFrame


def build_dim_station(
    stops_df: DataFrame,
    existing_dim: DataFrame | None = None,
) -> DataFrame:
    """Build station areas, retaining existing keys and updating names."""
    stops_df = stops_df[["stop_id", "stop_name"]].copy()
    stops_df = stops_df[stops_df["stop_id"].str.startswith("StopArea:", na=False)]
    stops_df = stops_df.rename(
        columns={"stop_id": "station_id", "stop_name": "station_name"}
    )
    stops_df["station_id"] = stops_df["station_id"].str.strip()
    stops_df["station_name"] = stops_df["station_name"].str.strip().str.lower()
    stops_df = (
        stops_df.dropna(subset=["station_id", "station_name"])
        .drop_duplicates(subset=["station_id"])
        .reset_index(drop=True)
    )

    if existing_dim is None:
        dim_station = stops_df.copy()
        dim_station.insert(0, "station_key", range(1, len(dim_station) + 1))
    else:
        dim_station = existing_dim.copy()
        new_stations = stops_df[~stops_df["station_id"].isin(dim_station["station_id"])].copy()
        next_key = int(dim_station["station_key"].max()) + 1 if not dim_station.empty else 1
        new_stations.insert(0, "station_key", range(next_key, next_key + len(new_stations)))
        dim_station = pd.concat([dim_station, new_stations], ignore_index=True)
        dim_station = dim_station.set_index("station_id")
        dim_station.update(stops_df.set_index("station_id")[["station_name"]])
        dim_station = dim_station.reset_index()

    dim_station["station_key"] = dim_station["station_key"].astype("int64")
    return dim_station[["station_key", "station_id", "station_name"]]
