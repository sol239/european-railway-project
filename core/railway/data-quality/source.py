"""Compact, configuration-driven source GTFS validation (DQ1–DQ19, DQ21–DQ27, DQ29–DQ36)."""
from datetime import date, datetime, timedelta
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo

import pandas as pd


class DataQualityError(ValueError):
    """A critical GTFS source quality rule failed."""


# DQ2–DQ6: project-required columns (not necessarily GTFS-required columns).
SCHEMAS = {
    "agency": (2, ("agency_id",)),
    "routes": (3, ("route_id", "agency_id", "route_short_name", "route_long_name", "route_type")),
    "stops": (4, ("stop_id", "stop_name")),
    "trips": (5, ("trip_id", "route_id")),
    "stop_times": (6, ("trip_id", "stop_id", "arrival_time", "departure_time",
                        "stop_sequence", "stop_headsign", "pickup_type", "drop_off_type")),
}

# DQ7–DQ10: uniqueness checks on the original GTFS files.
UNIQUE = [(7, "agency", "agency_id"), (8, "routes", "route_id"),
          (9, "stops", "stop_id"), (10, "trips", "trip_id")]

# DQ12–DQ19, DQ21–DQ27, DQ29–DQ31: strictly more than 99% populated, as in original code.
COMPLETE = [
    (12, "agency", "agency_id"),
    (13, "routes", "route_id"), (14, "routes", "agency_id"),
    (15, "routes", "route_short_name"), (16, "routes", "route_long_name"),
    (17, "routes", "route_type"), (18, "stops", "stop_id"),
    (19, "stops", "stop_name"), (21, "trips", "trip_id"),
    (22, "trips", "route_id"), (23, "stop_times", "trip_id"),
    (24, "stop_times", "stop_id"), (25, "stop_times", "arrival_time"),
    (26, "stop_times", "departure_time"), (27, "stop_times", "stop_sequence"),
    (29, "stop_times", "pickup_type"),
    (30, "stop_times", "drop_off_type"), (31, "feed_info", "feed_version"),
]

# DQ33–DQ36: (rule, child file, foreign key, parent file, referenced key).
REFERENCES = [
    (33, "routes", "agency_id", "agency", "agency_id"),
    (34, "trips", "route_id", "routes", "route_id"),
    (35, "stop_times", "trip_id", "trips", "trip_id"),
    (36, "stop_times", "stop_id", "stops", "stop_id"),
]


def check_required_files(archive_path: Path) -> None:
    """DQ1: Require source GTFS files at the ZIP root."""
    try:
        with ZipFile(archive_path) as archive:
            names = {entry.filename for entry in archive.infolist() if not entry.is_dir()}
    except (OSError, BadZipFile) as exc:
        raise DataQualityError(f"DQ1: Cannot read {archive_path}: {exc}") from exc
    missing = sorted({f"{name}.txt" for name in SCHEMAS} - names)
    if missing:
        raise DataQualityError(f"DQ1: {archive_path}: missing files {missing}")


def read_frame(path: Path, rule: int) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype="string", keep_default_na=False, skip_blank_lines=False)
    except (OSError, ValueError, UnicodeError, pd.errors.ParserError) as exc:
        raise DataQualityError(f"DQ{rule}: Cannot read {path}: {exc}") from exc


def column_values(df: pd.DataFrame, column: str, rule: int, path: Path) -> pd.Series:
    if column not in df.columns:
        raise DataQualityError(f"DQ{rule}: {path}: missing column {column}")
    if df.empty:
        raise DataQualityError(f"DQ{rule}: {path}: table is empty")
    values = df[column].str.strip()
    return values.mask(values.eq(""))


def fail_invalid(rule: int, label: str, values: pd.Series, invalid: pd.Series) -> None:
    count = int(invalid.sum())
    if count:
        samples = values[invalid].drop_duplicates().head(5).fillna("<missing>").tolist()
        raise DataQualityError(
            f"DQ{rule}: {label}: invalid_rows={count}, "
            f"total_rows={len(values)}, sample_values={samples}"
        )


def check_schema(df: pd.DataFrame, path: Path, rule: int, columns: tuple[str, ...]) -> None:
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise DataQualityError(f"DQ{rule}: {path}: missing columns {missing}")
    if df.empty:
        raise DataQualityError(f"DQ{rule}: {path}: table is empty")


def check_unique(df: pd.DataFrame, path: Path, rule: int, column: str) -> None:
    values = column_values(df, column, rule, path)
    duplicates = values.notna() & values.duplicated(keep=False)
    fail_invalid(rule, f"{path}.{column}", values, duplicates)


def check_complete(df: pd.DataFrame, path: Path, rule: int, column: str) -> None:
    values = column_values(df, column, rule, path)
    present = int(values.notna().sum())
    total = len(values)
    if present * 100 <= total * 99:
        raise DataQualityError(
            f"DQ{rule}: {path}.{column}: missing_count={total - present}, "
            f"total_rows={total}, non_nullness_percent={100 * present / total:.6f}; required > 99%"
        )


def check_reference(child: pd.DataFrame, parent: pd.DataFrame, child_path: Path,
                    parent_path: Path, rule: int, fk: str, pk: str) -> None:
    source = column_values(child, fk, rule, child_path)
    target = column_values(parent, pk, rule, parent_path)
    invalid = source.notna() & ~source.isin(target.dropna())
    fail_invalid(rule, f"{child_path}.{fk} -> {parent_path}.{pk}", source, invalid)


def check_feed_timeliness(df: pd.DataFrame, path: Path, today: date) -> None:
    """DQ11: Feed version must be an ISO date within the last two calendar days."""
    values = column_values(df, "feed_version", 11, path)
    invalid = []
    for value in values:
        try:
            parsed = date.fromisoformat(value)
            valid = parsed.isoformat() == value and today - timedelta(days=2) <= parsed <= today
        except (ValueError, TypeError):
            valid = False
        invalid.append(not valid)
    fail_invalid(11, f"{path}.feed_version", values, pd.Series(invalid, index=values.index))


def check_station_prefixes(df: pd.DataFrame, path: Path) -> None:
    """DQ32: SNCF stop IDs use StopArea: or StopPoint: prefixes."""
    values = column_values(df, "stop_id", 32, path)
    invalid = ~values.str.fullmatch(r"(?:StopArea|StopPoint):\s*\S.*", na=False)
    fail_invalid(32, f"{path}.stop_id", values, invalid)


def validate_source(archive_path: Path, staging_dir: Path,
                    current_date: date | None = None) -> None:
    """Run configured source checks, aggregate failures, and block downstream tasks."""
    failures: list[str] = []
    cache: dict[Path, pd.DataFrame | DataQualityError] = {}

    def run(check, *args) -> None:
        try:
            check(*args)
        except DataQualityError as exc:
            failures.append(str(exc))

    def frame(name: str, extension: str, rule: int) -> pd.DataFrame:
        path = staging_dir / f"{name}.{extension}"
        if path not in cache:
            try:
                cache[path] = read_frame(path, rule)
            except DataQualityError as exc:
                cache[path] = exc
        result = cache[path]
        if isinstance(result, DataQualityError):
            raise DataQualityError(f"DQ{rule}: Cannot read {path}: {result}") from result
        return result

    def apply(check, rule: int, datasets: tuple[tuple[str, str], ...], *args) -> None:
        try:
            loaded = [frame(name, ext, rule) for name, ext in datasets]
            check(*loaded, *args)
        except DataQualityError as exc:
            failures.append(str(exc))

    run(check_required_files, archive_path)
    for name, (rule, columns) in SCHEMAS.items():
        path = staging_dir / f"{name}.txt"
        apply(lambda df, p=path, r=rule, c=columns: check_schema(df, p, r, c),
              rule, ((name, "txt"),))

    for rule, name, column in UNIQUE:
        path = staging_dir / f"{name}.txt"
        apply(lambda df, p=path, r=rule, c=column: check_unique(df, p, r, c),
              rule, ((name, "txt"),))

    today = current_date or datetime.now(ZoneInfo("Europe/Prague")).date()
    path = staging_dir / "feed_info.csv"
    apply(lambda df: check_feed_timeliness(df, path, today), 11, (("feed_info", "csv"),))

    for rule, name, column in COMPLETE:
        path = staging_dir / f"{name}.csv"
        apply(lambda df, p=path, r=rule, c=column: check_complete(df, p, r, c),
              rule, ((name, "csv"),))

    path = staging_dir / "stops.csv"
    apply(lambda df: check_station_prefixes(df, path), 32, (("stops", "csv"),))

    for rule, child_name, fk, parent_name, pk in REFERENCES:
        child_path = staging_dir / f"{child_name}.txt"
        parent_path = staging_dir / f"{parent_name}.txt"
        apply(lambda child, parent, cp=child_path, pp=parent_path, r=rule, f=fk, p=pk:
              check_reference(child, parent, cp, pp, r, f, p),
              rule, ((child_name, "txt"), (parent_name, "txt")))

    if failures:
        raise DataQualityError("Critical source data quality failures:\n" + "\n".join(failures))
