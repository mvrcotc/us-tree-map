"""Raster → hex summaries (data contract: Raster → hex method; perf-budget: Pipeline rules).

1. Clip window: the pilot state plus a 10 km buffer, widened to cover every
   shipped hex whole (a res-5 hex reaches up to ~20 km past the border), in the
   raster's own grid.
2. Cell grid: every pixel's resolution-8 cell, by pixel center. Built once per
   source grid and window by rasterizing the res-8 hexagons onto the raster
   (GDAL burns a pixel when its center is inside the polygon, the same rule as
   indexing each pixel center), then cached in `data/work/cellgrid/`. Any later
   year of the same grid reuses it; another source reuses it only when its CRS,
   transform and window hash to the same key.
3. Reducers count pixels per class or sum values per cell with `np.bincount`,
   one block of rows at a time, so memory stays bounded.
4. `rollup` sums res-8 counts up to res 7, 6, 5, keeping every child of each
   `hex_base` hex (so border hexes are whole). Fractions and means are computed
   by the callers, last, and are NULL where no pixel was valid.
"""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import h3.api.basic_int as h3
import numpy as np
import pyarrow as pa
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from treemap_pipeline import config, h3util

BUFFER_M = 10_000
STRIP_ROWS = 2048
# Rows per strip in the reducers: smaller, so several years' temporaries stay well under
# 1 GB on an 8 GB machine (perf-budget → Pipeline rules: bounded memory).
REDUCE_ROWS = 512
# Datasets reduced at once per strip. Reads and bincount release the GIL, so threads scale
# (4 threads ≈ 3.6× on TCC, Oct 28, 2026); each dataset stays on one thread per strip.
REDUCE_THREADS = 4
# Integer rasters pack count and value into one float64 weight, (1 << 24) + v, so one
# bincount gives both; exact while every cell's value sum stays below 1 << 24.
PACK = 1 << 24
# Pixel index 0 means "no cell"; cell k is stored as k + 1.
NO_CELL = 0


@dataclass(frozen=True)
class CellGrid:
    """Res-8 cell of every pixel in a clip window of one source grid."""

    key: str
    src_crs: rasterio.crs.CRS
    src_transform: rasterio.Affine  # of the whole source raster
    window: Window
    transform: rasterio.Affine  # of the window
    cells: np.ndarray  # uint64, sorted; pixel value k + 1 means cells[k]
    index_path: Path  # uint32 .npy, window shape

    @property
    def shape(self) -> tuple[int, int]:
        return int(self.window.height), int(self.window.width)

    def index(self) -> np.ndarray:
        index = np.load(self.index_path, mmap_mode="r")
        if index.shape != self.shape:
            raise ValueError(f"cached index {self.index_path.name} is {index.shape}, window is {self.shape}")
        return index

    def check(self, ds: rasterio.DatasetReader) -> None:
        """Fail unless `ds` is on exactly this grid (same CRS and transform; window inside it)."""
        if ds.crs != self.src_crs or ds.transform != self.src_transform:
            raise ValueError(f"{ds.name} is not on the grid of cell grid {self.key}")
        if self.window.col_off + self.window.width > ds.width or self.window.row_off + self.window.height > ds.height:
            raise ValueError(f"{ds.name} is smaller than the window of cell grid {self.key}")


def clip_window(ds: rasterio.DatasetReader, geometry: dict, cover_cells: np.ndarray | None = None, buffer_m: float = BUFFER_M) -> Window:
    """Whole-pixel window covering the geometry's bounds plus a buffer, and every hex in `cover_cells` whole.

    Fails if the window would cross the raster's edge: edge hexes would be partial.
    """
    lngs, lats = _coords(geometry)
    if ds.crs.is_geographic:
        dlat = buffer_m / 111_320
        dlng = dlat / np.cos(np.radians(max(abs(lats.min()), abs(lats.max()))))
        bounds = transform_bounds("EPSG:4326", ds.crs, lngs.min() - dlng, lats.min() - dlat, lngs.max() + dlng, lats.max() + dlat, densify_pts=21)
    else:
        if ds.crs.linear_units not in ("metre", "meter"):
            raise ValueError(f"projected CRS must be in meters, got {ds.crs.linear_units}")
        left, bottom, right, top = transform_bounds("EPSG:4326", ds.crs, lngs.min(), lats.min(), lngs.max(), lats.max(), densify_pts=21)
        bounds = (left - buffer_m, bottom - buffer_m, right + buffer_m, top + buffer_m)
    if cover_cells is not None and len(cover_cells):
        pts = np.array([pt for c in cover_cells for pt in h3.cell_to_boundary(int(c))], dtype=float)  # (lat, lng)
        cx, cy = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform(pts[:, 1], pts[:, 0])
        margin = 0 if ds.crs.is_geographic else 2 * abs(ds.transform.a)  # hex edges bow slightly between vertices
        bounds = (min(bounds[0], cx.min() - margin), min(bounds[1], cy.min() - margin), max(bounds[2], cx.max() + margin), max(bounds[3], cy.max() + margin))
    f = from_bounds(*bounds, transform=ds.transform)
    col0, row0 = int(np.floor(f.col_off)), int(np.floor(f.row_off))
    col1, row1 = int(np.ceil(f.col_off + f.width)), int(np.ceil(f.row_off + f.height))
    if col0 < 0 or row0 < 0 or col1 > ds.width or row1 > ds.height:
        raise ValueError(f"clip window {col0}:{col1} x {row0}:{row1} crosses the edge of {ds.name} ({ds.width} x {ds.height})")
    return Window(col0, row0, col1 - col0, row1 - row0)


def _coords(geometry: dict) -> tuple[np.ndarray, np.ndarray]:
    polys = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    pts = np.array([pt[:2] for poly in polys for ring in poly for pt in ring], dtype=float)
    return pts[:, 0], pts[:, 1]


def grid_key(crs, transform, window: Window, res: int = config.RES_WORK) -> str:
    spec = {"crs": crs.to_wkt(), "transform": list(transform)[:6], "window": [int(window.col_off), int(window.row_off), int(window.width), int(window.height)], "res": res}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def cell_grid(ds: rasterio.DatasetReader, geometry: dict | None, cover_cells: np.ndarray | None = None, cache_dir: Path = config.WORK / "cellgrid", res: int = config.RES_WORK) -> CellGrid:
    """Load the cached cell grid for this source grid and window, or build it.

    `cover_cells`: hexes that must lie whole inside the window (the pilot's res-5 `hex_base`).
    `geometry=None`: the raster is already a clip (e.g. `sources.nlcd.clip`), so the window is all of it.
    """
    window = Window(0, 0, ds.width, ds.height) if geometry is None else clip_window(ds, geometry, cover_cells)
    transform = ds.window_transform(window)
    key = grid_key(ds.crs, ds.transform, window, res)
    index_path = cache_dir / f"{key}.index.npy"
    cells_path = cache_dir / f"{key}.cells.npy"
    if not (index_path.exists() and cells_path.exists()):
        _build_cell_grid(ds.crs, transform, (int(window.height), int(window.width)), res, index_path, cells_path)
    return CellGrid(key, ds.crs, ds.transform, window, transform, np.load(cells_path), index_path)


def _build_cell_grid(crs, transform, shape: tuple[int, int], res: int, index_path: Path, cells_path: Path) -> None:
    height, width = shape
    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    to_src = Transformer.from_crs("EPSG:4326", crs, always_xy=True)

    # Every res-8 cell that overlaps the window (densified window outline in lat/lng).
    t = np.linspace(0, 1, 65)
    edge_cols = np.concatenate([t * width, np.full_like(t, width), (1 - t) * width, np.zeros_like(t)])
    edge_rows = np.concatenate([np.zeros_like(t), t * height, np.full_like(t, height), (1 - t) * height])
    xs, ys = transform @ (edge_cols, edge_rows)
    lngs, lats = to_wgs.transform(np.asarray(xs), np.asarray(ys))
    outline = h3.LatLngPoly(list(zip(lats, lngs)))
    cells = np.array(sorted(h3.h3shape_to_cells_experimental(outline, res, contain="overlap")), dtype=np.uint64)
    if len(cells) >= np.iinfo(np.uint32).max:
        raise ValueError("too many cells for a uint32 index")

    # Hexagon outlines in the raster's CRS, vectorized over all vertices.
    rings = [h3.cell_to_boundary(int(c)) for c in cells]  # tuples of (lat, lng)
    nv = np.array([len(r) for r in rings])
    flat = np.array([pt for r in rings for pt in r], dtype=float)
    vx, vy = to_src.transform(flat[:, 1], flat[:, 0])
    inv = ~transform
    _, vrow = inv @ (vx, vy)
    starts = np.concatenate([[0], np.cumsum(nv)[:-1]])
    row_min = np.minimum.reduceat(vrow, starts)
    row_max = np.maximum.reduceat(vrow, starts)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = index_path.with_name(f"{index_path.stem}.{os.getpid()}.part.npy")
    index = np.lib.format.open_memmap(tmp, mode="w+", dtype=np.uint32, shape=(height, width))
    for r0 in range(0, height, STRIP_ROWS):
        r1 = min(r0 + STRIP_ROWS, height)
        hit = np.nonzero((row_max >= r0) & (row_min <= r1))[0]
        shapes = []
        for k in hit:
            s = starts[k]
            ring = list(zip(vx[s : s + nv[k]], vy[s : s + nv[k]]))
            shapes.append(({"type": "Polygon", "coordinates": [ring + [ring[0]]]}, int(k) + 1))
        strip_transform = transform @ rasterio.Affine.translation(0, r0)
        index[r0:r1] = rasterize(shapes, out_shape=(r1 - r0, width), transform=strip_transform, fill=NO_CELL, dtype="uint32")
        uncovered = int((index[r0:r1] == NO_CELL).sum())
        if uncovered:
            raise ValueError(f"{uncovered} pixels in rows {r0}:{r1} fall in no hexagon")
    index.flush()
    del index
    cells_tmp = cells_path.with_name(f"{cells_path.stem}.{os.getpid()}.part.npy")
    np.save(cells_tmp, cells)
    cells_tmp.rename(cells_path)
    tmp.rename(index_path)  # last: the index's existence marks a complete build


def _strips(grid: CellGrid):
    height, _ = grid.shape
    for r0 in range(0, height, REDUCE_ROWS):
        r1 = min(r0 + REDUCE_ROWS, height)
        win = Window(grid.window.col_off, grid.window.row_off + r0, grid.window.width, r1 - r0)
        yield r0, r1, win


def categorical_counts(ds: rasterio.DatasetReader, grid: CellGrid, classes: list[int], band: int = 1) -> tuple[pa.Table, pa.Table]:
    """One raster: see `categorical_counts_many`."""
    counts, totals = categorical_counts_many([ds], grid, classes, band)
    return counts[0], totals


def categorical_counts_many(datasets: list[rasterio.DatasetReader], grid: CellGrid, classes: list[int], band: int = 1) -> tuple[list[pa.Table], pa.Table]:
    """([counts per dataset], totals) for rasters on the same grid, e.g. every year of one source.

    counts: pixels per (res-8 cell, class) for the listed classes. totals: `n_total`, all
    pixels per cell. Pixels with nodata or any value not in `classes` count toward
    `n_total` only, so `valid_frac` = sum(n) / n_total. A cell with no valid pixel has no
    count rows: its fractions are NULL, never 0 (hard rule 1). Each block of the cell index is
    read once and counted for every dataset (the index is the slow read).
    """
    _check_distinct(datasets)
    lookups = []
    for ds in datasets:
        grid.check(ds)
        lookup = np.full(_lookup_size(ds.dtypes[band - 1], classes), len(classes), dtype=np.int32)  # len(classes) = invalid
        lookup[np.asarray(classes)] = np.arange(len(classes), dtype=np.int32)
        lookups.append(lookup)
    k = len(classes) + 1
    ncell = len(grid.cells) + 1
    _check_key_range(ncell * k)
    counts = [np.zeros(ncell * k, dtype=np.int32) for _ in datasets]  # per-cell counts are small; keeps 8 years ≈ 250 MB
    n_total = np.zeros(ncell, dtype=np.int64)
    def count(ds, lookup, base, win):
        return np.bincount((base + lookup[ds.read(band, window=win)]).ravel(), minlength=ncell * k).astype(np.int32)

    index = grid.index()
    with ThreadPoolExecutor(REDUCE_THREADS) as pool:
        for r0, r1, win in _strips(grid):
            idx = np.asarray(index[r0:r1]).astype(np.int32)
            n_total += np.bincount(idx.ravel(), minlength=ncell)
            base = idx * k
            for acc, c in zip(counts, pool.map(lambda ds, lookup: count(ds, lookup, base, win), datasets, lookups)):
                acc += c
    has = n_total[1:] > 0
    totals = pa.table({"h3": pa.array(grid.cells[has], pa.uint64()), "n_total": pa.array(n_total[1:][has], pa.int64())})
    tables = []
    for acc in counts:
        c = acc.reshape(ncell, k)[1:, :-1]  # drop "no cell" and "invalid"
        cell_i, cls_i = np.nonzero(c)
        tables.append(
            pa.table(
                {
                    "h3": pa.array(grid.cells[cell_i], pa.uint64()),
                    "class": pa.array(np.asarray(classes)[cls_i], pa.int32()),
                    "n": pa.array(c[cell_i, cls_i], pa.int64()),
                }
            )
        )
    return tables, totals


def continuous_sums(ds: rasterio.DatasetReader, grid: CellGrid, valid_min: float, valid_max: float, band: int = 1) -> pa.Table:
    """One raster: see `continuous_sums_many`."""
    return continuous_sums_many([ds], grid, valid_min, valid_max, band)[0]


def continuous_sums_many(datasets: list[rasterio.DatasetReader], grid: CellGrid, valid_min: float, valid_max: float, band: int = 1) -> list[pa.Table]:
    """Per dataset, per res-8 cell: `sum` of valid values, `n_valid` and `n_total` pixels.

    Valid = not nodata and within [valid_min, valid_max]; everything else counts in
    `n_total` only. `sum` is NULL where `n_valid` is 0, so means come out NULL, never 0
    (hard rule 1). Each block of the cell index is read once for every dataset.
    """
    _check_distinct(datasets)
    for ds in datasets:
        grid.check(ds)
    ncell = len(grid.cells) + 1
    packed = all(np.dtype(ds.dtypes[band - 1]).kind in "ui" for ds in datasets) and valid_min >= 0 and np.isfinite(valid_max)
    totals = [np.zeros(ncell, dtype=np.float64) for _ in datasets]
    n_valid = [np.zeros(ncell, dtype=np.int64) for _ in datasets]
    n_total = np.zeros(ncell, dtype=np.int64)

    def reduce(ds, idx, win):
        v = ds.read(band, window=win).ravel()  # native dtype: no float64 copy of the strip
        ok = (v >= valid_min) & (v <= valid_max)
        if v.dtype.kind == "f":
            ok &= ~np.isnan(v)
        nodata = ds.nodatavals[band - 1]
        if nodata is not None:
            ok &= v != nodata
        cell = idx[ok]
        if packed:
            both = np.bincount(cell, weights=v[ok] + float(PACK), minlength=ncell)
            n = np.floor(both / PACK)
            return n.astype(np.int64), both - n * PACK
        return np.bincount(cell, minlength=ncell), np.bincount(cell, weights=v[ok], minlength=ncell)

    index = grid.index()
    with ThreadPoolExecutor(REDUCE_THREADS) as pool:
        for r0, r1, win in _strips(grid):
            idx = np.asarray(index[r0:r1]).ravel().astype(np.int32)
            strip_total = np.bincount(idx, minlength=ncell)
            # Packing is exact only while a cell's strip sum stays below PACK.
            # Bin 0 (no cell) is dropped later, so it doesn't count here.
            if packed and strip_total[1:].max() * valid_max >= PACK:
                raise ValueError(f"cells too large to pack ({strip_total[1:].max()} px × {valid_max})")
            n_total += strip_total
            for total, nv, (n, s) in zip(totals, n_valid, pool.map(lambda ds: reduce(ds, idx, win), datasets)):
                nv += n
                total += s
    has = n_total[1:] > 0
    return [
        pa.table(
            {
                "h3": pa.array(grid.cells[has], pa.uint64()),
                "sum": pa.array(total[1:][has], pa.float64(), mask=nv[1:][has] == 0),
                "n_valid": pa.array(nv[1:][has], pa.int64()),
                "n_total": pa.array(n_total[1:][has], pa.int64()),
            }
        )
        for total, nv in zip(totals, n_valid)
    ]


def _check_distinct(datasets: list) -> None:
    if len({id(ds) for ds in datasets}) != len(datasets):
        raise ValueError("each dataset needs its own handle: they are read in parallel threads")


def _check_key_range(n: int) -> None:
    if n >= np.iinfo(np.int32).max:
        raise ValueError(f"{n:,} cell x class bins do not fit 32-bit keys")


def _lookup_size(dtype: str, classes: list[int]) -> int:
    """Length of the value → class lookup, indexed by raw pixel values.

    Signed 16-bit rasters (LANDFIRE: negative fill codes) are allowed when every class is
    non-negative: a negative pixel indexes the lookup's upper half (numpy wraps negative
    indexes), which holds no class, so it counts as invalid.
    """
    dt = np.dtype(dtype)
    if dt.itemsize > 2 or dt.kind not in "ui" or (dt.kind == "i" and dt.itemsize != 2):
        raise ValueError(f"categorical rasters must be unsigned 8- or 16-bit, or signed 16-bit, got {dtype}")
    size = 1 << (8 * dt.itemsize)
    lo, hi = (0, size - 1) if dt.kind == "u" else (0, size // 2 - 1)
    if len(classes) and (min(classes) < lo or max(classes) > hi):
        raise ValueError(f"classes must lie in {lo}–{hi} for {dtype}")
    return size


def rollup(table: pa.Table, members: dict[int, np.ndarray], group_cols: list[str], sum_cols: list[str]) -> dict[int, pa.Table]:
    """Sum res-8 rows up to each resolution in `members` ({res: hex_base cells at res}).

    At each resolution every res-8 row whose ancestor is a `hex_base` hex counts, so a
    border hex sums all its children, not only those inside the state (whole edge hexes).
    Returns {res: table} with `h3`, `res`, `p3`, the group columns and the summed columns.
    Sums only: callers compute fractions and means from the summed counts afterwards.
    """
    con = h3util.con()
    t = table  # noqa: F841 (read by DuckDB)
    groups = "".join(f", {c}" for c in group_cols)
    sums = ", ".join(f"sum({c})::{_sum_type(table, c)} AS {c}" for c in sum_cols)
    out = {}
    for res, cells in members.items():
        m = pa.table({"h3": pa.array(cells, pa.uint64())})  # noqa: F841
        cell = "h3" if res == config.RES_WORK else f"h3_cell_to_parent(h3, {int(res)})"
        out[res] = con.sql(
            f"SELECT {cell} AS h3, {int(res)}::TINYINT AS res, h3_cell_to_parent({cell}, {config.RES_PARTITION}) AS p3{groups}, {sums} "
            f"FROM t WHERE {cell} IN (SELECT h3 FROM m) GROUP BY ALL ORDER BY h3{groups}"
        ).to_arrow_table()
    return out


def require_coverage(rolled: dict[int, pa.Table], members: dict[int, np.ndarray]) -> None:
    """Fail if any `hex_base` hex got no pixels (it would vanish from the table silently)."""
    for res, cells in members.items():
        if len(rolled[res]) != len(cells):
            raise ValueError(f"r{res}: {len(cells) - len(rolled[res])} hex_base hexes have no pixels in the clip")


def _sum_type(table: pa.Table, col: str) -> str:
    return "DOUBLE" if pa.types.is_floating(table.schema.field(col).type) else "BIGINT"
