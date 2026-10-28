"""hex_landcover and land_frac on synthetic clips (data contract: Tables → hex_landcover; Checks)."""

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from treemap_pipeline import config, h3util, io, raster
from treemap_pipeline.build import hex_base, landcover
from treemap_pipeline.build.landcover import CLASSES, GROUPS

# Synthetic clips, not real data: 30 m Albers around Madison, three "years".
PX, SIZE, NODATA = 30.0, 1600, 250
LNG, LAT = -89.40, 43.07
GEOMETRY = {"type": "Polygon", "coordinates": [[[LNG - 0.02, LAT - 0.015], [LNG + 0.02, LAT - 0.015], [LNG + 0.02, LAT + 0.015], [LNG - 0.02, LAT + 0.015], [LNG - 0.02, LAT - 0.015]]]}
YEARS = (1985, 2000, 2025)


@pytest.fixture(scope="module")
def members():
    tables = hex_base.build_hex_base(GEOMETRY)
    return {res: t["h3"].to_numpy() for res, t in tables.items()}


@pytest.fixture(scope="module")
def clips(tmp_path_factory, members):
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform(LNG, LAT)
    transform = from_origin(round(x) - SIZE * PX / 2, round(y) + SIZE * PX / 2, PX, PX)
    rng = np.random.default_rng(3)
    out = {}
    d = tmp_path_factory.mktemp("clips")
    for year in YEARS:
        data = rng.choice(CLASSES + [NODATA], size=(SIZE, SIZE)).astype(np.uint8)
        out[year] = d / f"lc_{year}.tif"
        with rasterio.open(out[year], "w", driver="GTiff", width=SIZE, height=SIZE, count=1, dtype="uint8", crs="EPSG:5070", transform=transform, nodata=NODATA, tiled=True, blockxsize=256, blockysize=256) as ds:
            ds.write(data, 1)
    return out


@pytest.fixture(scope="module")
def nodata_hex(clips, members, tmp_path_factory):
    """Blank one member res-8 hex in the 2025 clip (its fractions must be NULL, not 0); return its id."""
    with rasterio.open(clips[2025]) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=tmp_path_factory.mktemp("g"))
        data = ds.read(1)
        profile = ds.profile
    target = int(members[8][len(members[8]) // 2])
    k = int(np.searchsorted(grid.cells, np.uint64(target)))
    data[np.asarray(grid.index()) == k + 1] = NODATA
    with rasterio.open(clips[2025], "w", **profile) as ds:
        ds.write(data, 1)
    return target


@pytest.fixture(scope="module")
def built(clips, members, nodata_hex, tmp_path_factory):
    return landcover.build_landcover(clips, members, cache_dir=tmp_path_factory.mktemp("cellgrid"))


def test_schema_rows_and_years(built, members):
    for res, t in built.items():
        assert t.schema.equals(landcover.SCHEMA)
        assert t.num_rows == len(members[res]) * len(YEARS)
        assert set(t["year"].to_pylist()) == set(YEARS)
        keys = list(zip(t["h3"].to_pylist(), t["year"].to_pylist()))
        assert keys == sorted(keys)
        assert all(p3 == h3util.parents(np.array([c], np.uint64), 3)[0] for c, p3 in list(zip(t["h3"].to_pylist(), t["p3"].to_pylist()))[:50])


def test_fractions_sum_to_one_and_in_range(built):
    for t in built.values():
        fr = np.column_stack([t[name].to_numpy(zero_copy_only=False) for name in GROUPS]).astype(float)
        ok = ~np.isnan(fr).any(axis=1)
        assert np.allclose(fr[ok].sum(axis=1), 1, atol=1e-6)
        assert (fr[ok] >= 0).all() and (fr[ok] <= 1).all()
        vf = t["valid_frac"].to_numpy(zero_copy_only=False)
        assert ((vf >= 0) & (vf <= 1)).all()


def test_matches_naive_count(built, clips, members, tmp_path_factory):
    """One res-7 hex in 1985: shares equal a direct count over all its res-8 children's pixels."""
    with rasterio.open(clips[1985]) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=tmp_path_factory.mktemp("g2"))
        data = ds.read(1)
    cells = grid.cells[np.asarray(grid.index()).astype(np.int64) - 1]
    parent7 = h3util.parents(cells.ravel(), 7).reshape(cells.shape)
    t = built[7].filter(pc.equal(built[7]["year"], 1985))
    target = t["h3"][0].as_py()
    vals = data[parent7 == np.uint64(target)]
    valid = vals[vals != NODATA]
    row = t.filter(pc.equal(t["h3"], pa.scalar(target, pa.uint64())))
    assert row["valid_frac"][0].as_py() == pytest.approx(len(valid) / len(vals), rel=1e-6)
    for name, cls in GROUPS.items():
        assert row[name][0].as_py() == pytest.approx(np.isin(valid, cls).mean(), rel=1e-5)


def test_all_nodata_hex_is_null(built, nodata_hex):
    t = built[8]
    row = t.filter(pc.and_(pc.equal(t["h3"], pa.scalar(nodata_hex, pa.uint64())), pc.equal(t["year"], 2025)))
    assert row.num_rows == 1
    assert all(row[name][0].as_py() is None for name in GROUPS)
    assert row["valid_frac"][0].as_py() == 0
    # Same hex in 1985 has data.
    before = t.filter(pc.and_(pc.equal(t["h3"], pa.scalar(nodata_hex, pa.uint64())), pc.equal(t["year"], 1985)))
    assert before["frac_forest"][0].as_py() is not None


def test_land_frac_and_fill(built, members, nodata_hex, tmp_path):
    lf = landcover.land_frac(built, 2025)
    for res, t in lf.items():
        y = built[res].filter(pc.equal(built[res]["year"], 2025))
        assert t["h3"].to_pylist() == y["h3"].to_pylist()
        for v, w in zip(t["value"].to_pylist(), y["frac_water"].to_pylist()):
            assert (v is None) == (w is None)
            if w is not None:
                assert v == pytest.approx(1 - w, abs=1e-6)
    # fill writes land_frac into hex_base partitions and keeps NULL for the blank hex.
    out, work = tmp_path / "out", tmp_path / "work"
    for res, t in hex_base.build_hex_base(GEOMETRY).items():
        io.write_partitioned(t, "hex_base", res, out if res in config.RES_SHIPPED else work, ["census"])
    records = hex_base.fill("land_frac", lf, ["nlcd"], out_dir=out, work_dir=work)
    assert records and all(r["res"] in config.RES_SHIPPED for r in records)
    assert all(r["sources"] == ["census", "nlcd"] for r in records)
    r8 = pq.read_table(work / "hex" / "hex_base" / "r8").sort_by("h3")
    by_id = dict(zip(r8["h3"].to_pylist(), r8["land_frac"].to_pylist()))
    assert by_id[nodata_hex] is None
    assert sum(v is not None for v in by_id.values()) == len(by_id) - 1
    assert all(0 <= v <= 1 for v in by_id.values() if v is not None)


def test_batched_passes_match_one_pass(built, clips, members, monkeypatch, tmp_path):
    monkeypatch.setattr(landcover, "YEARS_PER_PASS", 2)  # 3 years: passes of 2 and 1
    again = landcover.build_landcover(clips, members, cache_dir=tmp_path)
    for res in built:
        assert again[res].equals(built[res])


def test_missing_hex_fails(clips, members, tmp_path):
    extra = dict(members)
    far = h3util.parents(np.array([0x8828308281FFFFF], np.uint64), 8)  # a res-8 cell far from the clip
    extra[8] = np.sort(np.concatenate([members[8], far]))
    with pytest.raises(ValueError, match="no pixels in the clip"):
        landcover.build_landcover(clips, extra, cache_dir=tmp_path)


def test_fill_keeps_sources_already_in_the_manifest(built, tmp_path):
    out, work = tmp_path / "out", tmp_path / "work"
    records = []
    for res, t in hex_base.build_hex_base(GEOMETRY).items():
        written = io.write_partitioned(t, "hex_base", res, out if res in config.RES_SHIPPED else work, ["census", "dem"])
        records += written if res in config.RES_SHIPPED else []
    io.update_manifest(out, records)
    records = hex_base.fill("land_frac", landcover.land_frac(built, 2025), ["nlcd"], out_dir=out, work_dir=work)
    assert all(r["sources"] == ["census", "dem", "nlcd"] for r in records)
