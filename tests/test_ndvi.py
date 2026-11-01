import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s2ndvi import change_summary, cloud_mask, ndvi, ndvi_change, scaled_reflectance  # noqa: E402


def test_ndvi_known_values():
    red = np.array([[0.1, 0.2], [0.3, 0.0]], dtype="float32")
    nir = np.array([[0.5, 0.2], [0.1, 0.0]], dtype="float32")
    out = ndvi(red, nir)
    assert np.isclose(out[0, 0], (0.5 - 0.1) / 0.6)
    assert out[0, 1] == 0.0
    assert out[1, 0] < 0
    assert np.isnan(out[1, 1])  # zero denominator


def test_ndvi_mask_sets_nan():
    red = np.full((2, 2), 0.1, dtype="float32")
    nir = np.full((2, 2), 0.5, dtype="float32")
    mask = np.array([[True, False], [False, False]])
    out = ndvi(red, nir, mask)
    assert np.isnan(out[0, 0]) and not np.isnan(out[1, 1])


def test_cloud_mask_flags_cloud_and_nodata():
    scl = np.array([[0, 4], [9, 5]])
    assert cloud_mask(scl).tolist() == [[True, False], [True, False]]


def test_scaled_reflectance_applies_offset_and_clips():
    dn = np.array([0, 1000, 11000], dtype="uint16")
    refl = scaled_reflectance(dn, 1e-4, -0.1)
    assert np.allclose(refl, [0.0, 0.0, 1.0])


def test_change_summary_areas():
    before = np.zeros((10, 10), dtype="float32")
    after = np.zeros((10, 10), dtype="float32")
    after[:2, :] = 0.5  # 20 pixels gain
    after[2:3, :] = -0.5  # 10 pixels loss
    diff = ndvi_change(before, after)
    s = change_summary(before, after, diff, threshold=0.15)
    assert s["pixels_valid"] == 100
    assert s["area_gain_ha"] == 0.2
    assert s["area_loss_ha"] == 0.1
    assert s["area_stable_ha"] == 0.7


def test_band_scaling_respects_offset_applied_flag():
    from s2ndvi.stac import band_scaling

    class FakeAsset:
        extra_fields = {"raster:bands": [{"scale": 0.0001, "offset": -0.1}]}

    assert band_scaling(FakeAsset(), offset_applied=False) == (0.0001, -0.1)
    assert band_scaling(FakeAsset(), offset_applied=True) == (0.0001, 0.0)
