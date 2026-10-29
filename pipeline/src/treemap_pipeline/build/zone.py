"""`hex_zone` (static, one row per hex, PHZM 2023 half-zones).

Data contract: Tables → `hex_zone`. `zone_coldest` is the coldest half-zone with any pixel in
the hex (the engine gates on it, so it errs cold); `zone_mode` the most common half-zone, a
tie going to the colder one; `valid_frac` valid pixels over all pixels. A hex with no valid
pixel gets NULL zones, never a made-up zone (hard rule 1).
"""

from pathlib import Path

import numpy as np
import pyarrow as pa
import rasterio

from treemap_pipeline import config, h3util, raster
from treemap_pipeline.sources import phzm

SCHEMA = pa.schema(
    [
        ("h3", pa.uint64()),
        ("res", pa.int8()),
        ("p3", pa.uint64()),
        ("zone_coldest", pa.string()),
        ("zone_coldest_num", pa.float32()),
        ("zone_mode", pa.string()),
        ("valid_frac", pa.float32()),
    ]
)
CLASSES = list(range(phzm.HALF_ZONES))


def build_zone(clip: Path, members: dict[int, np.ndarray], cache_dir: Path = config.WORK / "cellgrid") -> dict[int, pa.Table]:
    """{res: hex_zone table} from the half-zone clip."""
    with rasterio.open(clip) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=cache_dir)
        (counts,), totals = raster.categorical_counts_many([ds], grid, CLASSES)
    rolled = raster.rollup(counts, members, ["class"], ["n"])
    rolled_totals = raster.rollup(totals, members, [], ["n_total"])
    raster.require_coverage(rolled_totals, members)
    return {res: _zones(rolled[res], rolled_totals[res]) for res in members}


def _label(col: str) -> str:
    return f"(({col} // 2) + 1)::VARCHAR || CASE WHEN {col} % 2 = 0 THEN 'a' ELSE 'b' END"


def _zones(counts: pa.Table, totals: pa.Table) -> pa.Table:
    c, t = counts, totals  # noqa: F841 (read by DuckDB)
    sql = f"""
        SELECT t.h3, t.res, t.p3,
               {_label("z.coldest")} AS zone_coldest,
               (z.coldest // 2 + 1 + 0.5 * (z.coldest % 2))::FLOAT AS zone_coldest_num,
               {_label("z.mode")} AS zone_mode,
               (coalesce(z.valid, 0) / t.n_total)::FLOAT AS valid_frac
        FROM t LEFT JOIN (
            SELECT h3, min(class) AS coldest, first(class ORDER BY n DESC, class ASC) AS mode, sum(n) AS valid
            FROM c GROUP BY h3
        ) z USING (h3)
        ORDER BY t.h3
    """
    return h3util.con().sql(sql).to_arrow_table().cast(SCHEMA)
