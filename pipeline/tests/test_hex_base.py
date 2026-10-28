"""hex_base: roll-up consistency, ids, types and nulls (data contract: Checks)."""

import json

import h3.api.basic_int as h3
import pyarrow.parquet as pq
import pytest

from treemap_pipeline import config, io
from treemap_pipeline.build.hex_base import SCHEMA, build_hex_base

# A small synthetic quadrilateral (about 30 x 20 km), not a real boundary.
POLYGON = {
    "type": "Polygon",
    "coordinates": [[[-89.6, 43.0], [-89.25, 43.0], [-89.2, 43.2], [-89.6, 43.18], [-89.6, 43.0]]],
}


@pytest.fixture(scope="module")
def tables():
    return build_hex_base(POLYGON, finest=8, coarsest=5)


def cell_set(table):
    return set(table["h3"].to_pylist())


def test_resolutions_present(tables):
    assert sorted(tables) == [5, 6, 7, 8]


def test_rollup_consistency(tables):
    """Every hex at res r is exactly the set of parents of the hexes at res r + 1."""
    for res in (5, 6, 7):
        children = cell_set(tables[res + 1])
        assert cell_set(tables[res]) == {h3.cell_to_parent(c, res) for c in children}


def test_children_partition_parents(tables):
    """Child counts per parent sum to the child total (no hex dropped or double counted)."""
    for res in (5, 6, 7):
        children = cell_set(tables[res + 1])
        per_parent = {}
        for c in children:
            p = h3.cell_to_parent(c, res)
            per_parent[p] = per_parent.get(p, 0) + 1
        assert sum(per_parent.values()) == len(children)
        assert set(per_parent) == cell_set(tables[res])


def test_ids_res_and_p3(tables):
    for res, t in tables.items():
        for c, r, p3 in zip(t["h3"].to_pylist(), t["res"].to_pylist(), t["p3"].to_pylist()):
            assert h3.is_valid_cell(c)
            assert h3.get_resolution(c) == r == res
            assert p3 == h3.cell_to_parent(c, config.RES_PARTITION)


def test_schema_sorted_and_nulls(tables):
    for t in tables.values():
        assert t.schema.equals(SCHEMA)
        ids = t["h3"].to_pylist()
        assert ids == sorted(ids)
        assert all(a > 0 for a in t["area_km2"].to_pylist())
        for name in ("state_fips", "county_fips", "land_frac", "in_atlas", "elev_m"):
            assert t[name].null_count == t.num_rows, f"{name} must be NULL until its source lands"


def test_partitioned_write_and_manifest(tables, tmp_path):
    t = tables[7]
    records = io.write_partitioned(t, "hex_base", 7, tmp_path, ["census"])
    assert sum(r["rows"] for r in records) == t.num_rows
    for r in records:
        assert len(r["path"].stem) == 15
        meta = pq.ParquetFile(r["path"]).metadata
        assert meta.row_group(0).column(0).compression == "ZSTD"
        part = pq.read_table(r["path"])
        assert set(part["p3"].to_pylist()) == {int(r["path"].stem, 16)}
    manifest = json.loads(io.update_manifest(tmp_path, records).read_text())
    assert sum(f["rows"] for f in manifest["files"].values()) == t.num_rows
    assert all(len(f["sha256"]) == 64 for f in manifest["files"].values())


BUILT = config.OUT / "hex" / "hex_base"


@pytest.mark.skipif(not BUILT.exists(), reason="pilot hex_base not built yet")
def test_built_pilot_rollup():
    """Roll-up consistency on the real pilot output (res 7 -> 6 -> 5)."""
    sets = {res: set(pq.read_table(BUILT / f"r{res}")["h3"].to_pylist()) for res in config.RES_SHIPPED}
    for res in (5, 6):
        assert sets[res] == {h3.cell_to_parent(c, res) for c in sets[res + 1]}
