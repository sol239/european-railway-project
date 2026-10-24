from zipfile import ZipFile
from fetching_library_python import FetchingHelper
import pandas as pd
from pathlib import Path
from core.config.settings import settings

ARCHIVE_DOWNLOAD_PATH = settings.raw_dir / "data-gtfs.zip"


async def download_gtfs_archive() -> Path:
    """Download the SNCF GTFS archive to the configured location.

    Returns:
        Path: Location of the downloaded GTFS ZIP archive.

    Raises:
        Exception: If the archive download fails.
    """
    gtfs_url = "https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip"

    await FetchingHelper.download_file(gtfs_url, path=ARCHIVE_DOWNLOAD_PATH)

    return ARCHIVE_DOWNLOAD_PATH


def extract_gtfs_archive() -> list[Path]:
    """Extract GTFS files from the downloaded ZIP archive.

    Extracts all archive contents into the configured staging directory
    and returns paths to the extracted GTFS text files.

    Returns:
        list[Path]: Paths to the extracted GTFS text files.

    Raises:
        FileNotFoundError: If the GTFS archive does not exist.
        BadZipFile: If the archive is invalid or corrupted.
    """
    with ZipFile(ARCHIVE_DOWNLOAD_PATH) as archive:
        archive.extractall(settings.staging_dir)

        return [
            settings.staging_dir / name
            for name in archive.namelist()
            if name.endswith(".txt")
        ]


def convert_to_csv(files: list[Path]) -> list[Path]:
    """Convert GTFS text files to CSV format.

    Reads each GTFS text file as a pandas DataFrame, preserving
    column values as strings, and writes the result as a CSV file
    in the same directory.

    Args:
        files (list[Path]): Paths to the GTFS text files to convert.

    Returns:
        list[Path]: Paths to the generated CSV files.

    Raises:
        FileNotFoundError: If an input file does not exist.
        pd.errors.ParserError: If an input file cannot be parsed.
        OSError: If an output file cannot be written.
    """
    output_files: list[Path] = []

    for file in files:
        df = pd.read_csv(file, dtype=str)

        output_path = file.with_suffix(".csv")

        df.to_csv(output_path, index=False)
        output_files.append(output_path)

    return output_files
