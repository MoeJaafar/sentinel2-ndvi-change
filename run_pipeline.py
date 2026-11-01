"""Sentinel-2 NDVI change detection: search, download windows, compare, report.

Example:
    python run_pipeline.py --before 2025-03-20/2025-04-30 --after 2026-03-20/2026-04-30
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).parent / "src"))

from s2ndvi import (  # noqa: E402
    change_summary,
    cloud_mask,
    ndvi,
    ndvi_change,
    read_band,
    scaled_reflectance,
    search_scenes,
)
from s2ndvi.plots import plot_change_classes, plot_change_maps  # noqa: E402

MIN_VALID_FRACTION = 0.90


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aoi", default="aoi/aleppo_fields.geojson", help="GeoJSON polygon in WGS84")
    p.add_argument("--before", default="2025-03-20/2025-04-30", help="STAC date interval for the first scene")
    p.add_argument("--after", default="2026-03-20/2026-04-30", help="STAC date interval for the second scene")
    p.add_argument("--max-cloud", type=float, default=10.0, help="max scene cloud cover in percent")
    p.add_argument("--threshold", type=float, default=0.15, help="|dNDVI| above which a pixel counts as changed")
    p.add_argument("--out", default="outputs", help="output directory")
    return p.parse_args()


def load_scene(bbox: list[float], date_range: str, max_cloud: float):
    """Pick the clearest scene whose AOI window is at least 90 percent valid."""
    candidates = search_scenes(bbox, date_range, max_cloud=max_cloud)
    if not candidates:
        raise SystemExit(f"no scenes under {max_cloud}% cloud fully covering the AOI in {date_range}")
    for scene in candidates:
        print(f"  trying {scene.id} ({scene.date}, {scene.cloud_cover:.1f}% cloud)")
        red_dn, transform, crs = read_band(scene.hrefs["red"], bbox)
        nir_dn, _, _ = read_band(scene.hrefs["nir"], bbox)
        scl, _, _ = read_band(scene.hrefs["scl"], bbox, out_shape=red_dn.shape)
        mask = cloud_mask(scl)
        valid_fraction = 1.0 - mask.mean()
        print(f"    valid pixels in AOI: {valid_fraction:.1%}")
        if valid_fraction < MIN_VALID_FRACTION:
            continue
        red = scaled_reflectance(red_dn, scene.scale["red"], scene.offset["red"])
        nir = scaled_reflectance(nir_dn, scene.scale["nir"], scene.offset["nir"])
        return scene, ndvi(red, nir, mask), transform, crs, valid_fraction
    raise SystemExit(f"every candidate scene in {date_range} had too many masked pixels over the AOI")


def write_geotiff(path: Path, arr: np.ndarray, transform, crs, description: str) -> None:
    profile = {
        "driver": "GTiff",
        "height": arr.shape[0],
        "width": arr.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": transform,
        "nodata": np.nan,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype("float32"), 1)
        dst.set_band_description(1, description)


def main() -> None:
    args = parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    aoi = gpd.read_file(args.aoi)
    if aoi.crs is None:
        aoi = aoi.set_crs("EPSG:4326")
    bbox = [float(v) for v in aoi.to_crs("EPSG:4326").total_bounds]
    print(f"AOI bbox (WGS84): {bbox}")

    print("Selecting BEFORE scene")
    s_before, ndvi_before, transform, crs, vf_before = load_scene(bbox, args.before, args.max_cloud)
    print("Selecting AFTER scene")
    s_after, ndvi_after, transform_after, crs_after, vf_after = load_scene(bbox, args.after, args.max_cloud)

    if crs != crs_after or ndvi_before.shape != ndvi_after.shape:
        raise SystemExit(
            "the two scenes do not share a grid; pick dates on the same tile or add reprojection "
            f"({crs} {ndvi_before.shape} vs {crs_after} {ndvi_after.shape})"
        )

    diff = ndvi_change(ndvi_before, ndvi_after)
    summary = change_summary(ndvi_before, ndvi_after, diff, threshold=args.threshold)
    summary["before"] = {
        "scene": s_before.id,
        "date": s_before.date,
        "cloud_cover": s_before.cloud_cover,
        "valid_fraction": round(vf_before, 4),
    }
    summary["after"] = {
        "scene": s_after.id,
        "date": s_after.date,
        "cloud_cover": s_after.cloud_cover,
        "valid_fraction": round(vf_after, 4),
    }
    summary["aoi"] = {"file": args.aoi, "bbox_wgs84": bbox, "crs": str(crs), "shape": list(ndvi_before.shape)}

    write_geotiff(out / "ndvi_before.tif", ndvi_before, transform, crs, f"NDVI {s_before.date}")
    write_geotiff(out / "ndvi_after.tif", ndvi_after, transform, crs, f"NDVI {s_after.date}")
    write_geotiff(out / "ndvi_change.tif", diff, transform, crs, "NDVI difference, after minus before")
    plot_change_maps(
        ndvi_before, ndvi_after, diff, transform, crs, aoi, (s_before.date, s_after.date), out / "ndvi_maps.png"
    )
    plot_change_classes(diff, transform, crs, aoi, args.threshold, summary, out / "ndvi_change_classes.png")
    (out / "summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
