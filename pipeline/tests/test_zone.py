"""PHZM half-zones and hex_zone on synthetic grids (data contract: Tables → hex_zone)."""

import zipfile

import numpy as np
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest
import rasterio
from rasterio.transform import from_origin

from treemap_pipeline import config, raster
from treemap_pipeline.build import hex_base, zone
from treemap_pipeline.sources import phzm

# Synthetic data, not real: a geographic grid of half-zone indexes around Madison.
LNG, LAT = -89.40, 43.07
GEOMETRY = {"type": "Polygon", "coordinates": [[[LNG - 0.02, LAT - 0.015], [LNG + 0.02, LAT - 0.015], [LNG + 0.02, LAT + 0.015], [LNG - 0.02, LAT + 0.015], [LNG - 0.02, LAT - 0.015]]]}
PX, SIZE = 0.0005, 300  # about 40 × 55 m: many pixels per res-8 hex


def test_half_zone_index_and_labels():
    t = np.array([-60, -55.01, -55, -10, -5.5, -5, 0, 69.9, -9999, np.nan, -80, 90])
    idx = phzm.half_zone_index(t)
    assert idx.tolist() == [0, 0, 1, 10, 10, 11, 12, 25, 255, 255, 0, 25]
    assert [phzm.label(i) for i in (0, 1, 10, 11, 25)] == ["1a", "1b", "6a", "6b", "13b"]
    assert [phzm.number(i) for i in (10, 11, 6)] == [6.0, 6.5, 4.0]


@pytest.fixture(scope="module")
def members():
    return {res: t["h3"].to_numpy() for res, t in hex_base.build_hex_base(GEOMETRY).items()}


@pytest.fixture(scope="module")
def clip(tmp_path_factory, members):
    """Half-zones 8–11 (5a–6b) at random, one member res-8 hex all nodata."""
    transform = from_origin(LNG - SIZE * PX / 2, LAT + SIZE * PX / 2, PX, PX)
    data = np.random.default_rng(3).integers(8, 12, size=(SIZE, SIZE)).astype(np.uint8)
    path = tmp_path_factory.mktemp("phzm") / "halfzone.tif"
    profile = dict(driver="GTiff", width=SIZE, height=SIZE, count=1, dtype="uint8", crs="EPSG:4269", transform=transform, nodata=phzm.NODATA)
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(data, 1)
    with rasterio.open(path) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=tmp_path_factory.mktemp("g"))
    target = int(members[8][len(members[8]) // 2])
    data[np.asarray(grid.index()) == int(np.searchsorted(grid.cells, np.uint64(target))) + 1] = phzm.NODATA
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(data, 1)
    return path, target


@pytest.fixture(scope="module")
def built(clip, members, tmp_path_factory):
    return zone.build_zone(clip[0], members, cache_dir=tmp_path_factory.mktemp("cellgrid"))


def test_schema_and_rows(built, members):
    for res, t in built.items():
        assert t.schema.equals(zone.SCHEMA)
        assert t["h3"].to_pylist() == sorted(int(c) for c in members[res])
        vf = t["valid_frac"].to_numpy(zero_copy_only=False)
        assert ((vf >= 0) & (vf <= 1)).all()


def test_matches_naive_count(built, clip, tmp_path_factory):
    """Each res-8 hex: coldest = min half-zone of its pixels, mode = most common (colder on a tie)."""
    with rasterio.open(clip[0]) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=tmp_path_factory.mktemp("g2"))
        data = ds.read(1)
    index = np.asarray(grid.index())
    t = built[8]
    for i in range(0, t.num_rows, max(1, t.num_rows // 20)):
        h = t["h3"][i].as_py()
        if h == clip[1]:
            continue
        vals = data[index == int(np.searchsorted(grid.cells, np.uint64(h))) + 1]
        valid = vals[vals != phzm.NODATA]
        counts = np.bincount(valid, minlength=phzm.HALF_ZONES)
        assert t["zone_coldest"][i].as_py() == phzm.label(int(valid.min()))
        assert t["zone_coldest_num"][i].as_py() == phzm.number(int(valid.min()))
        assert t["zone_mode"][i].as_py() == phzm.label(int(np.argmax(counts)))  # argmax: first = colder
        assert t["valid_frac"][i].as_py() == pytest.approx(len(valid) / len(vals))


def test_all_nodata_hex_is_null(built, clip):
    row = built[8].filter(pc.equal(built[8]["h3"], clip[1]))
    assert row.num_rows == 1
    assert row["zone_coldest"][0].as_py() is None
    assert row["zone_coldest_num"][0].as_py() is None
    assert row["zone_mode"][0].as_py() is None
    assert row["valid_frac"][0].as_py() == 0


def test_coldest_is_coldest_of_children(built):
    """A parent's coldest half-zone is the coldest of its children's (roll-up of counts)."""
    import h3

    child = {h: v for h, v in zip(built[8]["h3"].to_pylist(), built[8]["zone_coldest_num"].to_pylist())}
    for h, v in zip(built[7]["h3"].to_pylist(), built[7]["zone_coldest_num"].to_pylist()):
        kids = [child[c] for c in (h3.str_to_int(x) for x in h3.cell_to_children(h3.int_to_str(h), 8)) if c in child and child[c] is not None]
        if kids:
            assert v == min(kids)


def test_clip_upsamples_without_changing_values(tmp_path, monkeypatch, members):
    """phzm.clip: °F BIL in a zip → half-zone tif, UPSAMPLE× finer, values only repeated."""
    monkeypatch.setattr(config, "RAW", tmp_path / "raw")
    raw = tmp_path / "raw" / "phzm"
    raw.mkdir(parents=True)
    n, px = 400, 0.002  # covers the res-5 hexes plus the 10 km buffer
    temps = np.random.default_rng(1).uniform(-30, 0, size=(n, n)).astype(np.float32)
    temps[:5, :5] = phzm.NODATA_IN
    bil = tmp_path / phzm.MEMBER
    with rasterio.open(bil, "w", driver="EHdr", width=n, height=n, count=1, dtype="float32", crs="EPSG:4269", transform=from_origin(LNG - n * px / 2, LAT + n * px / 2, px, px), nodata=phzm.NODATA_IN) as ds:
        ds.write(temps, 1)
    with zipfile.ZipFile(raw / phzm.SOURCE.zip_name(phzm.YEAR), "w") as zf:
        for f in tmp_path.glob(bil.stem + ".*"):
            zf.write(f, f.name)
    out = phzm.clip(GEOMETRY, members[5])
    assert out.with_suffix(".window.json").exists()
    with rasterio.open(f"/vsizip/{raw / phzm.SOURCE.zip_name(phzm.YEAR)}/{phzm.MEMBER}") as src, rasterio.open(out) as dst:
        window = raster.clip_window(src, GEOMETRY, members[5])
        coarse = phzm.half_zone_index(src.read(1, window=window))
        fine = dst.read(1)
        assert dst.res[0] == pytest.approx(src.res[0] / phzm.UPSAMPLE)
        assert dst.transform.c == pytest.approx(src.window_transform(window).c)
    assert fine.shape == (coarse.shape[0] * phzm.UPSAMPLE, coarse.shape[1] * phzm.UPSAMPLE)
    assert (fine[:: phzm.UPSAMPLE, :: phzm.UPSAMPLE] == coarse).all()
    assert set(np.unique(fine)) <= set(np.unique(coarse))
    assert phzm.clip(GEOMETRY, members[5]) == out  # second call reuses the clip


def test_real_output_if_built():
    path = config.OUT / "hex" / "hex_zone" / "r7"
    if not path.exists():
        pytest.skip("hex_zone not built")
    t = pq.read_table(path)
    num = t["zone_coldest_num"].to_numpy(zero_copy_only=False)
    # Wisconsin on the 2023 map spans 3b–6a (3.5–6.0).
    assert np.nanmin(num) >= 3.0 and np.nanmax(num) <= 6.5
