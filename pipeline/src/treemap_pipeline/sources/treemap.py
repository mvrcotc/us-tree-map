"""TreeMap 2023 CONUS (source id `treemap`, RDS-2026-0038), clipped to the pilot window.

The data zip (4.87 GB) is a USFS Box shared link from the RDS catalog page
(`https://www.fs.usda.gov/rds/archive/catalog/RDS-2026-0038`, checked Oct 29, 2026); Box
honors range requests, but the zip deflates its GeoTIFF, so it is downloaded whole. Members:
`Data/TreeMap2023_CONUS.tif` (pixel value = `TM_ID`, the imputed FIA plot record),
`Data/TreeMap2023_CONUS_Tree_Table.csv` and `Data/_variable_descriptions.csv`.

Tree table fields used (from `_variable_descriptions.csv`, Oct 29, 2026): `TM_ID`;
`STATUSCD` (1 = live, 2 = dead); `TPA_UNADJ` (trees per acre, by the plot design); `SPCD`
(FIA species code); `DIA` (diameter, inches, at 4.5 ft for timber species, at the ground
line for woodland species).
"""

import zipfile

import pyarrow as pa
import pyarrow.csv as pacsv

from treemap_pipeline.sources.zipclip import ZipRaster

YEAR = 2023
SOURCE = ZipRaster(
    source="treemap",
    base_url="https://usfs-public.box.com/shared/static",
    years=range(YEAR, YEAR + 1),
    zip_name=lambda year: "xlaazfhic3ugd1yetoxcicjgtl2t3mry.zip",  # Box file id of RDS-2026-0038.zip
    clip_stem=lambda year: f"TreeMap{year}_CONUS",
    download_if_compressed=True,
)
TREE_TABLE = f"Data/TreeMap{YEAR}_CONUS_Tree_Table.csv"
LIVE = 1


def tree_table(columns=("TM_ID", "STATUSCD", "TPA_UNADJ", "SPCD", "DIA")) -> pa.Table:
    """The tree table's needed columns, read from the downloaded zip."""
    with zipfile.ZipFile(SOURCE.raw_dir() / SOURCE.zip_name(YEAR)) as zf, zf.open(TREE_TABLE) as f:
        return pacsv.read_csv(
            f,
            convert_options=pacsv.ConvertOptions(
                include_columns=list(columns),
                null_values=["NA", ""],
                column_types={"TM_ID": pa.int64(), "STATUSCD": pa.int8(), "TPA_UNADJ": pa.float64(), "SPCD": pa.int16(), "DIA": pa.float64()},
            ),
        )
