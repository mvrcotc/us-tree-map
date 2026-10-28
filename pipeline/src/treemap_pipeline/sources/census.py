"""Download the Census cartographic boundary files (source id `census`)."""

import shutil
import urllib.request
from pathlib import Path

from treemap_pipeline import config

LAYERS = ("state", "county")


def zip_name(layer: str) -> str:
    return f"cb_{config.CENSUS_VINTAGE}_us_{layer}_500k.zip"


def raw_dir() -> Path:
    return config.RAW / "census"


def download(layer: str) -> Path:
    """Fetch one boundary zip into data/raw/census/ unless it is already there."""
    dest = raw_dir() / zip_name(layer)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(f"{config.CENSUS_BASE_URL}/{zip_name(layer)}") as resp, tmp.open("wb") as f:
        shutil.copyfileobj(resp, f)
    tmp.rename(dest)
    return dest


def download_all() -> dict[str, Path]:
    return {layer: download(layer) for layer in LAYERS}
