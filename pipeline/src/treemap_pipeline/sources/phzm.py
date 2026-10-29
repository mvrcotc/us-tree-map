"""2023 USDA Plant Hardiness Zone Map GIS data (source id `phzm`), as half-zones for the pilot window.

`phzm_us_grid_2023.zip` (41 MB, PRISM Climate Group, Oregon State) holds one ESRI BIL grid:
float32, 1991–2020 mean annual extreme minimum temperature in °F (attrunit "Degrees
Fahrenheit" in the metadata, checked Oct 29, 2026), 30″ (about 800 m) on NAD83 geographic,
nodata -9999. Terms: altered data need a prominent "not the official USDA Plant Hardiness
Zone Map" disclaimer and no USDA-ARS or OSU logos (data contract → `phzm`).

The clip stores the USDA half-zone index of each pixel, `floor((T + 60) / 5)`: 0 = 1a
(−60 to −55 °F), 1 = 1b, ..., 25 = 13b; 255 = nodata. It is upsampled `UPSAMPLE`× by
nearest neighbour so every res-8 hex (about 0.74 km², against about 0.6 km² per source pixel
in Wisconsin) holds pixel centers; values are unchanged, only repeated.
"""

import json
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine

from treemap_pipeline import config, raster
from treemap_pipeline.sources.zipclip import ZipRaster

YEAR = 2023
SOURCE = ZipRaster(
    source="phzm",
    base_url=f"https://prism.oregonstate.edu/phzm/data/{YEAR}",
    years=range(YEAR, YEAR + 1),
    zip_name=lambda year: f"phzm_us_grid_{year}.zip",
    clip_stem=lambda year: f"phzm_halfzone_{year}",
)
MEMBER = f"phzm_us_grid_{YEAR}.bil"
NODATA_IN = -9999.0
NODATA = 255
HALF_ZONES = 26  # 1a … 13b
UPSAMPLE = 4
DISCLAIMER = "Not the official USDA Plant Hardiness Zone Map."


def half_zone_index(temp_f: np.ndarray) -> np.ndarray:
    """uint8 half-zone index from °F (NaN or nodata → NODATA). A value on a band edge goes to the warmer half-zone."""
    t = np.asarray(temp_f, dtype=np.float64)
    ok = np.isfinite(t) & (t != NODATA_IN)
    idx = np.full(t.shape, NODATA, dtype=np.uint8)
    idx[ok] = np.clip(np.floor((t[ok] + 60) / 5), 0, HALF_ZONES - 1).astype(np.uint8)
    return idx


def label(index: int) -> str:
    """Half-zone label: 10 → '6a', 11 → '6b'."""
    return f"{index // 2 + 1}{'ab'[index % 2]}"


def number(index: int) -> float:
    """Numeric half-zone (data contract `zone_coldest_num`): 6a = 6.0, 6b = 6.5."""
    return index // 2 + 1 + 0.5 * (index % 2)


def clip(geometry: dict, cover_cells: np.ndarray) -> Path:
    """Write the upsampled half-zone clip for the pilot window unless a matching one exists."""
    zip_path = SOURCE.raw_dir() / SOURCE.zip_name(YEAR)
    if not zip_path.exists():
        SOURCE.raw_dir().mkdir(parents=True, exist_ok=True)
        SOURCE.download(YEAR)
    dest = SOURCE.clip_path(YEAR)
    sidecar = dest.with_suffix(".window.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(f"/vsizip/{zip_path}/{MEMBER}") as src:
        window = raster.clip_window(src, geometry, cover_cells)
        record = {
            "crs": src.crs.to_wkt(),
            "transform": list(src.window_transform(window))[:6],
            "width": int(window.width),
            "height": int(window.height),
            "upsample": UPSAMPLE,
        }
        if dest.exists() and _read(sidecar) == record:
            return dest
        idx = half_zone_index(src.read(1, window=window))
        transform = src.window_transform(window) @ Affine.scale(1 / UPSAMPLE)
        crs = src.crs
    fine = np.repeat(np.repeat(idx, UPSAMPLE, axis=0), UPSAMPLE, axis=1)
    tmp = dest.with_suffix(".part.tif")
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "width": fine.shape[1],
        "height": fine.shape[0],
        "crs": crs,
        "transform": transform,
        "nodata": NODATA,
        "compress": "deflate",
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
    }
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(fine, 1)
    tmp.rename(dest)  # tif first, then the sidecar (as in sources.zipclip)
    sidecar_tmp = sidecar.with_suffix(".tmp")
    sidecar_tmp.write_text(json.dumps(record))
    sidecar_tmp.rename(sidecar)
    return dest


def _read(sidecar: Path) -> dict | None:
    try:
        return json.loads(sidecar.read_text())
    except (OSError, ValueError):
        return None
