import os

import boto3
from botocore.config import Config
from botocore.client import BaseClient


def create_s3_client() -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=os.getenv(
            "S3_ENDPOINT",
            "http://localhost:7004",
        ),
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )