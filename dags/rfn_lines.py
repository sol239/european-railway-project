"""Airflow entry point for the independent RFN geometry download."""

from core.railway.pipelines.rfn_lines_pipeline import rfn_lines_pipeline

dag = rfn_lines_pipeline()
