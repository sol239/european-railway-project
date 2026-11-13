"""Run-scoped temporary file helpers."""

from pathlib import Path
from urllib.parse import quote

import pandas as pd


def run_directory(root: Path, run_id: str) -> Path:
    if not run_id or run_id in ('.', '..'):
        raise ValueError('A non-empty run ID is required')
    return root / quote(run_id, safe='-_.')


def write_temporary(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.writing')
    if path.suffix == '.csv':
        frame.to_csv(temporary, index=False)
    elif path.suffix == '.parquet':
        frame = frame.copy()
        for column in ('trip_key', 'route_key', 'station_key', 'route_type'):
            if column in frame:
                frame[column] = frame[column].astype('Int64')
        frame.to_parquet(temporary, index=False)
    else:
        raise ValueError(f'Unsupported output format: {path.suffix}')
    temporary.replace(path)
    return str(path)
