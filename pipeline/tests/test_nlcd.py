"""sources.nlcd: zip handling, range reads and clips on synthetic files (no network)."""

import io
import json
import os
import zipfile

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from treemap_pipeline.build import hex_base
from treemap_pipeline.sources import nlcd

LNG, LAT = -89.40, 43.07
GEOMETRY = {"type": "Polygon", "coordinates": [[[LNG - 0.02, LAT - 0.015], [LNG + 0.02, LAT - 0.015], [LNG + 0.02, LAT + 0.015], [LNG - 0.02, LAT + 0.015], [LNG - 0.02, LAT - 0.015]]]}
SIZE = 2000  # 60 km at 30 m: a stand-in for the CONUS mosaic


def make_zip(path, compression, year=2025):
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform(LNG, LAT)
    tif = io.BytesIO()
    data = np.random.default_rng(year).choice([11, 41, 82], size=(SIZE, SIZE)).astype(np.uint8)
    with rasterio.MemoryFile() as mem:
        with mem.open(driver="GTiff", width=SIZE, height=SIZE, count=1, dtype="uint8", crs="EPSG:5070", transform=from_origin(round(x / 30) * 30 - 30_000, round(y / 30) * 30 + 30_000, 30, 30), nodata=250, tiled=True) as ds:
            ds.write(data, 1)
        tif.write(mem.read())
    with zipfile.ZipFile(path, "w", compression=compression) as zf:
        zf.writestr(f"Annual_NLCD_LndCov_{year}_CU_C1V2.tif", tif.getvalue())
    return data


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setattr(nlcd, "raw_dir", lambda: tmp_path / "nlcd")
    (tmp_path / "nlcd").mkdir()
    return tmp_path / "nlcd"


@pytest.fixture(scope="module")
def cover():
    return hex_base.build_hex_base(GEOMETRY)[5]["h3"].to_numpy()


def test_clip_from_local_zip_is_on_the_source_grid(raw, cover):
    data = make_zip(raw / nlcd.zip_name(2025), zipfile.ZIP_STORED)
    path = nlcd.clip(2025, GEOMETRY, cover)
    record = json.loads(path.with_suffix(".window.json").read_text())
    with rasterio.open(f"/vsizip/{raw / nlcd.zip_name(2025)}/Annual_NLCD_LndCov_2025_CU_C1V2.tif") as src, rasterio.open(path) as clip:
        col, row = ~src.transform @ (clip.transform.c, clip.transform.f)
        assert col == int(col) and row == int(row), "whole-pixel offset: same pixel alignment"
        assert clip.crs == src.crs and clip.res == src.res
        assert np.array_equal(clip.read(1), data[int(row) : int(row) + clip.height, int(col) : int(col) + clip.width])
        assert (clip.width, clip.height) == (record["width"], record["height"])


def test_clip_is_reused_only_when_the_window_matches(raw, cover):
    make_zip(raw / nlcd.zip_name(2025), zipfile.ZIP_STORED)
    path = nlcd.clip(2025, GEOMETRY, cover)
    mtime = os.path.getmtime(path)
    before = json.loads(path.with_suffix(".window.json").read_text())
    assert os.path.getmtime(nlcd.clip(2025, GEOMETRY, cover)) == mtime
    moved = dict(GEOMETRY, coordinates=[[[x + 0.05, y] for x, y in GEOMETRY["coordinates"][0]]])
    moved_cover = hex_base.build_hex_base(moved)[5]["h3"].to_numpy()
    nlcd.clip(2025, moved, moved_cover)
    assert json.loads(path.with_suffix(".window.json").read_text()) != before
    assert os.path.getmtime(path) != mtime


class FakeResponse(io.BytesIO):
    def __init__(self, body, status, headers):
        super().__init__(body)
        self.status, self.headers = status, headers

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def serve(blob: bytes, honor_range: bool):
    def fake_open(req):
        rng = req.get_header("Range")
        if not honor_range or rng is None:
            return FakeResponse(blob, 200, {"Content-Length": str(len(blob))})
        a, b = (int(v) for v in rng.removeprefix("bytes=").split("-"))
        return FakeResponse(blob[a : b + 1], 206, {"Content-Range": f"bytes {a}-{b}/{len(blob)}"})

    return fake_open


def test_remote_zip_must_honor_ranges(raw, tmp_path, monkeypatch):
    make_zip(tmp_path / "remote.zip", zipfile.ZIP_STORED)
    monkeypatch.setattr(nlcd, "_open", serve((tmp_path / "remote.zip").read_bytes(), honor_range=False))
    with pytest.raises(OSError, match="ignores range requests"):
        nlcd.source_path(2025)


def test_remote_stored_zip_gives_a_vsicurl_path(raw, tmp_path, monkeypatch):
    make_zip(tmp_path / "remote.zip", zipfile.ZIP_STORED)
    monkeypatch.setattr(nlcd, "_open", serve((tmp_path / "remote.zip").read_bytes(), honor_range=True))
    path = nlcd.source_path(2025)
    assert path == f"/vsizip//vsicurl/{nlcd.BASE_URL}/{nlcd.zip_name(2025)}/Annual_NLCD_LndCov_2025_CU_C1V2.tif"


def test_remote_deflated_zip_is_refused(raw, tmp_path, monkeypatch):
    make_zip(tmp_path / "remote.zip", zipfile.ZIP_DEFLATED)
    monkeypatch.setattr(nlcd, "_open", serve((tmp_path / "remote.zip").read_bytes(), honor_range=True))
    with pytest.raises(ValueError, match="compresses its GeoTIFF"):
        nlcd.source_path(2025)
