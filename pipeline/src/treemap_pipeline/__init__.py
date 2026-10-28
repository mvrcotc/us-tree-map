"""US Tree Map data pipeline. Entry point: `uv run treemap-pipeline [steps...]`."""

import argparse
import json
import time
from datetime import datetime, timezone

from treemap_pipeline import config, io
from treemap_pipeline.build import canopy, geo, hex_base, landcover
from treemap_pipeline.sources import census, nlcd, tcc

# Fetch steps download or clip sources; the others only build, so P1 (perf-budget,
# downloads excluded) is the sum of the build steps.
STEPS = ("geo", "hex_base", "fetch_nlcd", "landcover", "fetch_tcc", "canopy")
FETCH_STEPS = {"fetch_nlcd", "fetch_tcc"}
# Years clipped at once by a fetch step (range reads; a few at a time is polite to the host).
FETCH_WORKERS = 3


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


def fetch(source) -> list[dict]:
    clips = source.fetch_all(pilot_geometry(), hex_base.members((5,))[5], workers=FETCH_WORKERS)
    print(f"  {source.source}: {len(clips)} clipped years in {source.raw_dir() / 'clip'}")
    return []


def clips_or_exit(source) -> dict:
    # A clip counts only with its sidecar, which fetch writes last (sources.zipclip).
    missing = [y for y in source.years if not (source.clip_path(y).exists() and source.clip_path(y).with_suffix('.window.json').exists())]
    if missing:
        raise SystemExit(f"{source.source} clips missing for {missing[0]}–{missing[-1]}: run `uv run treemap-pipeline fetch_{source.source}` first")
    return {y: source.clip_path(y) for y in source.years}


def write_table(tables: dict, name: str, sources: list[str]) -> list[dict]:
    """Write res 5–7 to data/out (manifest records returned) and res 8 to data/work."""
    records = []
    for res, table in tables.items():
        out = config.OUT if res in config.RES_SHIPPED else config.WORK
        written = io.write_partitioned(table, name, res, out, sources)
        if res in config.RES_SHIPPED:
            records += written
        print(f"  {name} r{res}: {table.num_rows:,} hex-years")
    return records


def run_landcover() -> list[dict]:
    tables = landcover.build_landcover(clips_or_exit(nlcd.SOURCE), hex_base.members())
    records = write_table(tables, "hex_landcover", ["nlcd"])
    records += hex_base.fill("land_frac", landcover.land_frac(tables, max(nlcd.YEARS)), ["nlcd"])
    return records


def run_canopy() -> list[dict]:
    tables = canopy.build_canopy(clips_or_exit(tcc.SOURCE), hex_base.members())
    return write_table(tables, "hex_canopy", ["tcc"])


RUNNERS = {
    "geo": run_geo,
    "hex_base": run_hex_base,
    "fetch_nlcd": lambda: fetch(nlcd.SOURCE),
    "landcover": run_landcover,
    "fetch_tcc": lambda: fetch(tcc.SOURCE),
    "canopy": run_canopy,
}


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
