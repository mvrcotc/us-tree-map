"""US Tree Map data pipeline. Entry point: `uv run treemap-pipeline [steps...]`."""

import argparse
import json
import time
from datetime import datetime, timezone

from treemap_pipeline import config, io
from treemap_pipeline.build import geo, hex_base, landcover
from treemap_pipeline.sources import census, nlcd

# Fetch steps download or clip sources; the others only build, so P1 (perf-budget,
# downloads excluded) is the sum of the build steps.
STEPS = ("geo", "hex_base", "fetch_nlcd", "landcover")
FETCH_STEPS = {"fetch_nlcd"}


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


def pilot_geometry() -> dict:
    return geo.read_state_geometry(geo.connect(), census.download_all()["state"], config.PILOT_FIPS)


def run_fetch_nlcd() -> list[dict]:
    clips = nlcd.fetch_all(pilot_geometry(), hex_base.members((5,))[5])
    print(f"  nlcd: {len(clips)} clipped years in {nlcd.raw_dir() / 'clip'}")
    return []


def run_landcover() -> list[dict]:
    missing = [y for y in nlcd.YEARS if not nlcd.clip_path(y).exists()]
    if missing:
        raise SystemExit(f"Annual NLCD clips missing for {missing[0]}–{missing[-1]}: run `uv run treemap-pipeline fetch_nlcd` first")
    members = hex_base.members()
    tables = landcover.build_landcover({y: nlcd.clip_path(y) for y in nlcd.YEARS}, members)
    records = []
    for res, table in tables.items():
        out = config.OUT if res in config.RES_SHIPPED else config.WORK
        written = io.write_partitioned(table, "hex_landcover", res, out, ["nlcd"])
        if res in config.RES_SHIPPED:
            records += written
        print(f"  hex_landcover r{res}: {table.num_rows:,} hex-years")
    records += hex_base.fill("land_frac", landcover.land_frac(tables, max(nlcd.YEARS)), ["nlcd"])
    return records


RUNNERS = {"geo": run_geo, "hex_base": run_hex_base, "fetch_nlcd": run_fetch_nlcd, "landcover": run_landcover}


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
        "steps": steps,
        "full_run": steps == list(STEPS),
        "steps_s": timings,
        "total_s": round(time.perf_counter() - started, 2),
        "build_s": round(sum(t for s, t in timings.items() if s not in FETCH_STEPS), 2),
        "note": "perf-budget P1 = build_s when full_run is true (fetch steps excluded); geo and hex_base include the small Census download on a first run",
    }
    (config.QA / "pipeline-timing.json").write_text(json.dumps(report, indent=1) + "\n")
