"""Figures for the NDVI change report."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.colors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from rasterio.plot import plotting_extent  # noqa: E402


def _overlay_aoi(ax, aoi: gpd.GeoDataFrame, crs) -> None:
    aoi.to_crs(crs).boundary.plot(ax=ax, color="black", linewidth=0.8)


def plot_change_maps(
    before: np.ndarray,
    after: np.ndarray,
    diff: np.ndarray,
    transform,
    crs,
    aoi: gpd.GeoDataFrame,
    labels: tuple[str, str],
    out_path: Path,
) -> None:
    """Three panels: NDVI before, NDVI after, and the difference."""
    extent = plotting_extent(before, transform)
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), constrained_layout=True)

    for ax, arr, title in zip(axes[:2], (before, after), labels):
        im = ax.imshow(arr, cmap="YlGn", vmin=0.0, vmax=0.8, extent=extent)
        ax.set_title(f"NDVI {title}")
        _overlay_aoi(ax, aoi, crs)
        fig.colorbar(im, ax=ax, shrink=0.8, label="NDVI")

    im = axes[2].imshow(diff, cmap="RdYlGn", vmin=-0.5, vmax=0.5, extent=extent)
    axes[2].set_title(f"NDVI change ({labels[1]} minus {labels[0]})")
    _overlay_aoi(axes[2], aoi, crs)
    fig.colorbar(im, ax=axes[2], shrink=0.8, label="NDVI difference")

    for ax in axes:
        ax.set_xlabel(f"Easting (m, {crs})")
        ax.set_ylabel("Northing (m)")
        ax.tick_params(labelsize=7)

    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_change_classes(
    diff: np.ndarray,
    transform,
    crs,
    aoi: gpd.GeoDataFrame,
    threshold: float,
    summary: dict,
    out_path: Path,
) -> None:
    """Map of gain / stable / loss classes plus a histogram of the difference."""
    extent = plotting_extent(diff, transform)
    classes = np.full(diff.shape, np.nan, dtype="float32")
    valid = ~np.isnan(diff)
    classes[valid] = 0
    classes[valid & (diff > threshold)] = 1
    classes[valid & (diff < -threshold)] = -1

    cmap = matplotlib.colors.ListedColormap(["#c0392b", "#d9d9d9", "#27ae60"])
    norm = matplotlib.colors.BoundaryNorm([-1.5, -0.5, 0.5, 1.5], cmap.N)

    fig, (ax_map, ax_hist) = plt.subplots(
        1, 2, figsize=(14, 5.5), constrained_layout=True, gridspec_kw={"width_ratios": [1.3, 1]}
    )
    im = ax_map.imshow(classes, cmap=cmap, norm=norm, extent=extent)
    _overlay_aoi(ax_map, aoi, crs)
    cbar = fig.colorbar(im, ax=ax_map, ticks=[-1, 0, 1], shrink=0.8)
    cbar.ax.set_yticklabels(["loss", "stable", "gain"])
    ax_map.set_title(
        f"Vegetation change classes (|dNDVI| > {threshold})\n"
        f"gain {summary['area_gain_ha']:.0f} ha, loss {summary['area_loss_ha']:.0f} ha, "
        f"stable {summary['area_stable_ha']:.0f} ha"
    )
    ax_map.set_xlabel(f"Easting (m, {crs})")
    ax_map.set_ylabel("Northing (m)")
    ax_map.tick_params(labelsize=7)

    vals = diff[valid]
    ax_hist.hist(vals, bins=80, range=(-0.8, 0.8), color="#555", edgecolor="none")
    ax_hist.axvline(-threshold, color="#c0392b", linestyle="--", label="loss threshold")
    ax_hist.axvline(threshold, color="#27ae60", linestyle="--", label="gain threshold")
    ax_hist.axvline(0, color="black", linewidth=0.8)
    ax_hist.set_xlabel("NDVI difference")
    ax_hist.set_ylabel("Pixels")
    ax_hist.set_title("Distribution of per-pixel NDVI change")
    ax_hist.legend()

    fig.savefig(out_path, dpi=150)
    plt.close(fig)
