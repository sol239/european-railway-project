import pandas as pd
from pandas import DataFrame


def build_dim_route(
    routes_df: DataFrame,
    agency_df: DataFrame,
    existing_dim: DataFrame | None = None,
) -> DataFrame:
    """Build routes with agency attributes and stable surrogate keys."""
    routes_df = routes_df[
        ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"]
    ].copy()

    if existing_dim is None:
        routes_df.insert(
            0,
            "route_key",
            range(1, len(routes_df) + 1),
        )

        dim_route = routes_df.copy()

    else:
        dim_route = existing_dim[["route_key", *routes_df.columns]].copy()

        new_routes: DataFrame = routes_df[
            ~routes_df["route_id"].isin(dim_route["route_id"])
        ].copy()

        next_key = int(dim_route["route_key"].max()) + 1 if not dim_route.empty else 1

        new_routes.insert(
            0,
            "route_key",
            range(next_key, next_key + len(new_routes)),
        )

        if not new_routes.empty:
            dim_route = pd.concat(
                [dim_route, new_routes],
                ignore_index=True,
            )

        dim_route = dim_route.set_index("route_id")

        dim_route.update(routes_df.set_index("route_id"))

        dim_route = dim_route.reset_index()

    dim_route["route_key"] = dim_route["route_key"].astype("int64")
    dim_route = dim_route[
        [
            "route_key",
            "route_id",
            "agency_id",
            "route_short_name",
            "route_long_name",
            "route_type",
        ]
    ]

    if not routes_df["agency_id"].isin(agency_df["agency_id"]).all():
        raise ValueError("Routes without a matching source agency")
    if existing_dim is not None:
        agency_columns = list(agency_df.columns)
        agency_df = pd.concat(
            [agency_df, existing_dim.reindex(columns=agency_columns)], ignore_index=True
        ).drop_duplicates("agency_id")
    dim_route = dim_route.merge(
        agency_df, on="agency_id", how="left", validate="many_to_one", indicator=True
    )
    if dim_route["_merge"].ne("both").any():
        raise ValueError("Routes without a matching source agency")
    dim_route = dim_route.drop(columns=["_merge"])

    dim_route["route_type"] = dim_route["route_type"].astype("Int64")
    return dim_route
