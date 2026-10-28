"""raster: cell grid, reducers and roll-up on a synthetic GeoTIFF (data contract: Raster → hex method)."""

import os

import h3.api.basic_int as h3
import numpy as np
import pyarrow as pa
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from treemap_pipeline import config, h3util, raster

# Synthetic raster, not real data: 30 m Albers (EPSG:5070) around Madison, WI.
PX = 30.0
SIZE = 1600  # 48 km: room for a whole res-5 hex around the test square
NODATA = 250
CLASSES = [11, 41, 42, 82]
UNLISTED = 99  # a valid-looking value outside `CLASSES`: counts toward n_total only
# A small square (about 3 x 3 km) well inside the raster; the window is it plus 10 km.
LNG, LAT = -89.40, 43.07
GEOMETRY = {"type": "Polygon", "coordinates": [[[LNG - 0.02, LAT - 0.015], [LNG + 0.02, LAT - 0.015], [LNG + 0.02, LAT + 0.015], [LNG - 0.02, LAT + 0.015], [LNG - 0.02, LAT - 0.015]]]}


@pytest.fixture(scope="module")
def tif(tmp_path_factory):
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform(LNG, LAT)
    transform = from_origin(round(x) - SIZE * PX / 2, round(y) + SIZE * PX / 2, PX, PX)
    rng = np.random.default_rng(7)
    cats = rng.choice(CLASSES + [UNLISTED, NODATA], size=(SIZE, SIZE), p=[0.3, 0.3, 0.2, 0.1, 0.05, 0.05]).astype(np.uint8)
    cont = rng.uniform(0, 100, size=(SIZE, SIZE)).astype(np.float32)
    cont[cats == NODATA] = -9999
    path = tmp_path_factory.mktemp("raster") / "synthetic.tif"
    profile = dict(driver="GTiff", width=SIZE, height=SIZE, count=2, dtype="float32", crs="EPSG:5070", transform=transform, nodata=-9999, tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(cont, 2)
        ds.write(cats.astype(np.float32), 1)
    cat_path = path.with_name("cats.tif")
    with rasterio.open(cat_path, "w", **{**profile, "count": 1, "dtype": "uint8", "nodata": NODATA}) as ds:
        ds.write(cats, 1)
    return {"cats": cat_path, "cont": path}


@pytest.fixture(scope="module")
def grid(tif, tmp_path_factory):
    with rasterio.open(tif["cats"]) as ds:
        return raster.cell_grid(ds, GEOMETRY, cache_dir=tmp_path_factory.mktemp("cellgrid"))


def exact_cells(grid: raster.CellGrid) -> np.ndarray:
    """Res-8 cell of every pixel center in the window, by direct indexing (the reference)."""
    h, w = grid.shape
    cols, rows = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    xs, ys = grid.transform @ (cols.ravel(), rows.ravel())
    lngs, lats = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True).transform(np.asarray(xs), np.asarray(ys))
    t = pa.table({"lat": lats, "lng": lngs})  # noqa: F841
    return h3util.con().sql(f"SELECT h3_latlng_to_cell(lat, lng, {config.RES_WORK}) AS c FROM t").to_arrow_table()["c"].to_numpy().reshape(h, w)


def test_window_is_buffered_and_inside(tif, grid):
    h, w = grid.shape
    # 3.3 km + 2 x 10 km buffer ≈ 23 km ≈ 780 px; the raster is 1600 px.
    assert 700 < w < 900 and 700 < h < 900
    assert grid.window.col_off > 0 and grid.window.row_off > 0


def test_cell_grid_matches_pixel_center_indexing(grid):
    index = np.asarray(grid.index())
    assert (index != raster.NO_CELL).all(), "every pixel in the window gets a cell"
    ours = grid.cells[index.astype(np.int64) - 1]
    share = (ours != exact_cells(grid)).mean()
    # Rasterizing uses straight hexagon edges in Albers; H3 edges are straight in its own
    # gnomonic projection. The difference is centimeters, so only pixel centers almost
    # exactly on an edge can disagree.
    assert share < 1e-4, f"{share:.2e} of pixels disagree with direct indexing"


def test_cell_grid_is_cached(tif, grid):
    cache_dir = grid.index_path.parent
    mtime = os.path.getmtime(grid.index_path)
    with rasterio.open(tif["cats"]) as ds:
        again = raster.cell_grid(ds, GEOMETRY, cache_dir=cache_dir)
    assert again.key == grid.key
    assert os.path.getmtime(again.index_path) == mtime
    # A different window is a different grid key.
    other = dict(GEOMETRY, coordinates=[[[x + 0.01, y] for x, y in GEOMETRY["coordinates"][0]]])
    with rasterio.open(tif["cats"]) as ds:
        assert raster.grid_key(ds.crs, ds.transform, raster.clip_window(ds, other)) != grid.key
    # A cached index whose shape no longer matches the window is refused.
    bad = raster.CellGrid(grid.key, grid.src_crs, grid.src_transform, raster.Window(grid.window.col_off, grid.window.row_off, 10, 10), grid.transform, grid.cells, grid.index_path)
    with pytest.raises(ValueError, match="cached index"):
        bad.index()


def naive_counts(tif, grid) -> dict[tuple[int, int], int]:
    with rasterio.open(tif["cats"]) as ds:
        values = ds.read(1, window=grid.window)
    cells = grid.cells[np.asarray(grid.index()).astype(np.int64) - 1]
    out = {}
    for c, v in zip(cells.ravel().tolist(), values.ravel().tolist()):
        out[(c, v)] = out.get((c, v), 0) + 1
    return out


@pytest.mark.parametrize("strip_rows", [raster.STRIP_ROWS, 97])
def test_categorical_counts(tif, grid, monkeypatch, strip_rows):
    monkeypatch.setattr(raster, "STRIP_ROWS", strip_rows)
    with rasterio.open(tif["cats"]) as ds:
        counts, totals = raster.categorical_counts(ds, grid, CLASSES)
    naive = naive_counts(tif, grid)
    ours = {(c, k): n for c, k, n in zip(counts["h3"].to_pylist(), counts["class"].to_pylist(), counts["n"].to_pylist())}
    assert ours == {key: n for key, n in naive.items() if key[1] in CLASSES}
    total = {}
    for (c, _), n in naive.items():
        total[c] = total.get(c, 0) + n
    assert dict(zip(totals["h3"].to_pylist(), totals["n_total"].to_pylist())) == total
    assert sum(totals["n_total"].to_pylist()) == grid.shape[0] * grid.shape[1]
    valid = sum(counts["n"].to_pylist()) / sum(totals["n_total"].to_pylist())
    assert 0.85 < valid < 0.95  # 10% of pixels are nodata or unlisted


@pytest.mark.parametrize("strip_rows", [raster.STRIP_ROWS, 97])
def test_continuous_sums(tif, grid, monkeypatch, strip_rows):
    monkeypatch.setattr(raster, "STRIP_ROWS", strip_rows)
    with rasterio.open(tif["cont"]) as ds:
        sums = raster.continuous_sums(ds, grid, valid_min=0, valid_max=100, band=2)
        values = ds.read(2, window=grid.window)
    cells = grid.cells[np.asarray(grid.index()).astype(np.int64) - 1].ravel()
    v = values.ravel().astype(np.float64)
    ok = v != -9999
    for c, s, nv, nt in list(zip(*(sums[k].to_pylist() for k in ("h3", "sum", "n_valid", "n_total"))))[:200]:
        sel = cells == c
        assert nt == sel.sum()
        assert nv == (sel & ok).sum()
        assert s == pytest.approx(v[sel & ok].sum(), rel=1e-9)


def members_by_res(geometry) -> dict[int, np.ndarray]:
    """As hex_base: res-8 cells with centers inside, and their ancestors at res 7, 6, 5."""
    m8 = np.array(sorted(h3.h3shape_to_cells(h3.geo_to_h3shape(geometry), 8)), dtype=np.uint64)
    return {8: m8, **{r: np.unique(h3util.parents(m8, r)) for r in (7, 6, 5)}}


def test_rollup_sums_children_and_keeps_members(tif, grid):
    with rasterio.open(tif["cats"]) as ds:
        counts, totals = raster.categorical_counts(ds, grid, CLASSES)
    members = members_by_res(GEOMETRY)
    rolled = raster.rollup(totals, members, group_cols=[], sum_cols=["n_total"])
    assert set(rolled[8]["h3"].to_pylist()) == set(members[8].tolist())
    all8 = dict(zip(totals["h3"].to_pylist(), totals["n_total"].to_pylist()))  # every res-8 cell in the window
    for res in (7, 6):
        got = rolled[res]
        assert set(got["h3"].to_pylist()) == set(members[res].tolist())
        assert set(got["res"].to_pylist()) == {res}
        assert all(p3 == h3.cell_to_parent(c, 3) for c, p3 in zip(got["h3"].to_pylist(), got["p3"].to_pylist()))
        for c, n in zip(got["h3"].to_pylist(), got["n_total"].to_pylist()):
            children = h3.cell_to_children(c, 8)
            assert all(ch in all8 for ch in children), "the window covers the hex whole"
            assert n == sum(all8[ch] for ch in children)
    by_class = raster.rollup(counts, members, group_cols=["class"], sum_cols=["n"])
    assert by_class[5]["h3"].to_pylist() == sorted(by_class[5]["h3"].to_pylist())


def test_border_hex_is_whole(tif, grid):
    """A res-7 hex straddling the border counts its children outside the state too."""
    with rasterio.open(tif["cats"]) as ds:
        _, totals = raster.categorical_counts(ds, grid, CLASSES)
    members = members_by_res(GEOMETRY)
    rolled = dict(zip(*(raster.rollup(totals, members, [], ["n_total"])[7][k].to_pylist() for k in ("h3", "n_total"))))
    m8 = set(members[8].tolist())
    border = [c for c in members[7].tolist() if not set(h3.cell_to_children(c, 8)) <= m8]
    assert border, "the test square has border res-7 hexes"
    all8 = dict(zip(totals["h3"].to_pylist(), totals["n_total"].to_pylist()))
    for c in border:
        inside_only = sum(all8[ch] for ch in h3.cell_to_children(c, 8) if ch in m8)
        assert rolled[c] > inside_only


def test_cover_cells_widen_the_window(tif):
    members = members_by_res(GEOMETRY)
    with rasterio.open(tif["cats"]) as ds:
        plain = raster.clip_window(ds, GEOMETRY, buffer_m=0)
        covered = raster.clip_window(ds, GEOMETRY, cover_cells=members[5], buffer_m=0)
        assert covered.width > plain.width and covered.height > plain.height
        # Every vertex of every res-5 hex is inside the covered window.
        pts = np.array([pt for c in members[5] for pt in h3.cell_to_boundary(int(c))])
        xs, ys = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True).transform(pts[:, 1], pts[:, 0])
        cols, rows = ~ds.window_transform(covered) @ (xs, ys)
        assert cols.min() >= 0 and rows.min() >= 0 and cols.max() <= covered.width and rows.max() <= covered.height


def test_window_crossing_the_raster_edge_fails(tif):
    big = {"type": "Polygon", "coordinates": [[[LNG - 0.3, LAT - 0.2], [LNG + 0.3, LAT - 0.2], [LNG + 0.3, LAT + 0.2], [LNG - 0.3, LAT - 0.2]]]}
    with rasterio.open(tif["cats"]) as ds, pytest.raises(ValueError, match="crosses the edge"):
        raster.clip_window(ds, big)


def test_geographic_crs_buffer(tmp_path):
    path = tmp_path / "geo.tif"
    res_deg = 1 / 120  # about 800 m, like PHZM
    with rasterio.open(path, "w", driver="GTiff", width=600, height=600, count=1, dtype="uint8", crs="EPSG:4326", transform=from_origin(LNG - 2.5, LAT + 2.5, res_deg, res_deg)) as ds:
        ds.write(np.zeros((600, 600), np.uint8), 1)
    with rasterio.open(path) as ds:
        w = raster.clip_window(ds, GEOMETRY)
    # 0.04° x 0.03° square + 2 x 10 km ≈ 0.29° x 0.21° ≈ 35 x 26 px.
    assert 33 <= w.width <= 38 and 24 <= w.height <= 29


def test_build_in_small_strips_matches(tif, grid, tmp_path, monkeypatch):
    monkeypatch.setattr(raster, "STRIP_ROWS", 97)
    with rasterio.open(tif["cats"]) as ds:
        small = raster.cell_grid(ds, GEOMETRY, cache_dir=tmp_path)
    assert small.key == grid.key
    assert np.array_equal(np.asarray(small.index()), np.asarray(grid.index()))


def test_all_nodata_cell_is_null_not_zero(tif, grid, tmp_path):
    with rasterio.open(tif["cont"]) as src:
        profile, data = src.profile, src.read(2)
    data[:] = -9999  # nothing valid anywhere
    path = tmp_path / "empty.tif"
    with rasterio.open(path, "w", **{**profile, "count": 1}) as ds:
        ds.write(data, 1)
    with rasterio.open(path) as ds:
        sums = raster.continuous_sums(ds, grid, 0, 100)
    with rasterio.open(tif["cats"]) as ds:
        counts, totals = raster.categorical_counts(ds, grid, [200])  # a class no pixel has
    assert sums["sum"].null_count == sums.num_rows
    assert set(sums["n_valid"].to_pylist()) == {0}
    assert counts.num_rows == 0 and totals.num_rows > 0  # fractions come out NULL, not 0


def test_mismatched_grid_and_signed_dtype_fail(tif, grid, tmp_path):
    with rasterio.open(tif["cats"]) as src:
        profile = src.profile
    shifted = tmp_path / "shifted.tif"
    t = profile["transform"]
    with rasterio.open(shifted, "w", **{**profile, "transform": rasterio.Affine(t.a, t.b, t.c + 30, t.d, t.e, t.f)}) as ds:
        ds.write(np.zeros((SIZE, SIZE), np.uint8), 1)
    with rasterio.open(shifted) as ds, pytest.raises(ValueError, match="not on the grid"):
        raster.categorical_counts(ds, grid, CLASSES)
    signed = tmp_path / "signed.tif"
    with rasterio.open(signed, "w", **{**profile, "dtype": "int16", "nodata": -1}) as ds:
        ds.write(np.zeros((SIZE, SIZE), np.int16), 1)
    with rasterio.open(signed) as ds, pytest.raises(ValueError, match="unsigned"):
        raster.categorical_counts(ds, grid, CLASSES)


def test_parents_vectorized_matches_h3():
    cells = np.array(sorted(h3.h3shape_to_cells(h3.geo_to_h3shape(GEOMETRY), 8)), dtype=np.uint64)
    assert h3util.parents(cells, 5).tolist() == [h3.cell_to_parent(int(c), 5) for c in cells]


def test_many_equals_one_at_a_time(tif, grid):
    with rasterio.open(tif["cats"]) as a, rasterio.open(tif["cats"]) as b:
        many, totals = raster.categorical_counts_many([a, b], grid, CLASSES)
        one, totals_one = raster.categorical_counts(a, grid, CLASSES)
    assert many[0].equals(one) and many[1].equals(one) and totals.equals(totals_one)
    with rasterio.open(tif["cont"]) as a:
        many_c = raster.continuous_sums_many([a, a], grid, 0, 100, band=2)
        assert many_c[0].equals(raster.continuous_sums(a, grid, 0, 100, band=2)) and many_c[1].equals(many_c[0])
