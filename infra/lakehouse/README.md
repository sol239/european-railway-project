# Local object storage

MinIO is built locally from the pinned upstream source release because the historical public container images are unavailable. The first build downloads Go dependencies and takes several minutes.

From the project root, with credentials in `infra/lakehouse/.env`:

```bash
docker compose --env-file infra/lakehouse/.env -f infra/lakehouse/compose.yml up -d --build
```

The S3 endpoint is `http://localhost:7004` and the console is `http://localhost:7003`. Sign in with the credentials configured in `.env`. Data is persisted in the `minio_data` Docker volume.

MinIO joins the `railway-lakehouse` Docker network shared with Airflow. Start this stack before the root Compose stack. The bucket is configured by `S3_BUCKET` (default `railway`); all pipeline objects use its `data/` prefix. See the project README for the pipeline and host-side credentials setup.

The stack also runs `iceberg-catalog-db`, a PostgreSQL SQL catalog for PyIceberg, exposed on `127.0.0.1:7005` for local tools. It stores catalog pointers; Iceberg metadata and data stay in MinIO. The catalog username and database are `iceberg`, and its development password is `MINIO_ROOT_PASSWORD`. The `iceberg_catalog` Docker volume persists catalog state.
