"""hex_canopy on synthetic clips (data contract: Tables → hex_canopy)."""

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from treemap_pipeline import h3util, raster
from treemap_pipeline.build import canopy, hex_base

# Synthetic clips, not real data: 30 m Albers around Madison, three "years".
PX, SIZE = 30.0, 1600
LNG, LAT = -89.40, 43.07
GEOMETRY = {"type": "Polygon", "coordinates": [[[LNG - 0.02, LAT - 0.015], [LNG + 0.02, LAT - 0.015], [LNG + 0.02, LAT + 0.015], [LNG - 0.02, LAT + 0.015], [LNG - 0.02, LAT - 0.015]]]}
YEARS = (1985, 2000, 2025)
NON_PROCESSING, BACKGROUND = 254, 255


@pytest.fixture(scope="module")
def members():
    return {res: t["h3"].to_numpy() for res, t in hex_base.build_hex_base(GEOMETRY).items()}


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    """TCC-like uint8 clips: 0–100 with some 254 and 255 pixels."""
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform(LNG, LAT)
    transform = from_origin(round(x) - SIZE * PX / 2, round(y) + SIZE * PX / 2, PX, PX)
    rng = np.random.default_rng(5)
    d = tmp_path_factory.mktemp("tcc")
    out = {}
    for year in YEARS:
        data = rng.integers(0, 101, size=(SIZE, SIZE)).astype(np.uint8)
        data[rng.random((SIZE, SIZE)) < 0.05] = NON_PROCESSING
        data[rng.random((SIZE, SIZE)) < 0.05] = BACKGROUND
        out[year] = d / f"tcc_{year}.tif"
        with rasterio.open(out[year], "w", driver="GTiff", width=SIZE, height=SIZE, count=1, dtype="uint8", crs="EPSG:5070", transform=transform, nodata=BACKGROUND, tiled=True, blockxsize=256, blockysize=256) as ds:
            ds.write(data, 1)
    return out


@pytest.fixture(scope="module")
def blank_hex(clips, members, tmp_path_factory):
    """Set one member res-8 hex to 254 in 2025 (its canopy_frac must be NULL, not 0)."""
    with rasterio.open(clips[2025]) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=tmp_path_factory.mktemp("g"))
        data, profile = ds.read(1), ds.profile
    target = int(members[8][len(members[8]) // 3])
    data[np.asarray(grid.index()) == int(np.searchsorted(grid.cells, np.uint64(target))) + 1] = NON_PROCESSING
    with rasterio.open(clips[2025], "w", **profile) as ds:
        ds.write(data, 1)
    return target


@pytest.fixture(scope="module")
def built(clips, members, blank_hex, tmp_path_factory):
    return canopy.build_canopy(clips, members, cache_dir=tmp_path_factory.mktemp("cellgrid"))


def test_schema_rows_and_ranges(built, members):
    for res, t in built.items():
        assert t.schema.equals(canopy.SCHEMA)
        assert t.num_rows == len(members[res]) * len(YEARS)
        keys = list(zip(t["h3"].to_pylist(), t["year"].to_pylist()))
        assert keys == sorted(keys)
        cf = t["canopy_frac"].to_numpy(zero_copy_only=False).astype(float)
        assert ((cf[~np.isnan(cf)] >= 0) & (cf[~np.isnan(cf)] <= 1)).all()
        vf = t["valid_frac"].to_numpy(zero_copy_only=False)
        assert ((vf >= 0) & (vf <= 1)).all()


def test_matches_naive_mean(built, clips, tmp_path_factory):
    """One res-7 hex in 2000: canopy_frac and valid_frac equal a direct count over its pixels."""
    with rasterio.open(clips[2000]) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=tmp_path_factory.mktemp("g2"))
        data = ds.read(1)
    cells = grid.cells[np.asarray(grid.index()).astype(np.int64) - 1]
    parent7 = h3util.parents(cells.ravel(), 7).reshape(cells.shape)
    t = built[7].filter(pc.equal(built[7]["year"], 2000))
    target = t["h3"][1].as_py()
    vals = data[parent7 == np.uint64(target)]
    valid = vals[vals <= 100]
    row = t.filter(pc.equal(t["h3"], pa.scalar(target, pa.uint64())))
    assert row["canopy_frac"][0].as_py() == pytest.approx(valid.mean() / 100, rel=1e-6)
    assert row["valid_frac"][0].as_py() == pytest.approx(len(valid) / len(vals), rel=1e-6)


def test_no_valid_pixel_is_null(built, blank_hex):
    t = built[8].filter(pc.equal(built[8]["h3"], pa.scalar(blank_hex, pa.uint64())))
    by_year = dict(zip(t["year"].to_pylist(), zip(t["canopy_frac"].to_pylist(), t["valid_frac"].to_pylist())))
    assert by_year[2025] == (None, 0)
    assert by_year[1985][0] is not None


def test_batched_passes_match_one_pass(built, clips, members, monkeypatch, tmp_path):
    monkeypatch.setattr(canopy, "YEARS_PER_PASS", 2)
    again = canopy.build_canopy(clips, members, cache_dir=tmp_path)
    for res in built:
        assert again[res].equals(built[res])


def test_missing_hex_fails(clips, members, tmp_path):
    extra = dict(members)
    far = h3util.parents(np.array([0x8828308281FFFFF], np.uint64), 8)
    extra[8] = np.sort(np.concatenate([members[8], far]))
    with pytest.raises(ValueError, match="no pixels in the clip"):
        canopy.build_canopy(clips, extra, cache_dir=tmp_path)
