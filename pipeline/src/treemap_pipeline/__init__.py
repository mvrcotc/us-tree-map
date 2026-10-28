"""US Tree Map data pipeline. Entry point: `uv run treemap-pipeline [steps...]`."""

import argparse
import json
import time
from datetime import datetime, timezone

from treemap_pipeline import config, io
from treemap_pipeline.build import geo, hex_base
from treemap_pipeline.sources import census

STEPS = ("geo", "hex_base")


def run_geo() -> list[dict]:
    zips = census.download_all()
    return geo.build_geo(zips["state"], zips["county"], config.PILOT_FIPS, config.OUT)


def run_hex_base() -> list[dict]:
    zips = census.download_all()
    geometry = geo.read_state_geometry(geo.connect(), zips["state"], config.PILOT_FIPS)
    tables = hex_base.build_hex_base(geometry)
    records = []
    for res, table in tables.items():
        if res in config.RES_SHIPPED:
            records += io.write_partitioned(table, "hex_base", res, config.OUT, ["census"])
        else:
            # Res 8 is the working grid: kept in data/work/, not published (data contract).
            io.write_partitioned(table, "hex_base", res, config.WORK, ["census"])
        print(f"  hex_base r{res}: {table.num_rows:,} hexes")
    return records


RUNNERS = {"geo": run_geo, "hex_base": run_hex_base}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build US Tree Map data for the pilot state.")
    parser.add_argument("steps", nargs="*", choices=STEPS, help="steps to run (default: all)")
    steps = parser.parse_args().steps or list(STEPS)

    timings = {}
    started = time.perf_counter()
    for step in steps:
        t0 = time.perf_counter()
        print(f"{step} ...")
        records = RUNNERS[step]()
        io.update_manifest(config.OUT, records)
        timings[step] = round(time.perf_counter() - t0, 2)
        print(f"  done in {timings[step]} s")

    config.QA.mkdir(parents=True, exist_ok=True)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pilot": config.PILOT_STUSPS,
        "steps_s": timings,
        "total_s": round(time.perf_counter() - started, 2),
        "note": "perf-budget P1: downloads included on a first run",
    }
    (config.QA / "pipeline-timing.json").write_text(json.dumps(report, indent=1) + "\n")
