"""Paths and constants shared by every pipeline step.

Paths are built with pathlib only: the repo lives under a path with spaces.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "data"
RAW = DATA / "raw"
WORK = DATA / "work"
QA = REPO / "docs" / "qa"

# Output version (data contract: bump for any breaking change, never overwrite a published one).
VERSION = 1
OUT = DATA / "out" / f"v{VERSION}"

# Pilot state (CLAUDE.md, docs/pilot-state.md).
PILOT_NAME = "Wisconsin"
PILOT_STUSPS = "WI"
PILOT_FIPS = "55"

# H3 resolutions (data contract: Global rules).
RES_SHIPPED = (5, 6, 7)
RES_WORK = 8
RES_PARTITION = 3

# Census cartographic boundary files, 1:500,000 (data contract: source `census`).
CENSUS_VINTAGE = 2025
CENSUS_BASE_URL = f"https://www2.census.gov/geo/tiger/GENZ{CENSUS_VINTAGE}/shp"
