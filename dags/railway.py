"""Airflow entry point for the railway GTFS pipeline."""

from core.railway.pipelines.railway_gtfs_pipeline import railway_pipeline

dag = railway_pipeline()
