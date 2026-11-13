"""Pure source-domain cleaning; no warehouse keys or dimensional joins."""

from pandas import DataFrame, to_numeric

SOURCE_TABLES = (
    "agency", "routes", "stops", "trips", "stop_times", "calendar_dates", "calendar",
)


def clean_source(name: str, frame: DataFrame) -> DataFrame:
    """Standardize a GTFS table while retaining source IDs and useful attributes."""
    if name not in SOURCE_TABLES:
        raise ValueError(f"Unsupported Silver dataset: {name}")
    result = frame.astype("string").copy()
    for column in result.columns:
        result[column] = result[column].str.strip()
    if name == "routes":
        for column in ("route_short_name", "route_long_name"):
            result[column] = result[column].str.lower()
        result["route_type"] = result["route_type"].astype("Int64")
    elif name == "stops":
        # Retain both stations and platforms, including their parent relationship.
        result["stop_name"] = result["stop_name"].str.lower()
        for source, target, limit in (
            ("stop_lat", "latitude", 90), ("stop_lon", "longitude", 180),
        ):
            values = to_numeric(result.get(source, result.get(target)), errors="coerce")
            result[target] = values
            result[target] = result[target].astype("Float64")
            result[target] = result[target].where(result[target].between(-limit, limit))

    identifiers = {
        "agency": "agency_id", "routes": "route_id", "stops": "stop_id", "trips": "trip_id",
    }
    if name in identifiers:
        identifier = identifiers[name]
        result = result.dropna(subset=[identifier]).drop_duplicates(identifier)
    # Calendar exceptions are not deduplicated: conflicting exceptions must fail in Gold.
    # Stop visits retain their original grain and GTFS times (including hours >= 24).
    return result.reset_index(drop=True)
