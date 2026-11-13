# RFN railway line geometry ingestion

The independent Airflow DAG `rfn_lines_download` downloads the [SNCF RFN line geometry Parquet export](https://data.sncf.com/api/explore/v2.1/catalog/datasets/formes-des-lignes-du-rfn/exports/parquet?lang=fr&timezone=Europe%2FParis) with `FetchingHelper.download_file`, then uploads the original bytes to MinIO. It runs on demand, with two retries per task, and does not perform Silver or Gold transformations.

## Run

Open http://localhost:7001, find `rfn_lines_download`, and trigger it. Alternatively, from the repository root:

```bash
docker compose exec airflow-scheduler airflow dags trigger rfn_lines_download
```

The tasks are `download_parquet → upload_to_minio`. The upload task returns the S3 URI in its XCom. Scratch files live under `/tmp/railway/formes-des-lignes-du-rfn/<encoded-run-id>/` on the existing shared Airflow volume.

With the default `railway` bucket, objects are written to:

```text
s3://railway/data/raw/formes-des-lignes-du-rfn/<encoded-run-id>/formes-des-lignes-du-rfn.parquet
s3://railway/data/raw/formes-des-lignes-du-rfn/<encoded-run-id>/manifest.json
s3://railway/data/raw/formes-des-lignes-du-rfn/_latest.json
```

`S3_BUCKET` selects another bucket. The latest pointer contains `manifest_key`. That manifest contains the object `key`, S3 `uri`, original source URL, row count, byte size, SHA-256, and upload timestamp. The pointer advances only after upload succeeds. A retry reuses the downloaded file and rejects changing an already published run's bytes. New runs create new raw snapshots.

## Source fields

Inspection of the export on November 13, 2026 found 1,638 rows. The original GeoParquet geometry metadata is preserved.

| Field | Meaning |
| --- | --- |
| `geo_shape` | WKB LineString geometry of the railway segment, using longitude/latitude coordinates |
| `geo_point_2d` | Representative point in WKB, not the railway line geometry |
| `code_ligne` | RFN infrastructure line code, stored as text |
| `rg_troncon` | Section rank within a line |
| `pk_debut_r`, `pk_fin_r` | Start and end kilometre reference strings |
| `mnemo` | Infrastructure status, such as `EXPLOITE` or `NEUT` |
| `libelle` | Description of the infrastructure status |
| `mnemo_type` | Infrastructure feature type |

The source includes operating, closed, neutralised, and other line statuses. Filter `mnemo = 'EXPLOITE'` if you only want operating infrastructure. A line code has multiple rows, and even `(code_ligne, rg_troncon, pk_debut_r, pk_fin_r)` is not unique in this export. Create a proper segment identifier during any later transformation instead of using the line code as a segment primary key. See the [SNCF dataset description](https://data.sncf.com/explore/dataset/formes-des-lignes-du-rfn/).

## Connect it to the existing data

### Display the infrastructure layer in Cesium

The Nuxt app now implements this connection. Open http://localhost:7007 and use **Rails → Operating** or **Rails → All statuses** to display it. **Off** hides the layer. The map starts with it off.

Nitro reads the raw MinIO file through `/api/railways`, follows the latest manifest, verifies the checksum and row count, and decodes the GeoParquet WKB into GeoJSON. Cesium draws the `geo_shape` lines underneath station markers. Operating segments are solid blue; other statuses are dashed gray. Geometry coordinate order remains `[longitude, latitude]`. No station join or Iceberg registration is needed for this overlay.

MinIO credentials are configured server-side in Nuxt runtime config; Docker Compose uses the existing lakehouse env file. See [the frontend instructions](../frontend/README.md#railway-infrastructure-layer). The response is cached for 60 seconds; reload the page after a new ingestion to request the latest snapshot. Station date/search filters do not alter the infrastructure overlay.

### Relate stations to infrastructure lines

`gold.dim_station.station_id` contains GTFS station identifiers such as `StopArea:OCE87212027`. RFN `code_ligne` identifies infrastructure, so these are different keys.

A later spatial transformation can relate each station point to nearby `geo_shape` segments. Calculate distances in metres using a suitable projected coordinate system, such as EPSG:2154 for metropolitan France. Inspect the distances before choosing a matching tolerance. Junction stations can legitimately match multiple lines, so keep a bridge such as:

```text
gold.dim_station.station_key
    → bridge_station_rfn_segment (station_key, segment_key, distance_m, match_method)
    → dim_rfn_segment (segment_key, code_ligne, geometry, status, ...)
```

Use the full line geometry for matching, not its representative point. Proximity provides candidate associations rather than proof that a scheduled trip uses a particular track.

### Relate GTFS routes or trips to infrastructure

The project's `route_id` values look like `FR:Line::<UUID>:`. They are not RFN `code_ligne` values. A commercial route may use multiple infrastructure lines.

An authoritative crosswalk or a validated path reconstruction using ordered trip stops and a connected railway network is needed for a route/trip-to-infrastructure relationship. A nearest-station match alone cannot establish the full path. Preserve this as a many-to-many relationship if implemented later.

### Query it in Trino

The file is raw Parquet in MinIO. Uploading it does not register an Iceberg table, so it will not automatically appear in the current Trino Iceberg catalog or Metabase. A later Silver ingestion can publish its columns (including WKB as binary) into an Iceberg table, then use `ST_GeomFromBinary(geo_shape)` in Trino for geometry operations. See [Trino geospatial functions](https://trino.io/docs/current/functions/geospatial.html).
