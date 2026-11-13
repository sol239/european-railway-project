"""Build the factless fact of active GTFS services by date."""

import pandas as pd
from pandas import DataFrame


def build_fact_service_date(
    calendar_dates_df: DataFrame | None = None,
    calendar_df: DataFrame | None = None,
) -> DataFrame:
    """Return one row per active (service_id, service_date), without trip expansion."""
    if calendar_dates_df is None and calendar_df is None:
        raise ValueError("A calendar or calendar_dates source is required")

    active: set[tuple[str, pd.Timestamp]] = set()
    weekdays = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    if calendar_df is not None:
        calendar = calendar_df.copy()
        if (
            calendar["service_id"].isna().any()
            or calendar["service_id"].duplicated().any()
        ):
            raise ValueError("calendar requires unique, non-null service_id values")
        for row in calendar.to_dict("records"):
            if any(pd.isna(row[day]) or row[day] not in ("0", "1") for day in weekdays):
                raise ValueError("Calendar weekday flags must be 0 or 1")
            start = pd.to_datetime(row["start_date"], format="%Y%m%d", errors="raise")
            end = pd.to_datetime(row["end_date"], format="%Y%m%d", errors="raise")
            if pd.isna(start) or pd.isna(end) or start > end:
                raise ValueError("Invalid calendar date range")
            for date in pd.date_range(start, end):
                if row[weekdays[date.day_of_week]] == "1":
                    active.add((row["service_id"], date))

    if calendar_dates_df is not None:
        exceptions = calendar_dates_df[["service_id", "date", "exception_type"]].copy()
        if exceptions.isna().any().any() or exceptions["service_id"].eq("").any():
            raise ValueError("Calendar exceptions must not contain missing values")
        if not exceptions["exception_type"].isin(["1", "2"]).all():
            raise ValueError("Calendar exception_type must be 1 or 2")
        exceptions["date"] = pd.to_datetime(
            exceptions["date"], format="%Y%m%d", errors="raise"
        )
        if exceptions.duplicated(["service_id", "date"]).any():
            raise ValueError("Duplicate calendar exception for service_id and date")
        for service_id, date, exception_type in exceptions.itertuples(
            index=False, name=None
        ):
            if exception_type == "1":
                active.add((service_id, date))
            else:
                active.discard((service_id, date))

    result = DataFrame(sorted(active), columns=["service_id", "service_date"])
    result["service_id"] = result["service_id"].astype("string")
    result["service_date"] = pd.to_datetime(result["service_date"]).dt.date
    return result
