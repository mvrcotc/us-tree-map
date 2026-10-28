"""USFS NLCD Tree Canopy Cover v2025-6 (source id `tcc`), clipped to the pilot window.

One CONUS zip per year (about 3.6 GB) on the USFS raster gateway, storing one tiled,
deflate-compressed uint8 GeoTIFF; the host honors range requests (checked Oct 28, 2026).
Values (from the GeoTIFF's metadata, Oct 28, 2026): 0–100 = percent canopy cover,
254 = non-processing area, 255 = background (nodata). Clipping: `sources.zipclip`.
"""

from treemap_pipeline.sources.zipclip import ZipRaster

VERSION = "v2025-6"
VALID_MIN, VALID_MAX = 0, 100  # 254 and 255 fall outside, so they count as invalid
SOURCE = ZipRaster(
    source="tcc",
    base_url=f"https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/docs/{VERSION}",
    years=range(1985, 2026),
    zip_name=lambda year: f"nlcd_tcc_conus_{year}_{VERSION}_wgs84.zip",
    clip_stem=lambda year: f"nlcd_tcc_conus_{year}_{VERSION}",
)
YEARS = SOURCE.years
