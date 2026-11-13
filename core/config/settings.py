"""Local scratch configuration; published datasets live in MinIO."""

import os
from pathlib import Path


class Settings:
    @property
    def tmp_dir(self) -> Path:
        return Path(os.getenv("RAILWAY_WORK_DIR", "/tmp/railway"))


settings = Settings()
