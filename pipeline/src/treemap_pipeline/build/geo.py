"""Pilot-state outline and county lines as simplified GeoJSON (data contract: `geo/`).

Census files are NAD83 (EPSG:4269). At map scale NAD83 and WGS84 differ by about
a meter, so coordinates are written unchanged and labeled EPSG:4326.
"""

import json
from pathlib import Path

import duckdb

from treemap_pipeline import config

# Douglas-Peucker tolerance in degrees (~50 m), and coordinate precision (~1 m).
SIMPLIFY_DEG = 0.0005
DECIMALS = 5


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL spatial")
    con.execute("LOAD spatial")
    return con


def _vsizip(zip_path: Path, layer_name: str) -> str:
    return f"/vsizip/{zip_path}/{layer_name}.shp"


def _round(coords, nd: int = DECIMALS):
    if isinstance(coords[0], (int, float)):
        return [round(c, nd) for c in coords]
    return [_round(c, nd) for c in coords]


def _feature(geojson: str, props: dict) -> dict:
    geom = json.loads(geojson)
    geom["coordinates"] = _round(geom["coordinates"])
    return {"type": "Feature", "properties": props, "geometry": geom}


def read_state_geometry(con: duckdb.DuckDBPyConnection, state_zip: Path, fips: str) -> dict:
    """Full-resolution state polygon as a GeoJSON geometry dict (for hex membership)."""
    layer = state_zip.stem
    row = con.execute(
        f"SELECT ST_AsGeoJSON(geom) FROM ST_Read(?) WHERE STATEFP = ?",
        [_vsizip(state_zip, layer), fips],
    ).fetchone()
    if row is None:
        raise ValueError(f"state {fips} not found in {state_zip}")
    return json.loads(row[0])


def build_geo(state_zip: Path, county_zip: Path, fips: str, out_dir: Path) -> list[dict]:
    """Write geo/state.json and geo/counties.json; return manifest records."""
    con = connect()
    geo_dir = out_dir / "geo"
    geo_dir.mkdir(parents=True, exist_ok=True)

    state_rows = con.execute(
        "SELECT STATEFP, STUSPS, NAME, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, ?)) "
        "FROM ST_Read(?) WHERE STATEFP = ?",
        [SIMPLIFY_DEG, _vsizip(state_zip, state_zip.stem), fips],
    ).fetchall()
    county_rows = con.execute(
        "SELECT GEOID, NAME, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, ?)) "
        "FROM ST_Read(?) WHERE STATEFP = ? ORDER BY GEOID",
        [SIMPLIFY_DEG, _vsizip(county_zip, county_zip.stem), fips],
    ).fetchall()

    outputs = {
        "state": [_feature(g, {"state_fips": f, "stusps": s, "name": n}) for f, s, n, g in state_rows],
        "counties": [_feature(g, {"county_fips": geoid, "name": n}) for geoid, n, g in county_rows],
    }
    records = []
    for name, features in outputs.items():
        path = geo_dir / f"{name}.json"
        fc = {"type": "FeatureCollection", "crs_note": "EPSG:4326 (from NAD83)", "features": features}
        path.write_text(json.dumps(fc, separators=(",", ":")))
        records.append({"path": path, "table": f"geo/{name}", "res": None, "rows": len(features), "sources": ["census"]})
    return records
