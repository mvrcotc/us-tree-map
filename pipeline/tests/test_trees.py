"""hex_trees on a synthetic plot-id clip and tree table (data contract: Tables → hex_trees)."""

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from treemap_pipeline import config, h3util, raster
from treemap_pipeline.build import hex_base, trees

# Synthetic data, not real TreeMap plots: 30 m Albers around Madison.
PX, SIZE = 30.0, 1600
LNG, LAT = -89.40, 43.07
GEOMETRY = {"type": "Polygon", "coordinates": [[[LNG - 0.02, LAT - 0.015], [LNG + 0.02, LAT - 0.015], [LNG + 0.02, LAT + 0.015], [LNG - 0.02, LAT + 0.015], [LNG - 0.02, LAT - 0.015]]]}
NODATA = 0
PLOTS = [70001, 70002, 70003, 70004, 100000]  # ids above 16 bits on purpose
# TM_ID, STATUSCD, TPA_UNADJ, SPCD, DIA
TREES = [
    (70001, 1, 6.0, 316, 10.0),  # red maple
    (70001, 1, 6.0, 316, 12.0),
    (70001, 1, 6.0, 833, 20.0),  # northern red oak
    (70001, 2, 6.0, 833, 30.0),  # dead: left out
    (70002, 1, 75.0, 316, 2.0),  # microplot sapling
    (70002, 1, 6.0, 371, None),  # live, no diameter: tpa only
    (70003, 1, 6.0, 833, 15.0),
    (70004, 2, 6.0, 833, 25.0),  # only dead trees: known plot, zero live trees
    (100000, 1, 6.0, 129, 18.0),  # eastern white pine
]


def tree_table() -> pa.Table:
    cols = list(zip(*TREES))
    return pa.table(
        {
            "TM_ID": pa.array(cols[0], pa.int64()),
            "STATUSCD": pa.array(cols[1], pa.int8()),
            "TPA_UNADJ": pa.array(cols[2], pa.float64()),
            "SPCD": pa.array(cols[3], pa.int16()),
            "DIA": pa.array(cols[4], pa.float64()),
        }
    )


def plot_values() -> dict[int, dict[int, tuple[float, float]]]:
    """{tm_id: {spcd: (ba ft²/ac, tpa)}}: the contract's formula, live trees only."""
    out: dict[int, dict[int, list[float]]] = {}
    for tm, status, tpa, sp, dia in TREES:
        if status != 1:
            continue
        v = out.setdefault(tm, {}).setdefault(sp, [0.0, 0.0])
        v[0] += 0.005454 * dia * dia * tpa if dia is not None else 0.0
        v[1] += tpa
    return {tm: {sp: tuple(v) for sp, v in d.items()} for tm, d in out.items()}


@pytest.fixture(scope="module")
def members():
    return {res: t["h3"].to_numpy() for res, t in hex_base.build_hex_base(GEOMETRY).items()}


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform(LNG, LAT)
    transform = from_origin(round(x) - SIZE * PX / 2, round(y) + SIZE * PX / 2, PX, PX)
    data = np.random.default_rng(13).choice(np.array([NODATA, *PLOTS], np.int32), size=(SIZE, SIZE), p=[0.3, 0.2, 0.15, 0.15, 0.1, 0.1])
    path = tmp_path_factory.mktemp("treemap") / "treemap.tif"
    with rasterio.open(path, "w", driver="GTiff", width=SIZE, height=SIZE, count=1, dtype="int32", crs="EPSG:5070", transform=transform, nodata=NODATA, tiled=True, blockxsize=256, blockysize=256) as ds:
        ds.write(data, 1)
    return path


@pytest.fixture(scope="module")
def built(clip, members, tmp_path_factory):
    return trees.build_trees(clip, tree_table(), members, cache_dir=tmp_path_factory.mktemp("cellgrid"))


def test_plot_species_formula():
    ps = trees.plot_species(tree_table())
    got = {(r["tm_id"], r["spcd"]): (r["ba"], r["tpa"]) for r in ps.to_pylist()}
    want = plot_values()
    assert set(got) == {(tm, sp) for tm, d in want.items() for sp in d}
    for (tm, sp), (ba, tpa) in got.items():
        assert tpa == pytest.approx(want[tm][sp][1])
        if (tm, sp) == (70002, 371):
            assert ba is None  # basal area unknown, not 0
        else:
            assert ba == pytest.approx(want[tm][sp][0])


def test_schema_and_shares(built):
    for t in built.values():
        assert t.schema.equals(trees.SCHEMA)
        keys = list(zip(t["h3"].to_pylist(), t["spcd"].to_pylist()))
        assert keys == sorted(keys)
        # Each hex's shares sum to 1, within 3-significant-figure rounding.
        sums = t.group_by("h3").aggregate([("ba_share", "sum")])["ba_share_sum"].to_numpy()
        assert (abs(sums - 1) < 6e-3).all()
        fpf = t["forest_px_frac"].to_numpy()
        assert ((fpf > 0) & (fpf <= 1)).all()


def assert_matches_direct_count(built, clip, cache_dir, plots):
    """Every hex at every resolution equals a direct count from the raster, up to the rounding.

    `plots` maps a plot id to its {spcd: (ba, tpa)}; a raster plot absent from it has unknown
    species, so it counts as forest but not in the species means.
    """
    with rasterio.open(clip) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=cache_dir)
        data = ds.read(1)
    cells = grid.cells[np.asarray(grid.index()).astype(np.int64) - 1].ravel()
    data = data.ravel()
    for res, t in built.items():
        ids, inverse = np.unique(h3util.parents(cells, res) if res < 8 else cells, return_inverse=True)
        total = np.bincount(inverse, minlength=len(ids))
        pixels = {tm: np.bincount(inverse[data == tm], minlength=len(ids)) for tm in PLOTS}
        forest = sum(pixels.values())
        known = sum(pixels[tm] for tm in plots)
        rows = {}
        for r in t.to_pylist():
            rows.setdefault(r["h3"], {})[r["spcd"]] = r
        for h, by_species in rows.items():
            i = int(np.searchsorted(ids, np.uint64(h)))
            want_ba, want_tpa = {}, {}
            for tm, species in plots.items():
                for sp, (b, tp) in species.items():
                    if pixels[tm][i]:
                        want_ba[sp] = want_ba.get(sp, 0) + pixels[tm][i] * b
                        want_tpa[sp] = want_tpa.get(sp, 0) + pixels[tm][i] * tp
            assert set(by_species) == set(want_tpa), (res, h)
            total_ba = sum(want_ba.values())
            rounded = lambda v: trees.round_sig(pa.array([float(v)], pa.float64())).to_pylist()[0]  # noqa: E731
            for sp, r in by_species.items():
                assert r["tpa"] == pytest.approx(rounded(want_tpa[sp] / known[i]), rel=1e-6)
                assert r["forest_px_frac"] == pytest.approx(rounded(forest[i] / total[i]), rel=1e-6)
                if want_ba[sp] == 0:  # only diameter-less trees: basal area unknown, so NULL, never 0
                    assert r["ba_ft2ac"] is None and r["ba_share"] is None
                else:
                    assert r["ba_ft2ac"] == pytest.approx(rounded(want_ba[sp] / known[i]), rel=1e-6)
                    assert r["ba_share"] == pytest.approx(rounded(want_ba[sp] / total_ba), rel=1e-6)


def test_matches_direct_count_at_every_resolution(built, clip, tmp_path):
    """Includes a dead-only plot: in the denominators, adding no species of its own."""
    assert_matches_direct_count(built, clip, tmp_path, {tm: plot_values().get(tm, {}) for tm in PLOTS})


def test_many_plots_missing_from_tree_table_fails(clip, members, tmp_path):
    t = tree_table().filter(pc.not_equal(tree_table()["TM_ID"], 100000))
    with pytest.raises(ValueError, match="missing from the tree table"):
        trees.build_trees(clip, t, members, cache_dir=tmp_path)


def test_plot_without_tree_rows_is_forest_but_not_in_species_means(clip, members, tmp_path, monkeypatch):
    """Unknown species are never treated as treeless: the means use known plots only."""
    monkeypatch.setattr(trees, "MAX_UNKNOWN_SHARE", 1.0)
    full = tree_table()
    built = trees.build_trees(clip, full.filter(pc.not_equal(full["TM_ID"], 100000)), members, cache_dir=tmp_path)
    assert 129 not in built[5]["spcd"].to_pylist()  # white pine grows only on the missing plot
    known = {tm: plot_values().get(tm, {}) for tm in PLOTS if tm != 100000}
    assert_matches_direct_count(built, clip, tmp_path, known)


def test_round_sig_keeps_rare_values_and_nulls():
    got = trees.round_sig(pa.array([123.456, 0.0012345, 0.0, None], pa.float32())).to_pylist()
    assert got[0] == pytest.approx(123.0)
    assert got[1] == pytest.approx(0.00123)
    assert got[2] == 0.0 and got[3] is None


def test_real_output_if_built():
    path = config.OUT / "hex" / "hex_trees" / "r7"
    if not path.exists():
        pytest.skip("hex_trees not built")
    t = pq.read_table(path)
    assert t.num_rows > 0
    fpf = t["forest_px_frac"].to_numpy()
    assert ((fpf > 0) & (fpf <= 1)).all()
    sums = t.group_by("h3").aggregate([("ba_share", "sum")])["ba_share_sum"].to_numpy()
    assert (abs(sums[sums > 0] - 1) < 6e-3).all()
    assert max(f.stat().st_size for f in path.glob("*.parquet")) <= 1_000_000  # perf-budget L5
