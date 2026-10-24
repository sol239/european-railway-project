import pandas as pd
from pandas import DataFrame


def build_dim_routes(
    routes_df: DataFrame,
    agency_df: DataFrame,
    existing_dim: DataFrame | None = None,
) -> DataFrame:
    """Build routes with agency attributes and stable surrogate keys."""
    routes_df = routes_df[
        ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"]
    ].copy()

    routes_df["route_id"] = routes_df["route_id"].str.strip()
    routes_df["agency_id"] = routes_df["agency_id"].str.strip()
    routes_df["route_short_name"] = routes_df["route_short_name"].str.strip().str.lower()
    routes_df["route_long_name"] = routes_df["route_long_name"].str.strip().str.lower()

    routes_df = (
        routes_df.dropna(subset=["route_id"])
        .drop_duplicates(subset=["route_id"])
        .reset_index(drop=True)
    )

    routes_df["route_type"] = routes_df["route_type"].astype("Int64")

    if existing_dim is None:
        routes_df.insert(
            0,
            "route_key",
            range(1, len(routes_df) + 1),
        )

        dim_routes = routes_df.copy()

    else:
        dim_routes = existing_dim[["route_key", *routes_df.columns]].copy()

        new_routes: DataFrame = routes_df[
            ~routes_df["route_id"].isin(dim_routes["route_id"])
        ].copy()

        next_key = int(dim_routes["route_key"].max()) + 1 if not dim_routes.empty else 1

        new_routes.insert(
            0,
            "route_key",
            range(next_key, next_key + len(new_routes)),
        )

        dim_routes = pd.concat(
            [dim_routes, new_routes],
            ignore_index=True,
        )

        dim_routes = dim_routes.set_index("route_id")

        dim_routes.update(routes_df.set_index("route_id"))

        dim_routes = dim_routes.reset_index()

    dim_routes["route_key"] = dim_routes["route_key"].astype("int64")
    dim_routes = dim_routes[
        [
            "route_key",
            "route_id",
            "agency_id",
            "route_short_name",
            "route_long_name",
            "route_type",
        ]
    ]

    # Keep agency attributes in the route dimension for a star schema.
    agency_df = agency_df.astype("string").copy()
    for column in agency_df.columns:
        agency_df[column] = agency_df[column].str.strip()
    agency_df = agency_df.dropna(subset=["agency_id"]).drop_duplicates("agency_id")
    dim_routes = dim_routes.merge(
        agency_df, on="agency_id", how="left", validate="many_to_one", indicator=True
    )
    if dim_routes["_merge"].ne("both").any():
        raise ValueError("Routes without a matching source agency")
    dim_routes = dim_routes.drop(columns=["_merge"])

    return dim_routes
