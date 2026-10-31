"""Reconcile hex_trees' per-plot formula with TreeMap's own attribute table.

Our live basal area and trees per acre per plot (`build.trees.plot_species`) against the
raster attribute table's `BALIVE` and `TPA_LIVE`, which are published independently of the
tree table. Also counts plots with no tree-table rows and how many of those TreeMap gives live
basal area. Writes docs/qa/treemap_balive.json. Run: `uv run python qa/check_treemap_balive.py`.
"""

import json

import pyarrow as pa

from treemap_pipeline import config, h3util
from treemap_pipeline.build import trees
from treemap_pipeline.sources import treemap

ps = trees.plot_species(treemap.tree_table())  # noqa: F841 (read by DuckDB)
vat = treemap.attribute_table()  # noqa: F841 (read by DuckDB)
plots = pa.table({"tm": treemap.tree_table(("TM_ID",))["TM_ID"]})  # noqa: F841 (read by DuckDB)
con = h3util.con()
n, b50, b01, b99, t50, t01, t99 = con.sql(
    """
    SELECT count(*), median(ba / BALIVE), quantile_cont(ba / BALIVE, 0.01), quantile_cont(ba / BALIVE, 0.99),
           median(t / TPA_LIVE), quantile_cont(t / TPA_LIVE, 0.01), quantile_cont(t / TPA_LIVE, 0.99)
    FROM (SELECT tm_id AS plot, sum(ba) AS ba, sum(tpa) AS t FROM ps GROUP BY 1) JOIN vat ON plot = vat.TM_ID
    WHERE BALIVE > 0 AND TPA_LIVE > 0
    """
).fetchall()[0]
missing, stocked = con.sql(
    "SELECT count(*), count(*) FILTER (WHERE BALIVE > 0) FROM vat WHERE TM_ID NOT IN (SELECT DISTINCT tm FROM plots)"
).fetchall()[0]
report = {
    "plots_compared": n,
    "ours_over_BALIVE": {"p01": b01, "median": b50, "p99": b99},
    "ours_over_TPA_LIVE": {"p01": t01, "median": t50, "p99": t99},
    "attribute_table_plots_without_tree_rows": missing,
    "of_those_with_BALIVE_above_0": stocked,
}
config.QA.mkdir(parents=True, exist_ok=True)
(config.QA / "treemap_balive.json").write_text(json.dumps(report, indent=1) + "\n")
print(json.dumps(report, indent=1))
