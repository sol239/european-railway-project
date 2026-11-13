# European Railway Project

## Service ports

| Service | Local address | Purpose |
| --- | --- | --- |
| Airflow | http://localhost:7001 | Airflow web interface and API |
| Metabase | http://localhost:7002 | Analytics dashboard |
| MinIO API | http://localhost:7004 | Object storage API |
| MinIO Console | http://localhost:7003 | Object storage web interface |
| Iceberg catalog database | localhost:7005 | PostgreSQL catalog |

These ports are bound to `127.0.0.1` and are accessible from the local machine. The Airflow PostgreSQL database and Airflow background services do not publish ports to the host.

| Service | Username | Password |
| --- | --- | --- |
| Airflow | `admin` | `22KVGfcDGhrMuVRM` |
| MinIO | `railway_admin` | `railway_admin` |
| Iceberg catalog database | `iceberg` | `railway_admin` |
| Metabase | Set during initial setup | Set during initial setup |

## Gold layer

```mermaid
erDiagram
    dim_route ||--o{ fact_stop_time : route_key
    dim_station ||--o{ fact_stop_time : station_key
    dim_trip ||--o{ fact_stop_time : trip_key
    dim_trip }o--o{ fact_service_date : service_id

    dim_route {
        int route_key PK
        string route_id
        string agency_id
        string route_short_name
        string route_long_name
        int route_type
    }
    dim_station {
        int station_key PK
        string station_id
        string station_name
    }
    dim_trip {
        int trip_key PK
        string trip_id
        string service_id
    }
    fact_stop_time {
        int trip_key FK
        int route_key FK
        int station_key FK
        string arrival_time
        string departure_time
        int stop_sequence
        string stop_headsign
        int pickup_type
        int drop_off_type
    }
    fact_service_date {
        string service_id
        date service_date
    }
```

`fact_stop_time` contains one row per stop visit. `fact_service_date` contains one row per active service and date and joins to trips through `service_id`. The diagram shows the principal fields; dimension attributes may also include additional source columns.
