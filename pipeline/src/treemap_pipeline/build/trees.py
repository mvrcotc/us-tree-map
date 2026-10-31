"""`hex_trees` (one row per hex per species present, TreeMap 2023).

Data contract: Tables → `hex_trees`. Each forested pixel carries one imputed FIA plot
(`TM_ID`); a plot's live trees give per-species basal area per acre
(Σ 0.005454 × DIA² × TPA_UNADJ, ft²/ac) and trees per acre (Σ TPA_UNADJ). Per hex:
- `ba_ft2ac`, `tpa`: pixel-weighted mean over the hex's forested pixels;
- `ba_share`: the species' share of the hex's live basal area;
- `forest_px_frac`: forested (plot-assigned) pixels over all pixels.
Roll-ups sum pixel × value products and pixel counts, never averages; means come last.
A hex with no forested pixel has no rows (no species present), not zeros.

Values are rounded to 3 significant figures (L5: the largest res-7 chunk is 2.2 MB unrounded).
Significant figures, not fixed decimals, so a rare species never rounds to a false 0.

TreeMap 2023 has plots in the raster with no rows in its tree table (771 CONUS; 70 in the
Wisconsin window, 0.002% of forested pixels), though the raster's attribute table gives all of
them live basal area. Their species are unknown, so those pixels count as forest but stay out of the
species means (never treated as treeless). More than MAX_UNKNOWN_SHARE fails the build: that
would mean a mismatched file, not this quirk.
"""

from pathlib import Path

import numpy as np
import pyarrow as pa
import rasterio

from treemap_pipeline import config, h3util, raster
from treemap_pipeline.sources import treemap

BA_FACTOR = 0.005454  # ft² per in² of diameter: π / (4 × 144)
MAX_UNKNOWN_SHARE = 0.001  # of forested pixels
SIG_FIGS = 3
SCHEMA = pa.schema(
    [
        ("h3", pa.uint64()),
        ("res", pa.int8()),
        ("p3", pa.uint64()),
        ("spcd", pa.int16()),
        ("ba_ft2ac", pa.float32()),
        ("ba_share", pa.float32()),
        ("tpa", pa.float32()),
        ("forest_px_frac", pa.float32()),
    ]
)


def plot_species(trees: pa.Table) -> pa.Table:
    """(tm_id, spcd, ba, tpa) per plot and species, live trees only.

    A live tree without a diameter adds to `tpa` but not to `ba` (its basal area is unknown,
    so it is left out rather than guessed); `missing_dia` counts them for the build log.
    """
    t = trees  # noqa: F841 (read by DuckDB)
    return h3util.con().sql(
        f"""
        SELECT TM_ID AS tm_id, SPCD AS spcd,
               sum({BA_FACTOR} * DIA * DIA * TPA_UNADJ) FILTER (WHERE DIA IS NOT NULL) AS ba,
               sum(TPA_UNADJ) AS tpa,
               count(*) FILTER (WHERE DIA IS NULL) AS missing_dia
        FROM t
        WHERE STATUSCD = {treemap.LIVE} AND TPA_UNADJ IS NOT NULL AND SPCD IS NOT NULL
        GROUP BY ALL ORDER BY tm_id, spcd
        """
    ).to_arrow_table()


def plot_counts(ds: rasterio.DatasetReader, grid: raster.CellGrid) -> tuple[pa.Table, pa.Table]:
    """(pixels per (res-8 cell, plot id), n_total per cell). Nodata pixels count in n_total only."""
    grid.check(ds)
    nodata = ds.nodata
    index = grid.index()
    ncell = len(grid.cells) + 1
    n_total = np.zeros(ncell, dtype=np.int64)
    keys, counts = [], []
    for r0, r1, win in raster._strips(grid):
        idx = np.asarray(index[r0:r1]).astype(np.int64)
        n_total += np.bincount(idx.ravel(), minlength=ncell)
        vals = ds.read(1, window=win).astype(np.int64)
        ok = idx > 0
        if nodata is not None:
            ok &= vals != int(nodata)
        ok &= vals > 0
        if ok.any() and vals[ok].max() >= 1 << 32:
            raise ValueError(f"plot id {vals[ok].max()} does not fit the 32-bit key")
        k, n = np.unique((idx[ok] << 32) | vals[ok], return_counts=True)
        keys.append(k)
        counts.append(n)
    k = np.concatenate(keys) if keys else np.zeros(0, np.int64)
    n = np.concatenate(counts) if counts else np.zeros(0, np.int64)
    pairs = pa.table({"key": k, "n": n})  # noqa: F841 (read by DuckDB)
    summed = h3util.con().sql("SELECT key, sum(n)::BIGINT AS n FROM pairs GROUP BY key ORDER BY key").to_arrow_table()
    key = summed["key"].to_numpy()
    cell_i = (key >> 32) - 1
    tm_id = key & 0xFFFFFFFF
    has = n_total[1:] > 0
    totals = pa.table({"h3": pa.array(grid.cells[has], pa.uint64()), "n_total": pa.array(n_total[1:][has], pa.int64())})
    return pa.table({"h3": pa.array(grid.cells[cell_i], pa.uint64()), "tm_id": pa.array(tm_id, pa.int64()), "n": summed["n"]}), totals


def build_trees(clip: Path, trees: pa.Table, members: dict[int, np.ndarray], cache_dir: Path = config.WORK / "cellgrid") -> dict[int, pa.Table]:
    """{res: hex_trees table} from the TreeMap clip and the tree table."""
    with rasterio.open(clip) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=cache_dir)
        pairs, totals = plot_counts(ds, grid)
    ps = plot_species(trees)
    # Arrays, not Python sets: the pairs can run to tens of millions on the 8 GB build machine.
    known = pa.array(np.isin(pairs["tm_id"].to_numpy(), trees["TM_ID"].drop_null().to_numpy()))
    n = pairs["n"].to_numpy()
    unknown_px = int(n[~known.to_numpy(zero_copy_only=False)].sum())
    share = unknown_px / max(int(n.sum()), 1)
    if share > MAX_UNKNOWN_SHARE:
        raise ValueError(f"{share:.2%} of forested pixels have plot ids missing from the tree table (limit {MAX_UNKNOWN_SHARE:.2%})")
    print(f"  trees: {unknown_px:,} forested pixels ({share:.3%}) have no tree-table plot; kept as forest, left out of species means")
    p, s = pairs.append_column("known", known), ps  # noqa: F841 (read by DuckDB)
    con = h3util.con()
    # Per res-8 cell and species: pixel × value sums (rolled up as sums).
    cell_species = con.sql(
        "SELECT p.h3, s.spcd, sum(p.n * s.ba)::DOUBLE AS ba_px, sum(p.n * s.tpa)::DOUBLE AS tpa_px "
        "FROM p JOIN s USING (tm_id) GROUP BY ALL"
    ).to_arrow_table()
    forest = con.sql(
        "SELECT h3, sum(n)::BIGINT AS forest_px, (sum(n) FILTER (WHERE known))::BIGINT AS known_px FROM p GROUP BY h3"
    ).to_arrow_table()
    rolled = raster.rollup(cell_species, members, ["spcd"], ["ba_px", "tpa_px"])
    rolled_forest = raster.rollup(forest, members, [], ["forest_px", "known_px"])
    rolled_totals = raster.rollup(totals, members, [], ["n_total"])
    raster.require_coverage(rolled_totals, members)
    return {res: _means(rolled[res], rolled_forest[res], rolled_totals[res]) for res in members}


def _means(species: pa.Table, forest: pa.Table, totals: pa.Table) -> pa.Table:
    s, f, t = species, forest, totals  # noqa: F841 (read by DuckDB)
    sql = """
        SELECT s.h3, s.res, s.p3, s.spcd,
               (s.ba_px / f.known_px)::FLOAT AS ba_ft2ac,
               (CASE WHEN sum(s.ba_px) OVER w > 0 THEN s.ba_px / sum(s.ba_px) OVER w END)::FLOAT AS ba_share,
               (s.tpa_px / f.known_px)::FLOAT AS tpa,
               (f.forest_px / t.n_total)::FLOAT AS forest_px_frac
        FROM s JOIN f USING (h3) JOIN t USING (h3)
        WINDOW w AS (PARTITION BY s.h3)
        ORDER BY s.h3, s.spcd
    """
    t = h3util.con().sql(sql).to_arrow_table().cast(SCHEMA)
    for name in ("ba_ft2ac", "ba_share", "tpa", "forest_px_frac"):
        t = t.set_column(t.schema.get_field_index(name), SCHEMA.field(name), round_sig(t[name]))
    return t


def round_sig(values: pa.ChunkedArray | pa.Array, digits: int = SIG_FIGS) -> pa.Array:
    """Round to `digits` significant figures; NULL stays NULL and non-zero stays non-zero."""
    x = values.to_numpy(zero_copy_only=False).astype(np.float64)
    out = x.copy()
    ok = np.isfinite(x) & (x != 0)
    scale = 10.0 ** (digits - 1 - np.floor(np.log10(np.abs(x[ok]))))
    out[ok] = np.round(x[ok] * scale) / scale
    return pa.array(out.astype(np.float32), pa.float32(), mask=~np.isfinite(x))
