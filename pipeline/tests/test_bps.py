"""BpS group mapping and hex_bps on a synthetic int16 clip (data contract: Tables → hex_bps)."""

import csv

import numpy as np
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from treemap_pipeline import config, raster
from treemap_pipeline.build import bps, hex_base

# Synthetic data, not real LANDFIRE values: 30 m Albers around Madison.
PX, SIZE = 30.0, 1600
LNG, LAT = -89.40, 43.07
GEOMETRY = {"type": "Polygon", "coordinates": [[[LNG - 0.02, LAT - 0.015], [LNG + 0.02, LAT - 0.015], [LNG + 0.02, LAT + 0.015], [LNG - 0.02, LAT + 0.015], [LNG - 0.02, LAT - 0.015]]]}
# VALUE, BPS_CODE, name, GROUPVEG. Values 20 and 21 share one code (two map zones).
ATTRS = [
    (-9999, -9999, "Fill-NoData", "Fill-NoData"),
    (-1111, -1111, "Fill-Not Mapped", "Fill-Not Mapped"),
    (1, 1, "Missing", "Missing"),
    (11, 11, "Open Water", "Open Water"),
    (20, 13110, "Laurentian-Acadian Northern Hardwoods Forest", "Hardwood"),
    (21, 13110, "Laurentian-Acadian Northern Hardwoods Forest", "Hardwood"),
    (30, 14200, "North-Central Interior Oak Savanna", "Hardwood"),
    (40, 13850, "Central Tallgrass Prairie", "Grassland"),
    (50, 15500, "Laurentian-Acadian Floodplain Systems", "Riparian"),
    (60, 16000, "Boreal Acidic Peatland Systems", "Peatland non-forest"),
]
VALUES = [a[0] for a in ATTRS]


def attributes():
    return [{"VALUE": str(v), "BPS_CODE": str(c), "BPS_NAME": n, "GROUPVEG": g} for v, c, n, g in ATTRS]


def test_propose_rules():
    assert bps.propose("North-Central Interior Oak Savanna", "Hardwood") == ("savanna", "name has Savanna", True)
    assert bps.propose("Great Lakes Pine Barrens", "Conifer")[0] == "savanna"
    assert bps.propose("Northern Rocky Mountain Ponderosa Pine Woodland and Savanna", "Conifer")[::2] == ("forest", True)
    assert bps.propose("Laurentian-Acadian Floodplain Systems", "Riparian")[0] == "forest"
    assert bps.propose("Eastern Great Plains Wet Meadow", "Riparian")[0] == "wetland"
    assert bps.propose("Central Tallgrass Prairie", "Grassland") == ("open", "GROUPVEG Grassland", False)
    assert bps.propose("Eastern Great Plains Wet Meadow-Prairie-Marsh", "Grassland")[::2] == ("wetland", True)
    assert bps.propose("Missing", "Missing")[0] == bps.INVALID
    assert bps.propose("Something", "NA")[::2] == ("other", True)


@pytest.fixture(scope="module")
def members():
    return {res: t["h3"].to_numpy() for res, t in hex_base.build_hex_base(GEOMETRY).items()}


@pytest.fixture(scope="module")
def clip(tmp_path_factory, members):
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform(LNG, LAT)
    transform = from_origin(round(x) - SIZE * PX / 2, round(y) + SIZE * PX / 2, PX, PX)
    data = np.random.default_rng(11).choice(np.array(VALUES, np.int16), size=(SIZE, SIZE))
    path = tmp_path_factory.mktemp("bps") / "bps.tif"
    profile = dict(driver="GTiff", width=SIZE, height=SIZE, count=1, dtype="int16", crs="EPSG:5070", transform=transform, nodata=-9999, tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(data, 1)
    with rasterio.open(path) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=tmp_path_factory.mktemp("g"))
    target = int(members[8][len(members[8]) // 4])
    data[np.asarray(grid.index()) == int(np.searchsorted(grid.cells, np.uint64(target))) + 1] = -1111
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(data, 1)
    return path, target


@pytest.fixture(scope="module")
def mapping(clip, tmp_path_factory):
    path = tmp_path_factory.mktemp("map") / "bps_groups.csv"
    bps.write_mapping(clip[0], attributes(), path)
    return path


def test_mapping_one_row_per_code(mapping):
    rows = bps.read_mapping(mapping)
    by_code = {int(r["bps_code"]): r for r in rows}
    assert sorted(by_code) == [1, 11, 13110, 13850, 14200, 15500, 16000]  # fill codes left out
    assert by_code[13110]["values"] == "20 21"
    assert by_code[14200]["group"] == "savanna" and by_code[14200]["needs_review"] == "yes"
    assert by_code[1]["group"] == bps.INVALID
    assert all(r["reviewed"] == "" for r in rows)


def test_reviewed_rows_keep_their_group(mapping, clip):
    rows = bps.read_mapping(mapping)
    for r in rows:
        if r["bps_code"] == "15500":
            r["group"], r["rule"], r["reviewed"] = "wetland", "Marco: floodplain counted as wetland", "Marco 2026-10-29"
    with open(mapping, "w", newline="") as f:
        w = csv.DictWriter(f, bps.FIELDS)
        w.writeheader()
        w.writerows(rows)
    bps.write_mapping(clip[0], attributes(), mapping)
    again = {r["bps_code"]: r for r in bps.read_mapping(mapping)}
    assert again["15500"]["group"] == "wetland" and again["15500"]["reviewed"] == "Marco 2026-10-29"
    assert again["14200"]["group"] == "savanna"  # unreviewed rows are re-proposed


@pytest.fixture(scope="module")
def built(clip, mapping, members, tmp_path_factory):
    return bps.build_bps(clip[0], bps.read_mapping(mapping), members, cache_dir=tmp_path_factory.mktemp("cellgrid"))


def test_schema_and_shares(built, members):
    for res, t in built.items():
        assert t.schema.equals(bps.SCHEMA)
        assert t["h3"].to_pylist() == sorted(int(c) for c in members[res])
        fr = np.column_stack([t[f"bps_{g}_frac"].to_numpy(zero_copy_only=False) for g in bps.GROUPS]).astype(float)
        ok = ~np.isnan(fr).any(axis=1)
        assert np.allclose(fr[ok].sum(axis=1), 1, atol=1e-6)


def test_matches_naive_count(built, clip, mapping, tmp_path_factory):
    with rasterio.open(clip[0]) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=tmp_path_factory.mktemp("g2"))
        data = ds.read(1)
    rows = bps.read_mapping(mapping)
    group_of = {int(v): r["group"] for r in rows for v in r["values"].split()}
    code_of = {int(v): int(r["bps_code"]) for r in rows for v in r["values"].split()}
    index = np.asarray(grid.index())
    t = built[8]
    for i in range(0, t.num_rows, max(1, t.num_rows // 15)):
        h = t["h3"][i].as_py()
        if h == clip[1]:
            continue
        vals = data[index == int(np.searchsorted(grid.cells, np.uint64(h))) + 1]
        valid = np.array([v for v in vals if v in group_of and group_of[v] != bps.INVALID])
        for g in bps.GROUPS:
            share = np.mean([group_of[v] == g for v in valid])
            assert t[f"bps_{g}_frac"][i].as_py() == pytest.approx(share, abs=1e-6)
        codes, n = np.unique([code_of[v] for v in valid], return_counts=True)
        assert t["bps_top_code"][i].as_py() == int(codes[np.argmax(n)])  # 20 and 21 counted as one code
        assert t["valid_frac"][i].as_py() == pytest.approx(len(valid) / len(vals))


def test_all_fill_hex_is_null(built, clip):
    row = built[8].filter(pc.equal(built[8]["h3"], clip[1]))
    assert all(row[f"bps_{g}_frac"][0].as_py() is None for g in bps.GROUPS)
    assert row["bps_top_code"][0].as_py() is None and row["bps_top_name"][0].as_py() is None
    assert row["valid_frac"][0].as_py() == 0


def test_unmapped_value_fails(clip, mapping, members, tmp_path):
    rows = [r for r in bps.read_mapping(mapping) if r["bps_code"] != "13850"]
    with pytest.raises(ValueError, match="not in"):
        bps.build_bps(clip[0], rows, members, cache_dir=tmp_path)


def test_real_output_if_built():
    path = config.OUT / "hex" / "hex_bps" / "r7"
    if not path.exists():
        pytest.skip("hex_bps not built")
    t = pq.read_table(path)
    fr = np.column_stack([t[f"bps_{g}_frac"].to_numpy(zero_copy_only=False) for g in bps.GROUPS]).astype(float)
    ok = ~np.isnan(fr).any(axis=1)
    assert np.allclose(fr[ok].sum(axis=1), 1, atol=1e-5)
