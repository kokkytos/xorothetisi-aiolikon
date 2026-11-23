import pathlib
import sys

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from xorothetisi_aiolikon import rasterize_mask, slope_degrees, write_filled_dem  # noqa: E402


def test_slope_of_inclined_plane():
    res = 100.0
    dem = np.tile(np.arange(50) * res * np.tan(np.radians(10)), (50, 1))
    s = slope_degrees(dem, res, res)
    assert np.allclose(s[1:-1, 1:-1], 10, atol=1e-6)
    assert np.isnan(s[0, 0])  # οι ακμές δεν υπολογίζονται


def test_rasterize_mask():
    info = {"transform": from_origin(0, 1000, 100, 100), "shape": (10, 10)}
    m = rasterize_mask(gpd.GeoDataFrame(geometry=[box(0, 800, 300, 1000)]), info)
    assert m.sum() == 6 and m[:2, :3].all()


def test_filled_dem_has_no_nodata(tmp_path):
    dem = np.full((20, 20), 100.0)
    dem[5:8, 5:8] = np.nan
    info = {"transform": from_origin(0, 2000, 100, 100), "shape": (20, 20), "crs": "EPSG:2100"}
    p = tmp_path / "f.tif"
    write_filled_dem(dem, info, p)
    with rasterio.open(p) as src:
        assert src.nodata is None and np.isfinite(src.read(1)).all()
