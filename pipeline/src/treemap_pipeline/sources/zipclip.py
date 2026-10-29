"""Clip yearly CONUS rasters that ship as one zipped GeoTIFF per year to the pilot window.

Two ways in, tried in order:
1. A local zip in `data/raw/{source}/` (downloaded whole, by hand or by `download`).
2. Range reads of the zip on the host (`/vsizip//vsicurl/`), which fetch only the clip window.
   Needs the GeoTIFF stored uncompressed in the zip and a host that honors `Range`. When the
   zip compresses it and the source allows it (`download_if_compressed`), the whole zip is
   downloaded to `data/raw/{source}/` instead (resumable) and kept as the raw input.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    "CPL_VSIL_CURL_CACHE_SIZE": str(128 << 20),  # process-wide region cache, shared by the fetch workers
    "VSI_CACHE": "TRUE",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_TIMEOUT": "120",
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "10",
    "GDAL_HTTP_USERAGENT": USER_AGENT,
}
RETRIES = 4
DOWNLOAD_ATTEMPTS = 20  # resumed range requests per zip before giving up
CHUNK = 4 << 20


class CompressedZip(ValueError):
    """The remote zip compresses its GeoTIFF, so range reads would fetch all of it."""


@dataclass(frozen=True)
class ZipRaster:
    """A source with one zipped CONUS GeoTIFF per year at `{base_url}/{zip_name(year)}`."""

    source: str  # data contract source id; also the folder under data/raw/
    base_url: str
    years: range
    zip_name: Callable[[int], str]
    clip_stem: Callable[[int], str]
    download_if_compressed: bool = False

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
            raise CompressedZip(f"{self.zip_name(year)} compresses its GeoTIFF, so range reads would fetch it all; download the zip to {self.raw_dir()} instead")
        return f"/vsizip//vsicurl/{url}/{member.filename}"

    def download(self, year: int) -> Path:
        """Download the year's zip whole to data/raw/{source}/, resuming a partial file."""
        dest = self.raw_dir() / self.zip_name(year)
        part = dest.with_suffix(".zip.part")
        url = f"{self.base_url}/{self.zip_name(year)}"
        size = None
        for _ in range(DOWNLOAD_ATTEMPTS):
            have = part.stat().st_size if part.exists() else 0
            try:
                with _open(urllib.request.Request(url, headers={"Range": f"bytes={have}-"})) as r:
                    if r.status == 206:
                        size = int(r.headers["Content-Range"].rsplit("/", 1)[1])
                        mode = "ab"
                    else:  # range ignored: start over
                        size, mode = int(r.headers["Content-Length"]), "wb"
                    with open(part, mode) as f:
                        while chunk := r.read(CHUNK):
                            f.write(chunk)
            except (OSError, urllib.error.URLError, TimeoutError):
                continue  # resume from what arrived
            if size is not None and part.stat().st_size == size:
                break
        else:
            raise OSError(f"{url}: download incomplete after {DOWNLOAD_ATTEMPTS} attempts")
        with zipfile.ZipFile(part) as zf:
            bad = zf.testzip()  # CRC check of every member
        if bad is not None:
            part.unlink()
            raise OSError(f"{url}: {bad} failed its CRC check; partial file removed, run again")
        part.rename(dest)
        return dest

    def clip(self, year: int, geometry: dict, cover_cells: np.ndarray) -> Path:
        """Write the year's clip (state + 10 km, whole res-5 hexes) unless a matching one exists."""
        dest = self.clip_path(year)
        sidecar = dest.with_suffix(".window.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            path = self.source_path(year)
        except CompressedZip:
            if not self.download_if_compressed:
                raise
            self.download(year)
            path = self.source_path(year)
        with rasterio.Env(**GDAL_ENV), rasterio.open(path) as src:
            window = raster.clip_window(src, geometry, cover_cells)
            record = _window_record(src, window)
            if dest.exists() and _read_record(sidecar) == record:
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
            # Tif first, then the sidecar: a crash in between leaves a new tif with an old or
        # missing sidecar, which is re-clipped next time, never reused with a wrong window.
        tmp.rename(dest)
        sidecar_tmp = sidecar.with_suffix(".tmp")
        sidecar_tmp.write_text(json.dumps(record))
        sidecar_tmp.rename(sidecar)
        return dest

    def fetch_all(self, geometry: dict, cover_cells: np.ndarray, years=None, workers: int = 1) -> dict[int, Path]:
        """Clip every year (`workers` at a time); fail unless all clips share one grid."""
        years = list(self.years if years is None else years)
        clips = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self.clip, y, geometry, cover_cells): y for y in years}
            for done in as_completed(futures):
                try:
                    clips[futures[done]] = done.result()
                except Exception as e:
                    pool.shutdown(wait=False, cancel_futures=True)  # stop queued years; running ones finish
                    raise RuntimeError(f"{self.source} {futures[done]}: clip failed: {e}") from e
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


def _read_record(sidecar: Path) -> dict | None:
    """The sidecar's window record, or None if it is missing or unreadable (then re-clip)."""
    try:
        return json.loads(sidecar.read_text())
    except (OSError, ValueError):
        return None


def _window_record(src: rasterio.DatasetReader, window: Window) -> dict:
    return {"crs": src.crs.to_wkt(), "transform": list(src.window_transform(window))[:6], "width": int(window.width), "height": int(window.height)}
