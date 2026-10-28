"""`hex_base`: the hex grid every other table joins to (data contract: Tables).

Membership: the resolution-8 cells whose centers fall inside the state polygon.
Coarser resolutions are the parents of those cells, so every hex at res r is
exactly the set of parents of the hexes at res r + 1 (roll-up consistency).

Filled now: `h3`, `res`, `p3`, and `area_km2` (from H3 itself). The other columns
stay NULL until their sources land.
"""

import h3.api.basic_int as h3
import numpy as np
import pyarrow as pa

from treemap_pipeline import config

SCHEMA = pa.schema(
    [
        ("h3", pa.uint64()),
        ("res", pa.int8()),
        ("p3", pa.uint64()),
        ("area_km2", pa.float32()),
        ("state_fips", pa.string()),
        ("county_fips", pa.string()),
        ("land_frac", pa.float32()),
        ("in_atlas", pa.bool_()),
        ("elev_m", pa.float32()),
    ]
)


def cells_in_polygon(geometry: dict, res: int) -> np.ndarray:
    """H3 cells (as uint64) whose centers lie inside a GeoJSON Polygon or MultiPolygon."""
    shape = h3.geo_to_h3shape(geometry)
    cells = h3.h3shape_to_cells(shape, res)
    return np.array(sorted(cells), dtype=np.uint64)


def parents(cells: np.ndarray, res: int) -> np.ndarray:
    return np.unique(np.fromiter((h3.cell_to_parent(int(c), res) for c in cells), dtype=np.uint64, count=len(cells)))


def table_for(cells: np.ndarray, res: int) -> pa.Table:
    cells = np.sort(cells)
    n = len(cells)
    p3 = np.fromiter((h3.cell_to_parent(int(c), config.RES_PARTITION) for c in cells), dtype=np.uint64, count=n)
    area = np.fromiter((h3.cell_area(int(c), unit="km^2") for c in cells), dtype=np.float32, count=n)
    columns = {
        "h3": pa.array(cells, pa.uint64()),
        "res": pa.array(np.full(n, res, dtype=np.int8)),
        "p3": pa.array(p3, pa.uint64()),
        "area_km2": pa.array(area, pa.float32()),
    }
    for field in SCHEMA:
        if field.name not in columns:
            columns[field.name] = pa.nulls(n, field.type)
    return pa.table(columns, schema=SCHEMA)


def build_hex_base(geometry: dict, finest: int = config.RES_WORK, coarsest: int = min(config.RES_SHIPPED)) -> dict[int, pa.Table]:
    """Return one hex_base table per resolution, finest to coarsest."""
    cells = cells_in_polygon(geometry, finest)
    if len(cells) == 0:
        raise ValueError("no cell centers inside the polygon")
    tables = {}
    for res in range(finest, coarsest - 1, -1):
        if res < finest:
            cells = parents(cells, res)
        tables[res] = table_for(cells, res)
    return tables
