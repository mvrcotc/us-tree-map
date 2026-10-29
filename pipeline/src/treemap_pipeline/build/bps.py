"""`hex_bps` (static, one row per hex, LANDFIRE LF 2020 BpS) and its group mapping.

Data contract: Tables → `hex_bps`. Each BpS code maps to one of five groups in
`pipeline/mappings/bps_groups.csv`, which Marco reviews. The mapping starts from LANDFIRE's
GROUPVEG attribute, with name rules where GROUPVEG hides a group the contract needs (D8:
savanna is its own class, but North-Central Interior Oak Savanna is GROUPVEG Hardwood).
Rows a rule can't settle are marked `needs_review`.

Fractions are shares of valid pixels (any mapped BpS); fill codes and `invalid` rows count
toward `valid_frac`'s denominator only. A hex with no valid pixel gets NULL, never 0.
"""

import csv
from pathlib import Path

import numpy as np
import pyarrow as pa
import rasterio

from treemap_pipeline import config, h3util, raster
from treemap_pipeline.sources import bps as source

MAPPING = config.REPO / "pipeline" / "mappings" / "bps_groups.csv"
GROUPS = ("forest", "savanna", "open", "wetland", "other")
INVALID = "invalid"  # not a setting (LANDFIRE "Missing"): counts as no data
FIELDS = ["bps_code", "bps_name", "groupveg", "group", "rule", "needs_review", "pixels_in_window", "values", "reviewed"]

SCHEMA = pa.schema(
    [("h3", pa.uint64()), ("res", pa.int8()), ("p3", pa.uint64())]
    + [(f"bps_{g}_frac", pa.float32()) for g in GROUPS]
    + [("bps_top_code", pa.int32()), ("bps_top_name", pa.string()), ("valid_frac", pa.float32())]
)

GROUPVEG = {
    "Conifer": "forest",
    "Hardwood": "forest",
    "Hardwood-Conifer": "forest",
    "Conifer-Hardwood": "forest",
    "Peatland Forest": "forest",
    "Savanna": "savanna",
    "Grassland": "open",
    "Shrubland": "open",
    "Peatland non-forest": "wetland",
    "Sparse": "other",
    "Open Water": "other",
    "Perennial Ice/Snow": "other",
    "Barren-Rock/Sand/Clay": "other",
}

WET_WORDS = ("Marsh", "Wet Meadow", "Fen", "Bog")


def propose(name: str, groupveg: str) -> tuple[str, str, bool]:
    """(group, rule, needs_review) for one BpS from its name and GROUPVEG."""
    if groupveg == "Missing":
        return INVALID, "GROUPVEG Missing: no setting mapped", True
    if "Woodland and Savanna" in name or "Savanna and Woodland" in name:
        return GROUPVEG.get(groupveg, "forest"), f"name has woodland and savanna; GROUPVEG {groupveg}", True
    if "Savanna" in name:
        return "savanna", "name has Savanna", groupveg != "Savanna"
    if "Barrens" in name:
        return "savanna", f"name has Barrens (open pine or oak barrens); GROUPVEG {groupveg}", True
    if groupveg == "Riparian":
        if any(w in name for w in ("Forest", "Floodplain", "Swamp")):
            return "forest", "GROUPVEG Riparian; name has Forest, Floodplain or Swamp", True
        return "wetland", "GROUPVEG Riparian; no forest word in the name", True
    if groupveg in ("Grassland", "Shrubland") and any(w in name for w in WET_WORDS):
        return "wetland", f"GROUPVEG {groupveg}; name has a wetland word", True
    if groupveg in GROUPVEG:
        return GROUPVEG[groupveg], f"GROUPVEG {groupveg}", False
    return "other", f"GROUPVEG {groupveg}: no rule", True


def present_values(clip: Path) -> dict[int, int]:
    """{raster VALUE: pixels} over the clip window, fill codes excluded."""
    counts: dict[int, int] = {}
    with rasterio.open(clip) as ds:
        for r0 in range(0, ds.height, raster.STRIP_ROWS):
            block = ds.read(1, window=rasterio.windows.Window(0, r0, ds.width, min(raster.STRIP_ROWS, ds.height - r0)))
            vals, n = np.unique(block[block > source.FILL_MAX], return_counts=True)
            for v, k in zip(vals.tolist(), n.tolist()):
                counts[v] = counts.get(v, 0) + k
    return counts


def write_mapping(clip: Path, attributes: list[dict], path: Path = MAPPING) -> list[dict]:
    """Write one row per BpS code present in the clip window, keeping any `reviewed` marks."""
    present = present_values(clip)
    by_value = {int(r["VALUE"]): r for r in attributes}
    unknown = sorted(set(present) - set(by_value))
    if unknown:
        raise ValueError(f"raster values missing from the attribute table: {unknown[:10]}")
    codes: dict[int, dict] = {}
    for value, n in present.items():
        a = by_value[value]
        code = int(a["BPS_CODE"])
        row = codes.setdefault(code, {"bps_code": code, "bps_name": a["BPS_NAME"], "groupveg": a["GROUPVEG"], "pixels_in_window": 0, "values": []})
        if (row["bps_name"], row["groupveg"]) != (a["BPS_NAME"], a["GROUPVEG"]):
            raise ValueError(f"BPS_CODE {code}: VALUEs disagree on name or GROUPVEG")
        row["pixels_in_window"] += n
        row["values"].append(value)
    old = {int(r["bps_code"]): r for r in _read(path)} if path.exists() else {}
    rows = []
    for code in sorted(codes):
        r = codes[code]
        group, rule, review = propose(r["bps_name"], r["groupveg"])
        prev = old.get(code, {})
        if prev.get("reviewed"):
            group, rule = prev["group"], prev["rule"]  # a reviewed row keeps its group
        rows.append(r | {"group": group, "rule": rule, "needs_review": "yes" if review else "", "values": " ".join(map(str, sorted(r["values"]))), "reviewed": prev.get("reviewed", "")})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)
    tmp.rename(path)
    return rows


def _read(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def read_mapping(path: Path = MAPPING) -> list[dict]:
    rows = _read(path)
    bad = [r["bps_code"] for r in rows if r["group"] not in (*GROUPS, INVALID)]
    if bad:
        raise ValueError(f"{path.name}: unknown group for codes {bad[:10]}")
    return rows


def build_bps(clip: Path, mapping: list[dict], members: dict[int, np.ndarray], cache_dir: Path = config.WORK / "cellgrid") -> dict[int, pa.Table]:
    """{res: hex_bps table} from the clip and the reviewed mapping."""
    value_code, code_group, code_name = {}, {}, {}
    for r in mapping:
        code = int(r["bps_code"])
        code_group[code], code_name[code] = r["group"], r["bps_name"]
        for v in r["values"].split():
            value_code[int(v)] = code
    classes = sorted(v for v, c in value_code.items() if code_group[c] != INVALID)
    with rasterio.open(clip) as ds:
        grid = raster.cell_grid(ds, None, cache_dir=cache_dir)
        present = set(present_values(clip))
        if present - set(value_code):
            raise ValueError(f"BpS values in the clip but not in {MAPPING.name}: {sorted(present - set(value_code))[:10]}; rerun the bps_mapping step")
        (counts,), totals = raster.categorical_counts_many([ds], grid, classes)
    rolled = raster.rollup(counts, members, ["class"], ["n"])
    rolled_totals = raster.rollup(totals, members, [], ["n_total"])
    raster.require_coverage(rolled_totals, members)
    lookup = pa.table(
        {
            "class": pa.array(classes, pa.int32()),
            "code": pa.array([value_code[v] for v in classes], pa.int32()),
            "grp": pa.array([code_group[value_code[v]] for v in classes]),
            "name": pa.array([code_name[value_code[v]] for v in classes]),
        }
    )
    return {res: _shares(rolled[res], rolled_totals[res], lookup) for res in members}


def _shares(counts: pa.Table, totals: pa.Table, lookup: pa.Table) -> pa.Table:
    c, t, m = counts, totals, lookup  # noqa: F841 (read by DuckDB)
    fracs = ", ".join(f"CASE WHEN v.valid > 0 THEN coalesce(g.{g}, 0) / v.valid END AS bps_{g}_frac" for g in GROUPS)
    pivots = ", ".join(f"sum(n) FILTER (WHERE grp = '{g}') AS {g}" for g in GROUPS)
    sql = f"""
        WITH j AS (SELECT c.h3, c.n, m.code, m.grp, m.name FROM c JOIN m USING (class)),
        g AS (SELECT h3, {pivots} FROM j GROUP BY h3),
        v AS (SELECT h3, sum(n) AS valid FROM j GROUP BY h3),
        top AS (
            SELECT h3, first(code ORDER BY n DESC, code ASC) AS code, first(name ORDER BY n DESC, code ASC) AS name
            FROM (SELECT h3, code, name, sum(n) AS n FROM j GROUP BY ALL) GROUP BY h3
        )
        SELECT t.h3, t.res, t.p3, {fracs},
               top.code AS bps_top_code, top.name AS bps_top_name,
               (coalesce(v.valid, 0) / t.n_total)::FLOAT AS valid_frac
        FROM t LEFT JOIN v USING (h3) LEFT JOIN g USING (h3) LEFT JOIN top USING (h3)
        ORDER BY t.h3
    """
    return h3util.con().sql(sql).to_arrow_table().cast(SCHEMA)
