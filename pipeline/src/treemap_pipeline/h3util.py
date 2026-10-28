"""Vectorized H3 helpers through DuckDB's `h3` community extension."""

import duckdb
import numpy as np
import pyarrow as pa

_con: duckdb.DuckDBPyConnection | None = None


def con() -> duckdb.DuckDBPyConnection:
    """Shared connection with `h3` loaded. Installs it on first use (needs network once per machine)."""
    global _con
    if _con is None:
        c = duckdb.connect()
        try:
            c.execute("LOAD h3")
        except duckdb.Error:
            c.execute("INSTALL h3 FROM community")
            c.execute("LOAD h3")
        _con = c
    return _con


def parents(cells: np.ndarray, res: int) -> np.ndarray:
    """Parent of each cell at `res` (same order and length as `cells`)."""
    t = pa.table({"c": pa.array(cells, pa.uint64())})  # noqa: F841 (read by DuckDB)
    out = con().sql(f"SELECT h3_cell_to_parent(c, {int(res)}) AS p FROM t").to_arrow_table()["p"]
    if out.null_count:
        raise ValueError(f"{out.null_count} cells have no parent at res {res} (res above the cell's own?)")
    return out.to_numpy().astype(np.uint64)
