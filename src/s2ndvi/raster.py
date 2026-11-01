"""Windowed reads of Sentinel-2 cloud-optimised GeoTIFFs and NDVI maths."""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.warp import transform_bounds
from rasterio.windows import bounds as window_bounds
from rasterio.windows import from_bounds as window_from_bounds

# Scene Classification Layer values that should not enter an NDVI comparison.
SCL_NODATA = 0
SCL_SATURATED = 1
SCL_CLOUD_SHADOW = 3
SCL_CLOUD_MEDIUM = 8
SCL_CLOUD_HIGH = 9
SCL_THIN_CIRRUS = 10
SCL_SNOW = 11
SCL_INVALID = (
    SCL_NODATA,
    SCL_SATURATED,
    SCL_CLOUD_SHADOW,
    SCL_CLOUD_MEDIUM,
    SCL_CLOUD_HIGH,
    SCL_THIN_CIRRUS,
    SCL_SNOW,
)


def read_band(href: str, bbox_wgs84: list[float], out_shape: tuple[int, int] | None = None):
    """Read only the part of a remote COG that covers bbox_wgs84.

    Returns (array, transform, crs). When out_shape is given the window is
    resampled to that shape (used to bring the 20 m SCL band onto the 10 m
    grid of the red and NIR bands).
    """
    with rasterio.open(href) as ds:
        bounds = transform_bounds("EPSG:4326", ds.crs, *bbox_wgs84)
        window = window_from_bounds(*bounds, ds.transform).round_offsets().round_lengths()
        data = ds.read(
            1,
            window=window,
            out_shape=out_shape,
            resampling=Resampling.nearest,
            boundless=True,
            fill_value=0,
        )
        wb = window_bounds(window, ds.transform)
        height, width = data.shape
        transform = transform_from_bounds(*wb, width, height)
        return data, transform, ds.crs


def scaled_reflectance(dn: np.ndarray, scale: float, offset: float) -> np.ndarray:
    """Convert digital numbers to surface reflectance in [0, 1]."""
    refl = dn.astype("float32") * scale + offset
    return np.clip(refl, 0.0, 1.0)


def cloud_mask(scl: np.ndarray) -> np.ndarray:
    """True where a pixel is cloud, shadow, snow, saturated or missing."""
    return np.isin(scl, SCL_INVALID)


def ndvi(red: np.ndarray, nir: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Normalised Difference Vegetation Index, NaN where masked."""
    red = red.astype("float32")
    nir = nir.astype("float32")
    denom = nir + red
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(denom > 0, (nir - red) / denom, np.nan).astype("float32")
    if mask is not None:
        out[mask] = np.nan
    return out
