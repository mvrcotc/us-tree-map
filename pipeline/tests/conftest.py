"""Test-wide setup.

Synthetic rasters and cell grids from the tests take hundreds of MB per run; keep pytest's
temp folders on the project drive (data/work/tmp, gitignored), not the nearly full startup
disk. pytest still keeps only its last three runs there.
"""

import tempfile

from treemap_pipeline import config

_TMP = config.WORK / "tmp"
_TMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_TMP)
