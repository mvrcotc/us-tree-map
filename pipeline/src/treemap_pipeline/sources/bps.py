"""LANDFIRE LF 2020 Biophysical Settings, CONUS (source id `bps`), clipped to the pilot window.

One full-extent zip from landfire.gov (2.0 GB, checked Oct 29, 2026); it deflates the GeoTIFF,
so it is downloaded whole to data/raw/bps/ and clipped there (`sources.zipclip`). No email or
account is needed, unlike the LFPS clip service. The zip also holds the attribute table
`CSV_Data/LF2020_BPS.csv` (VALUE, BPS_CODE, BPS_NAME, GROUPVEG, ...), read from the local zip.
"""

import csv
import io
import zipfile

from treemap_pipeline.sources.zipclip import ZipRaster

YEAR = 2020
SOURCE = ZipRaster(
    source="bps",
    base_url=f"https://landfire.gov/data-downloads/CONUS_LF{YEAR}",
    years=range(YEAR, YEAR + 1),
    zip_name=lambda year: f"LF{year}_BPS_CONUS.zip",
    clip_stem=lambda year: f"LF{year}_BPS_CONUS",
    download_if_compressed=True,
)
ATTRIBUTES = f"LF{YEAR}_BPS_CONUS/CSV_Data/LF{YEAR}_BPS.csv"
# Raster values below 1 are fill codes, not settings: -9999 Fill-NoData, -1111 Fill-Not Mapped.
FILL_MAX = 0


def attributes() -> list[dict]:
    """Rows of the LANDFIRE attribute table (one per raster VALUE), from the downloaded zip."""
    with zipfile.ZipFile(SOURCE.raw_dir() / SOURCE.zip_name(YEAR)) as zf:
        text = zf.read(ATTRIBUTES).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))
