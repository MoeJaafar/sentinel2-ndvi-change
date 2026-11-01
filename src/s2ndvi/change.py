"""Compare two NDVI rasters and summarise where vegetation changed."""

from __future__ import annotations

import numpy as np

PIXEL_AREA_HA = 0.01  # a 10 m x 10 m Sentinel-2 pixel is 100 m^2


def ndvi_change(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Per-pixel NDVI difference (after minus before), NaN where either is masked."""
    if before.shape != after.shape:
        raise ValueError(f"shape mismatch: {before.shape} vs {after.shape}")
    return (after - before).astype("float32")


def change_summary(
    before: np.ndarray,
    after: np.ndarray,
    diff: np.ndarray,
    threshold: float = 0.15,
) -> dict:
    """Headline numbers for a report: means, change classes, areas in hectares."""
    valid = ~np.isnan(diff)
    n_valid = int(valid.sum())
    if n_valid == 0:
        raise ValueError("no valid pixels in both scenes")
    gain = valid & (diff > threshold)
    loss = valid & (diff < -threshold)
    stable = valid & ~gain & ~loss
    return {
        "threshold": threshold,
        "pixels_total": int(diff.size),
        "pixels_valid": n_valid,
        "valid_fraction": round(n_valid / diff.size, 4),
        "ndvi_mean_before": round(float(np.nanmean(before)), 4),
        "ndvi_mean_after": round(float(np.nanmean(after)), 4),
        "ndvi_diff_mean": round(float(np.nanmean(diff)), 4),
        "area_valid_ha": round(n_valid * PIXEL_AREA_HA, 1),
        "area_gain_ha": round(int(gain.sum()) * PIXEL_AREA_HA, 1),
        "area_loss_ha": round(int(loss.sum()) * PIXEL_AREA_HA, 1),
        "area_stable_ha": round(int(stable.sum()) * PIXEL_AREA_HA, 1),
        "share_gain": round(float(gain.sum() / n_valid), 4),
        "share_loss": round(float(loss.sum() / n_valid), 4),
        "share_stable": round(float(stable.sum() / n_valid), 4),
    }
