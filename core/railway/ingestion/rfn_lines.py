"""Download the unchanged SNCF national railway line geometry export."""

from pathlib import Path

import pyarrow.parquet as pq
from fetching_library_python import FetchingHelper

DATASET = 'formes-des-lignes-du-rfn'
SOURCE_URL = (
    'https://data.sncf.com/api/explore/v2.1/catalog/datasets/'
    'formes-des-lignes-du-rfn/exports/parquet?lang=fr&timezone=Europe%2FParis'
)
FILENAME = f'{DATASET}.parquet'


def parquet_metadata(path: Path):
    """Check the footer and source columns without transforming the raw file."""
    parquet = pq.ParquetFile(path)
    if not {'geo_shape', 'code_ligne'}.issubset(parquet.schema_arrow.names):
        raise ValueError('The RFN export is missing geo_shape or code_ligne')
    if parquet.metadata.num_rows == 0:
        raise ValueError('The RFN export is empty')
    return parquet.metadata


async def download_rfn_lines(path: Path) -> Path:
    """Stream to a temporary file so failed downloads never become completed files."""
    path = Path(path)
    if path.exists():
        parquet_metadata(path)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.parquet.downloading')
    try:
        await FetchingHelper.download_file(SOURCE_URL, path=temporary)
        parquet_metadata(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
