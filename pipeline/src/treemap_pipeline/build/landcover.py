"""`hex_landcover` (one row per hex per year, Annual NLCD 1.2) and `hex_base.land_frac`.

Data contract: Tables → `hex_landcover`. Fractions are shares of valid pixels and sum to
1 per hex-year; `valid_frac` is valid pixels over all pixels in the hex. A hex-year with
no valid pixel gets NULL fractions, never 0 (hard rule 1).
"""

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import rasterio

from treemap_pipeline import config, h3util, raster

# Contract column → NLCD classes. Together they cover all 16 CONUS classes.
GROUPS = {
    "frac_forest": [41, 42, 43],
    "frac_woody_wetland": [90],
    "frac_developed": [21, 22, 23, 24],
    "frac_crop": [82],
    "frac_grass_pasture": [71, 81],
    "frac_shrub": [52],
    "frac_herb_wetland": [95],
    "frac_water": [11],
    "frac_barren": [31],
    "frac_snow": [12],
}
CLASSES = sorted(c for cs in GROUPS.values() for c in cs)

SCHEMA = pa.schema(
    [("h3", pa.uint64()), ("res", pa.int8()), ("p3", pa.uint64()), ("year", pa.int16())]
    + [(name, pa.float32()) for name in GROUPS]
    + [("valid_frac", pa.float32())]
)


# Years counted per pass over the cell index: each pass reads the index once (the slow
# read), and memory stays bounded (perf-budget → Pipeline rules: never all years at once).
YEARS_PER_PASS = 8


def build_landcover(clips: dict[int, Path], members: dict[int, np.ndarray], cache_dir: Path = config.WORK / "cellgrid") -> dict[int, pa.Table]:
    """{res: hex_landcover table} from one clipped GeoTIFF per year (all on one grid)."""
    years = sorted(clips)
    with rasterio.open(clips[years[0]]) as first:
        grid = raster.cell_grid(first, None, cache_dir=cache_dir)
    parts: dict[int, list[pa.Table]] = {res: [] for res in members}
    rolled_totals = None
    for i in range(0, len(years), YEARS_PER_PASS):
        batch = years[i : i + YEARS_PER_PASS]
        datasets = [rasterio.open(clips[y]) for y in batch]
        try:
            counts, totals = raster.categorical_counts_many(datasets, grid, CLASSES)
        finally:
            for ds in datasets:
                ds.close()
        if rolled_totals is None:
            rolled_totals = raster.rollup(totals, members, [], ["n_total"])
            raster.require_coverage(rolled_totals, members)
        for year, c in zip(batch, counts):
            rolled = raster.rollup(c, members, ["class"], ["n"])
            for res in members:
                parts[res].append(_fractions(rolled[res], rolled_totals[res], year))
        del counts
    return {res: pa.concat_tables(tables).sort_by([("h3", "ascending"), ("year", "ascending")]) for res, tables in parts.items()}


def _fractions(counts: pa.Table, totals: pa.Table, year: int) -> pa.Table:
    c, t = counts, totals  # noqa: F841 (read by DuckDB)
    shares = ",\n".join(
        f"(sum(c.n) FILTER (WHERE c.class IN ({', '.join(map(str, cls))})) / nullif(sum(c.n), 0))::FLOAT AS {name}" for name, cls in GROUPS.items()
    )
    sql = f"""
        SELECT t.h3, t.res, t.p3, {int(year)}::SMALLINT AS year,
               {", ".join(f"CASE WHEN v.valid > 0 THEN coalesce(v.{name}, 0) END AS {name}" for name in GROUPS)},
               (coalesce(v.valid, 0) / t.n_total)::FLOAT AS valid_frac
        FROM t LEFT JOIN (
            SELECT c.h3, sum(c.n) AS valid, {shares}
            FROM c GROUP BY c.h3
        ) v USING (h3)
        ORDER BY t.h3
    """
    return h3util.con().sql(sql).to_arrow_table().cast(SCHEMA)


def land_frac(landcover: dict[int, pa.Table], year: int) -> dict[int, pa.Table]:
    """{res: table(h3, value)}: non-water share in `year` (data contract: `hex_base.land_frac`).

    A share of the hex's valid pixels, NULL when none is valid. Near the Great Lakes shore a
    hex can have few valid pixels; read it together with that year's `valid_frac`.
    """
    out = {}
    for res, t in landcover.items():
        y = t.filter(pc.equal(t["year"], pa.scalar(year, pa.int16())))
        water = y["frac_water"]
        value = pc.subtract(pa.scalar(1.0, pa.float32()), water)  # NULL stays NULL
        out[res] = pa.table({"h3": y["h3"], "value": value.cast(pa.float32())})
    return out
