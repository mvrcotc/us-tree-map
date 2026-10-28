"""`hex_canopy` (one row per hex per year, USFS TCC v2025-6).

Data contract: Tables → `hex_canopy`. `canopy_frac` is the mean TCC percent over the hex's
valid pixels, divided by 100; `valid_frac` is valid pixels over all pixels in the hex.
Valid = 0–100; 254 (non-processing) and 255 (background) are not. A hex-year with no
valid pixel gets a NULL `canopy_frac`, never 0 (hard rule 1).
"""

from pathlib import Path

import numpy as np
import pyarrow as pa
import rasterio

from treemap_pipeline import config, h3util, raster
from treemap_pipeline.sources import tcc

SCHEMA = pa.schema(
    [("h3", pa.uint64()), ("res", pa.int8()), ("p3", pa.uint64()), ("year", pa.int16()), ("canopy_frac", pa.float32()), ("valid_frac", pa.float32())]
)

# Years summed per pass over the cell index (see build.landcover.YEARS_PER_PASS).
YEARS_PER_PASS = 8


def build_canopy(clips: dict[int, Path], members: dict[int, np.ndarray], cache_dir: Path = config.WORK / "cellgrid") -> dict[int, pa.Table]:
    """{res: hex_canopy table} from one clipped GeoTIFF per year (all on one grid)."""
    years = sorted(clips)
    with rasterio.open(clips[years[0]]) as first:
        grid = raster.cell_grid(first, None, cache_dir=cache_dir)
    parts: dict[int, list[pa.Table]] = {res: [] for res in members}
    for i in range(0, len(years), YEARS_PER_PASS):
        batch = years[i : i + YEARS_PER_PASS]
        datasets = [rasterio.open(clips[y]) for y in batch]
        try:
            sums = raster.continuous_sums_many(datasets, grid, tcc.VALID_MIN, tcc.VALID_MAX)
        finally:
            for ds in datasets:
                ds.close()
        for year, s in zip(batch, sums):
            rolled = raster.rollup(s, members, [], ["sum", "n_valid", "n_total"])
            if i == 0 and year == batch[0]:
                raster.require_coverage(rolled, members)
            for res in members:
                parts[res].append(_means(rolled[res], year))
    return {res: pa.concat_tables(tables).sort_by([("h3", "ascending"), ("year", "ascending")]) for res, tables in parts.items()}


def _means(rolled: pa.Table, year: int) -> pa.Table:
    r = rolled  # noqa: F841 (read by DuckDB)
    sql = f"""
        SELECT h3, res, p3, {int(year)}::SMALLINT AS year,
               (CASE WHEN n_valid > 0 THEN sum / n_valid / 100 END)::FLOAT AS canopy_frac,
               (n_valid / n_total)::FLOAT AS valid_frac
        FROM r ORDER BY h3
    """
    return h3util.con().sql(sql).to_arrow_table().cast(SCHEMA)
