from pathlib import Path
from dataclasses import dataclass

DATA_DIR = Path("./data")
RAW_PATH = Path("./data/raw")
STAGING_PATH = Path("./data/staging")
PROCESSED_PATH = Path("./data/processed")
CURATED_PATH = Path("./data/curated")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    raw_dir: Path
    staging_dir: Path
    processed_dir: Path
    curated_dir: Path

settings: Settings = Settings(
    DATA_DIR,
    raw_dir=RAW_PATH,
    staging_dir=STAGING_PATH,
    processed_dir=PROCESSED_PATH,
    curated_dir=CURATED_PATH,
)
