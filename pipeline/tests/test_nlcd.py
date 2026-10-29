"""sources.zipclip (via nlcd and tcc): zip handling, range reads and clips on synthetic files (no network)."""

import dataclasses
import io
import json
import os
import zipfile

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from treemap_pipeline import config
from treemap_pipeline.build import hex_base
from treemap_pipeline.sources import nlcd, tcc, zipclip

SRC = nlcd.SOURCE

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
    monkeypatch.setattr(config, "RAW", tmp_path)
    (tmp_path / "nlcd").mkdir()
    return tmp_path / "nlcd"


@pytest.fixture(scope="module")
def cover():
    return hex_base.build_hex_base(GEOMETRY)[5]["h3"].to_numpy()


def test_clip_from_local_zip_is_on_the_source_grid(raw, cover):
    data = make_zip(raw / SRC.zip_name(2025), zipfile.ZIP_STORED)
    path = SRC.clip(2025, GEOMETRY, cover)
    record = json.loads(path.with_suffix(".window.json").read_text())
    with rasterio.open(f"/vsizip/{raw / SRC.zip_name(2025)}/Annual_NLCD_LndCov_2025_CU_C1V2.tif") as src, rasterio.open(path) as clip:
        col, row = ~src.transform @ (clip.transform.c, clip.transform.f)
        assert col == int(col) and row == int(row), "whole-pixel offset: same pixel alignment"
        assert clip.crs == src.crs and clip.res == src.res
        assert np.array_equal(clip.read(1), data[int(row) : int(row) + clip.height, int(col) : int(col) + clip.width])
        assert (clip.width, clip.height) == (record["width"], record["height"])


def test_clip_is_reused_only_when_the_window_matches(raw, cover):
    make_zip(raw / SRC.zip_name(2025), zipfile.ZIP_STORED)
    path = SRC.clip(2025, GEOMETRY, cover)
    mtime = os.path.getmtime(path)
    before = json.loads(path.with_suffix(".window.json").read_text())
    assert os.path.getmtime(SRC.clip(2025, GEOMETRY, cover)) == mtime
    moved = dict(GEOMETRY, coordinates=[[[x + 0.05, y] for x, y in GEOMETRY["coordinates"][0]]])
    moved_cover = hex_base.build_hex_base(moved)[5]["h3"].to_numpy()
    SRC.clip(2025, moved, moved_cover)
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
    monkeypatch.setattr(zipclip, "_open", serve((tmp_path / "remote.zip").read_bytes(), honor_range=False))
    with pytest.raises(OSError, match="ignores range requests"):
        SRC.source_path(2025)


def test_remote_stored_zip_gives_a_vsicurl_path(raw, tmp_path, monkeypatch):
    make_zip(tmp_path / "remote.zip", zipfile.ZIP_STORED)
    monkeypatch.setattr(zipclip, "_open", serve((tmp_path / "remote.zip").read_bytes(), honor_range=True))
    path = SRC.source_path(2025)
    assert path == f"/vsizip//vsicurl/{SRC.base_url}/{SRC.zip_name(2025)}/Annual_NLCD_LndCov_2025_CU_C1V2.tif"


def test_remote_deflated_zip_is_refused(raw, tmp_path, monkeypatch):
    make_zip(tmp_path / "remote.zip", zipfile.ZIP_DEFLATED)
    monkeypatch.setattr(zipclip, "_open", serve((tmp_path / "remote.zip").read_bytes(), honor_range=True))
    with pytest.raises(zipclip.CompressedZip, match="compresses its GeoTIFF"):
        SRC.source_path(2025)


def flaky(blob: bytes, cut: int):
    """Serve ranges, but drop the connection after `cut` bytes of each response."""
    def fake_open(req):
        a = int(req.get_header("Range").removeprefix("bytes=").split("-")[0])
        return Cutoff(blob[a:], 206, {"Content-Range": f"bytes {a}-{len(blob) - 1}/{len(blob)}"}, cut)
    return fake_open


class Cutoff(FakeResponse):
    def __init__(self, body, status, headers, cut):
        super().__init__(body, status, headers)
        self.cut, self.sent = cut, 0

    def read(self, n=-1):
        if self.sent >= self.cut:
            raise ConnectionResetError("dropped")
        data = super().read(min(n, self.cut - self.sent) if n > 0 else self.cut - self.sent)
        self.sent += len(data)
        return data


def test_deflated_zip_is_downloaded_with_resume_then_clipped(raw, tmp_path, cover, monkeypatch):
    data = make_zip(tmp_path / "remote.zip", zipfile.ZIP_DEFLATED)
    blob = (tmp_path / "remote.zip").read_bytes()
    monkeypatch.setattr(zipclip, "_open", flaky(blob, cut=len(blob) // 3 + 1))
    path = SRC.clip(2025, GEOMETRY, cover)
    assert (raw / SRC.zip_name(2025)).read_bytes() == blob
    assert not (raw / (SRC.zip_name(2025) + ".part")).exists()
    with rasterio.open(path) as clip:
        assert clip.read(1).size > 0 and set(np.unique(clip.read(1))) <= set(np.unique(data))


def test_download_not_allowed_raises(raw, tmp_path, cover, monkeypatch):
    make_zip(tmp_path / "remote.zip", zipfile.ZIP_DEFLATED)
    monkeypatch.setattr(zipclip, "_open", serve((tmp_path / "remote.zip").read_bytes(), honor_range=True))
    strict = dataclasses.replace(SRC, download_if_compressed=False)
    with pytest.raises(zipclip.CompressedZip):
        strict.clip(2025, GEOMETRY, cover)


def test_tcc_names_match_the_gateway():
    """URL and clip names as listed on the USFS raster gateway (checked Oct 28, 2026)."""
    assert f"{tcc.SOURCE.base_url}/{tcc.SOURCE.zip_name(2025)}" == "https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/docs/v2025-6/nlcd_tcc_conus_2025_v2025-6_wgs84.zip"
    assert tcc.SOURCE.clip_path(1985).parent == config.RAW / "tcc" / "clip"
    assert list(tcc.YEARS) == list(range(1985, 2026))


def test_fetch_all_with_workers(raw, cover):
    for year in (2024, 2025):
        make_zip(raw / SRC.zip_name(year), zipfile.ZIP_STORED, year)
    clips = SRC.fetch_all(GEOMETRY, cover, years=[2024, 2025], workers=2)
    assert sorted(clips) == [2024, 2025] and all(p.exists() for p in clips.values())


def test_unreadable_sidecar_means_reclip(raw, cover):
    make_zip(raw / SRC.zip_name(2025), zipfile.ZIP_STORED)
    path = SRC.clip(2025, GEOMETRY, cover)
    path.with_suffix(".window.json").write_text('{"crs": ')  # cut short by a crash
    mtime = os.path.getmtime(path)
    SRC.clip(2025, GEOMETRY, cover)
    assert os.path.getmtime(path) != mtime
    assert json.loads(path.with_suffix(".window.json").read_text())["width"] > 0


def test_fetch_all_names_the_failed_year(raw, cover):
    make_zip(raw / SRC.zip_name(2024), zipfile.ZIP_STORED, 2024)
    (raw / SRC.zip_name(2025)).write_bytes(b"not a zip")
    with pytest.raises(RuntimeError, match="nlcd 2025: clip failed"):
        SRC.fetch_all(GEOMETRY, cover, years=[2024, 2025], workers=2)
