# Data Quality for Railway Data

## Source Data Checks

Source checks are implemented in `core/railway/data-quality/source.py`. Call `validate_source(archive_path, staging_dir)` to evaluate DQ1–DQ19, DQ21–DQ27, and DQ29–DQ36; it raises `DataQualityError` containing all failures. Individual checks can also be called independently. The pipeline runs these checks in `source_data_quality` after ingestion and before transformations. The dimension validation referenced in `transformed.py` is not yet implemented.

### DQ1: Completeness - ZIP Contains Required TXT Files

**Requirement:** The downloaded GTFS archive must contain all required `.txt` files:

- `agency.txt`
- `routes.txt`
- `stops.txt`
- `trips.txt`
- `stop_times.txt`

**Severity:** Critical

**Implementation:** `core/railway/data-quality/source.py::check_required_files`

### DQ2–DQ6: Completeness - TXT Tables Contain Required Columns

**Requirement:** Each table header must contain the columns listed below. Additional columns are allowed. These checks assess column presence; value completeness is checked separately. Missing required columns must fail before transformation.

| Rule | Table | Required columns |
| --- | --- | --- |
| DQ2 | `agency.txt` | `agency_id` |
| DQ3 | `routes.txt` | `route_id`, `agency_id`, `route_short_name`, `route_long_name`, `route_type` |
| DQ4 | `stops.txt` | `stop_id`, `stop_name` |
| DQ5 | `trips.txt` | `trip_id`, `route_id` |
| DQ6 | `stop_times.txt` | `trip_id`, `stop_id`, `arrival_time`, `departure_time`, `stop_sequence`, `stop_headsign`, `pickup_type`, `drop_off_type` |

Other agency attributes are retained when present. Other trip attributes are retained except `shape_id` and `route_id`; the latter is used separately to resolve route keys.

**Severity:** Critical

**Implementation:** `core/railway/data-quality/source.py`: `check_agency_required_columns` (DQ2), `check_routes_required_columns` (DQ3), `check_stops_required_columns` (DQ4), `check_trips_required_columns` (DQ5), `check_stop_times_required_columns` (DQ6)

### DQ7–DQ10: Uniqueness - Source IDs Are Unique

**Requirement:** After trimming surrounding whitespace, non-missing IDs must be unique across all rows of their source table. Duplicate IDs must fail before transformations remove duplicates. Nulls and blanks are assessed by the attribute completeness checks. Foreign keys may repeat.

| Rule | Table | Unique column |
| --- | --- | --- |
| DQ7 | `agency.txt` | `agency_id` |
| DQ8 | `routes.txt` | `route_id` |
| DQ9 | `stops.txt` | `stop_id` (stations and platforms together) |
| DQ10 | `trips.txt` | `trip_id` |

**Severity:** Critical

**Implementation:** `core/railway/data-quality/source.py`: `check_agency_agency_id_uniqueness` (DQ7), `check_routes_route_id_uniqueness` (DQ8), `check_stops_stop_id_uniqueness` (DQ9), `check_trips_trip_id_uniqueness` (DQ10)

### DQ11: Timeliness - Feed Date Is No Older Than Two Days

**Requirement:** Every `feed_version` in `data/staging/feed_info.csv` must be a valid `YYYY-MM-DD` date satisfying `current_date - 2 days <= feed_date <= current_date`, using the current date at check execution in `Europe/Prague`. Exactly two days old passes. Future, missing, invalid, or older dates fail, as do a missing file or column or an empty table.

Use this SNCF feed's date-valued `feed_version` for freshness; `feed_start_date` and `feed_end_date` describe service coverage. On `2026-10-24`, dates from `2026-10-22` through `2026-10-24` pass; `2026-10-21` fails.

**Severity:** Critical

**Implementation:** `core/railway/data-quality/source.py::check_feed_timeliness`

### DQ12–DQ19, DQ21–DQ27, and DQ29–DQ31: Completeness - Required Attribute Non-Nullness Exceeds 99%

**Requirement:** Each attribute below must independently have strictly more than 99% non-missing values in its staging CSV. Calculate `100 * non_missing_rows / total_rows` without rounding before comparison. Nulls, empty strings, and whitespace-only strings count as missing. Exactly 99% fails; 991 non-missing values out of 1,000 pass, while 990 fail. Do not average across columns or tables.

| Rule | Staging table | Required attribute | Acceptance | Implementation |
| --- | --- | --- | --- | --- |
| DQ12 | `agency.csv` | `agency_id` | Non-nullness > 99% | `check_agency_agency_id_completeness` |
| DQ13 | `routes.csv` | `route_id` | Non-nullness > 99% | `check_routes_route_id_completeness` |
| DQ14 | `routes.csv` | `agency_id` | Non-nullness > 99% | `check_routes_agency_id_completeness` |
| DQ15 | `routes.csv` | `route_short_name` | Non-nullness > 99% | `check_routes_route_short_name_completeness` |
| DQ16 | `routes.csv` | `route_long_name` | Non-nullness > 99% | `check_routes_route_long_name_completeness` |
| DQ17 | `routes.csv` | `route_type` | Non-nullness > 99% | `check_routes_route_type_completeness` |
| DQ18 | `stops.csv` | `stop_id` | Non-nullness > 99% | `check_stops_stop_id_completeness` |
| DQ19 | `stops.csv` | `stop_name` | Non-nullness > 99% | `check_stops_stop_name_completeness` |
| DQ21 | `trips.csv` | `trip_id` | Non-nullness > 99% | `check_trips_trip_id_completeness` |
| DQ22 | `trips.csv` | `route_id` | Non-nullness > 99% | `check_trips_route_id_completeness` |
| DQ23 | `stop_times.csv` | `trip_id` | Non-nullness > 99% | `check_stop_times_trip_id_completeness` |
| DQ24 | `stop_times.csv` | `stop_id` | Non-nullness > 99% | `check_stop_times_stop_id_completeness` |
| DQ25 | `stop_times.csv` | `arrival_time` | Non-nullness > 99% | `check_stop_times_arrival_time_completeness` |
| DQ26 | `stop_times.csv` | `departure_time` | Non-nullness > 99% | `check_stop_times_departure_time_completeness` |
| DQ27 | `stop_times.csv` | `stop_sequence` | Non-nullness > 99% | `check_stop_times_stop_sequence_completeness` |
| DQ29 | `stop_times.csv` | `pickup_type` | Non-nullness > 99% | `check_stop_times_pickup_type_completeness` |
| DQ30 | `stop_times.csv` | `drop_off_type` | Non-nullness > 99% | `check_stop_times_drop_off_type_completeness` |
| DQ31 | `feed_info.csv` | `feed_version` | Non-nullness > 99% | `check_feed_info_feed_version_completeness` |

A missing file or column, empty table, or percentage at or below 99% must fail before transformation. Report the rule ID, table, column, missing count, total row count, and non-nullness percentage.

DQ11 remains stricter for `feed_version`: every value must be valid and recent.

**Severity:** Critical

**Implementation:** `core/railway/data-quality/source.py`: one standalone function per table/attribute, listed below.

### DQ32: Consistency - Station Identifier Prefix

**Requirement:** After trimming surrounding whitespace, 100% of `stop_id` values in `data/staging/stops.csv` (from `stops.txt`) must start with `StopArea:` or `StopPoint:` and contain a non-empty suffix. Matching is case-sensitive. Nulls, blanks, unsupported prefixes, and empty suffixes fail, as do a missing file or column or an empty table. Report invalid row counts and sample values.

The station transformation selects only `StopArea:` rows and renames `stop_id` to `station_id`; all resulting dimension identifiers must therefore start with `StopArea:` and have a non-empty suffix. `StopPoint:` remains valid for source platform records.

**Severity:** Critical

**Implementation:** `core/railway/data-quality/source.py::check_station_identifier_prefixes`; `core/railway/data-quality/transformed.py::check_station_identifier_prefixes` (dimension validation).

### DQ33–DQ36: Referential Integrity - Foreign Keys Resolve

**Requirement:** After trimming surrounding whitespace on both sides, 100% of non-missing foreign keys must match a referenced ID from the same downloaded archive. Preserve IDs as strings and compare case-sensitively. Repeated foreign keys are allowed.

| Rule | Source column | Referenced column |
| --- | --- | --- |
| DQ33 | `routes.txt.agency_id` | `agency.txt.agency_id` |
| DQ34 | `trips.txt.route_id` | `routes.txt.route_id` |
| DQ35 | `stop_times.txt.trip_id` | `trips.txt.trip_id` |
| DQ36 | `stop_times.txt.stop_id` | `stops.txt.stop_id` |

Missing foreign keys are assessed by separate completeness rules.

Any unresolved reference, missing file or column, or empty required table must fail before transformation. Report the rule ID, source and target columns, invalid row count, and sample invalid IDs.

**Severity:** Critical

**Implementation:** `core/railway/data-quality/source.py`: `check_routes_agency_references` (DQ33), `check_trips_route_references` (DQ34), `check_stop_times_trip_references` (DQ35), `check_stop_times_stop_references` (DQ36).

## Processed Data Checks (Before Publishing)
