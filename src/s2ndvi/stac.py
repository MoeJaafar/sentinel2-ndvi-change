"""Find Sentinel-2 L2A scenes on the public Earth Search STAC catalog."""

from __future__ import annotations

from dataclasses import dataclass, field

import pystac_client
from shapely.geometry import box, shape

STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
BANDS = ("red", "nir", "scl")


@dataclass
class Scene:
    """One Sentinel-2 acquisition with the asset links we need."""

    id: str
    date: str
    cloud_cover: float
    hrefs: dict[str, str]
    scale: dict[str, float] = field(default_factory=dict)
    offset: dict[str, float] = field(default_factory=dict)


def band_scaling(asset, offset_applied: bool) -> tuple[float, float]:
    """Return (scale, offset) that turns stored digital numbers into reflectance.

    ESA L2A products from processing baseline 04.00 (Jan 2022) onwards store
    DN = (reflectance + 0.1) * 10000, and the raster extension advertises
    scale 0.0001 with offset -0.1. Earth Search, however, already subtracts
    that offset when it builds its COGs and says so with the item property
    ``earthsearch:boa_offset_applied``. Applying the offset a second time
    pushes dark pixels below zero and inflates NDVI, so the flag wins.
    """
    bands = asset.extra_fields.get("raster:bands") or [{}]
    info = bands[0]
    scale = float(info.get("scale", 1.0))
    offset = 0.0 if offset_applied else float(info.get("offset", 0.0))
    return scale, offset


def search_scenes(
    bbox: list[float],
    date_range: str,
    max_cloud: float = 10.0,
    require_full_coverage: bool = True,
) -> list[Scene]:
    """Return candidate scenes sorted by cloud cover, lowest first.

    bbox is [west, south, east, north] in WGS84. date_range is a STAC
    interval such as "2026-03-20/2026-04-30".
    """
    client = pystac_client.Client.open(STAC_URL)
    search = client.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": max_cloud}},
    )
    aoi = box(*bbox)
    scenes: list[Scene] = []
    for item in search.items():
        if require_full_coverage and not shape(item.geometry).contains(aoi):
            continue
        hrefs = {b: item.assets[b].href for b in BANDS}
        offset_applied = bool(item.properties.get("earthsearch:boa_offset_applied", False))
        scale, offset = {}, {}
        for b in ("red", "nir"):
            scale[b], offset[b] = band_scaling(item.assets[b], offset_applied)
        scenes.append(
            Scene(
                id=item.id,
                date=item.datetime.date().isoformat(),
                cloud_cover=float(item.properties["eo:cloud_cover"]),
                hrefs=hrefs,
                scale=scale,
                offset=offset,
            )
        )
    scenes.sort(key=lambda s: s.cloud_cover)
    return scenes
