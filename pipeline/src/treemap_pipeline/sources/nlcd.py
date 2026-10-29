"""Annual NLCD Collection 1.2 Land Cover (source id `nlcd`), clipped to the pilot window.

One CONUS zip per year (size unverified: ScienceBase lists 1.35–1.46 GB per year, Oct 28,
2026), each holding one deflated GeoTIFF. Clipping and range reads: `sources.zipclip`.
"""

from treemap_pipeline.sources.zipclip import ZipRaster

COLLECTION = "C1V2"
SOURCE = ZipRaster(
    source="nlcd",
    base_url="https://www.mrlc.gov/downloads/sciweb1/shared/mrlc/data-bundles",
    years=range(1985, 2026),
    zip_name=lambda year: f"Annual_NLCD_LndCov_{year}_CU_{COLLECTION}.zip",
    clip_stem=lambda year: f"Annual_NLCD_LndCov_{year}_CU_{COLLECTION}",
    # MRLC's zips deflate the GeoTIFF (checked Oct 28, 2026), so range reads can't clip them:
    # download each whole (about 1.4 GB) to data/raw/nlcd/ (Marco, Oct 28, 2026).
    download_if_compressed=True,
)
YEARS = SOURCE.years
