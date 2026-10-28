"""Clip yearly CONUS rasters that ship as one zipped GeoTIFF per year to the pilot window.

Two ways in, tried in order:
1. A local zip in `data/raw/{source}/` (downloaded whole, e.g. by hand when the host is slow).
2. Range reads of the zip on the host (`/vsizip//vsicurl/`), which fetch only the clip window.
   Needs the GeoTIFF stored uncompressed in the zip and a host that honors `Range`.
Either way the result is a clipped GeoTIFF in `data/raw/{source}/clip/`, on the source's own
grid (same CRS and pixel alignment), so every year shares one cell grid. A sidecar JSON
records the clip window; a clip is reused only if the window still matches.
"""

import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from treemap_pipeline import config, raster

USER_AGENT = "treemap-pipeline/0.1 (+https://github.com/mvrcotc/us-tree-map)"
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".zip,.tif",
    "CPL_VSIL_CURL_CHUNK_SIZE": str(4 << 20),  # 4 MB range requests instead of 16 kB
    "VSI_CACHE": "TRUE",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_TIMEOUT": "120",
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "10",
    "GDAL_HTTP_USERAGENT": USER_AGENT,
}
RETRIES = 4


@dataclass(frozen=True)
class ZipRaster:
    """A source with one zipped CONUS GeoTIFF per year at `{base_url}/{zip_name(year)}`."""

    source: str  # data contract source id; also the folder under data/raw/
    base_url: str
    years: range
    zip_name: Callable[[int], str]
    clip_stem: Callable[[int], str]

    def raw_dir(self) -> Path:
        return config.RAW / self.source

    def clip_path(self, year: int) -> Path:
        return self.raw_dir() / "clip" / f"{self.clip_stem(year)}_{config.PILOT_STUSPS}.tif"

    def source_path(self, year: int) -> str:
        """GDAL path of the year's GeoTIFF: the local zip if present, else the remote zip."""
        local = self.raw_dir() / self.zip_name(year)
        if local.exists():
            with zipfile.ZipFile(local) as zf:
                return f"/vsizip/{local}/{_tif_member(zf).filename}"
        url = f"{self.base_url}/{self.zip_name(year)}"
        with zipfile.ZipFile(io.BufferedReader(HttpRange(url, self.raw_dir()), 1 << 16)) as zf:
            member = _tif_member(zf)
        if member.compress_type != zipfile.ZIP_STORED:
            raise ValueError(f"{self.zip_name(year)} compresses its GeoTIFF, so range reads would fetch it all; download the zip to {self.raw_dir()} instead")
        return f"/vsizip//vsicurl/{url}/{member.filename}"

    def clip(self, year: int, geometry: dict, cover_cells: np.ndarray) -> Path:
        """Write the year's clip (state + 10 km, whole res-5 hexes) unless a matching one exists."""
        dest = self.clip_path(year)
        sidecar = dest.with_suffix(".window.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.Env(**GDAL_ENV), rasterio.open(self.source_path(year)) as src:
            window = raster.clip_window(src, geometry, cover_cells)
            record = _window_record(src, window)
            if dest.exists() and sidecar.exists() and json.loads(sidecar.read_text()) == record:
                return dest
            tmp = dest.with_suffix(".part.tif")
            profile = src.profile | {
                "driver": "GTiff",
                "width": record["width"],
                "height": record["height"],
                "transform": src.window_transform(window),
                "compress": "deflate",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
            }
            with rasterio.open(tmp, "w", **profile) as dst:
                for r0 in range(0, record["height"], raster.STRIP_ROWS):
                    rows = min(raster.STRIP_ROWS, record["height"] - r0)
                    block = src.read(1, window=Window(window.col_off, window.row_off + r0, window.width, rows))
                    dst.write(block, 1, window=Window(0, r0, window.width, rows))
        tmp.rename(dest)
        sidecar.write_text(json.dumps(record))
        return dest

    def fetch_all(self, geometry: dict, cover_cells: np.ndarray, years=None, workers: int = 1) -> dict[int, Path]:
        """Clip every year (`workers` at a time); fail unless all clips share one grid."""
        years = list(self.years if years is None else years)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            clips = dict(zip(years, pool.map(lambda y: self.clip(y, geometry, cover_cells), years)))
        records = {json.dumps(json.loads(p.with_suffix(".window.json").read_text()), sort_keys=True) for p in clips.values()}
        if len(records) != 1:
            raise ValueError(f"{self.source}: years are on {len(records)} different grids; expected one")
        return clips


def _open(req: urllib.request.Request):
    """urlopen with retries and backoff (hosts answer 503 at times)."""
    req.add_header("User-Agent", USER_AGENT)
    for attempt in range(RETRIES + 1):
        try:
            return urllib.request.urlopen(req, timeout=120)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == RETRIES or (isinstance(e, urllib.error.HTTPError) and e.code < 500):
                raise
            time.sleep(10 * 2**attempt)


class HttpRange(io.RawIOBase):
    """Seekable read-only file over HTTP range requests (to list a remote zip's members)."""

    def __init__(self, url: str, raw_dir: Path):
        self.url, self.raw_dir, self.pos = url, raw_dir, 0
        with _open(urllib.request.Request(url, headers={"Range": "bytes=0-0"})) as r:
            self._require_partial(r)
            self.size = int(r.headers["Content-Range"].rsplit("/", 1)[1])

    def _require_partial(self, r) -> None:
        if r.status != 206:
            raise OSError(f"{self.url} ignores range requests (HTTP {r.status}); download the zip to {self.raw_dir} instead")

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        with _open(urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})) as r:
            self._require_partial(r)
            data = r.read()
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def _tif_member(zf: zipfile.ZipFile) -> zipfile.ZipInfo:
    tifs = [i for i in zf.infolist() if i.filename.lower().endswith(".tif")]
    if len(tifs) != 1:
        raise ValueError(f"expected one .tif in the zip, found {[i.filename for i in tifs]}")
    return tifs[0]


def _window_record(src: rasterio.DatasetReader, window: Window) -> dict:
    return {"crs": src.crs.to_wkt(), "transform": list(src.window_transform(window))[:6], "width": int(window.width), "height": int(window.height)}
