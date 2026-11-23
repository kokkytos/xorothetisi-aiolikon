#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Χωροθέτηση περιοχών (π.χ. αιολικών) - αναπαραγώγιμη υλοποίηση χωρίς QGIS.

Ροή:
  1. Εξαγωγή της Περιφερειακής Ενότητας (NAME_GR == όνομα)
  2. Buffer γύρω από την ΠΕ
  3. Επιλογή οικισμών που τέμνουν το buffer
  4. Viewshed από τους οικισμούς (ένωση των ορατών περιοχών)
  5. Raster Natura 2000
  6. Μη επιτρεπόμενες = ορατές από οικισμούς OR Natura
  7. Επιτρεπόμενες  = (άνεμος > όριο) AND (κλίση < όριο)
  8. Περιοχές χωροθέτησης = Επιτρεπόμενες AND NOT Μη επιτρεπόμενες
  9. Αποκοπή στα όρια της ΠΕ και μετατροπή σε πολύγωνα

Όλες οι παράμετροι και οι διαδρομές αρχείων ορίζονται στο config.yaml.
Μαζί με το αποτέλεσμα (GeoPackage) παράγονται αυτόματα:
  - provenance.json   (παράμετροι, checksums εισόδων, εκδόσεις λογισμικού, git commit)
  - datapackage.json  (μεταδεδομένα Frictionless Data για το αποτέλεσμα)

Χρήση:  python src/xorothetisi_aiolikon.py --config config.yaml
"""
import argparse
import hashlib
import importlib.metadata as md
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import yaml
from rasterio import features
from rasterio.fill import fillnodata
from rasterio.warp import Resampling, reproject

__version__ = "1.0.0"
REGION_FIELD = "NAME_GR"


# ----------------------------------------------------------------------------
# Επεξεργασία δεδομένων
# ----------------------------------------------------------------------------
def read_dem(path):
    """Διαβάζει το DEM -> (πίνακας float64 με NaN στα nodata, πλέγμα)."""
    with rasterio.open(path) as src:
        arr = src.read(1).astype("float64")
        if src.nodata is not None:
            arr[arr == src.nodata] = np.nan
        info = {
            "transform": src.transform,
            "crs": src.crs,
            "shape": (src.height, src.width),
            "xres": abs(src.transform.a),
            "yres": abs(src.transform.e),
        }
    return arr, info


def slope_degrees(dem, xres, yres, scale=1.0):
    """Κλίση σε μοίρες, αλγόριθμος Horn (όπως gdaldem slope, χωρίς compute edges)."""
    p = np.pad(dem, 1, constant_values=np.nan)
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * xres)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * yres)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy) / scale))


def reproject_to_dem_grid(path, info):
    """Επαναπροβολή (nearest) ενός raster στο πλέγμα του DEM."""
    dst = np.full(info["shape"], np.nan, dtype="float32")
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
            dst_transform=info["transform"],
            dst_crs=info["crs"],
            resampling=Resampling.nearest,
        )
    return dst


def rasterize_mask(gdf, info):
    """Boolean μάσκα: True στα κελιά που καλύπτονται από τα πολύγωνα."""
    if len(gdf) == 0:
        return np.zeros(info["shape"], dtype=bool)
    out = features.rasterize(
        ((geom, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty),
        out_shape=info["shape"],
        transform=info["transform"],
        fill=0,
        dtype="uint8",
    )
    return out.astype(bool)


def write_filled_dem(dem, info, path):
    """
    Αντίγραφο του DEM χωρίς nodata (το gdal viewshed τα διαβάζει ως υψόμετρα).
    Τα κενά συμπληρώνονται με παρεμβολή· ό,τι μένει παίρνει το ελάχιστο υψόμετρο.
    """
    valid = np.isfinite(dem)
    filled = np.where(valid, dem, np.nanmin(dem)).astype("float32")
    if not valid.all():
        filled = fillnodata(filled, mask=valid.astype("uint8"),
                            max_search_distance=100, smoothing_iterations=0)
    with rasterio.open(
        path, "w", driver="GTiff", height=info["shape"][0], width=info["shape"][1],
        count=1, dtype="float32", crs=info["crs"], transform=info["transform"],
    ) as dst:
        dst.write(filled, 1)


def viewshed_union(dem_path, points, info):
    """Binary viewshed για κάθε οικισμό και ένωση (OR) των αποτελεσμάτων (GDAL)."""
    from osgeo import gdal  # lazy import: χρειάζεται μόνο εδώ

    gdal.UseExceptions()
    height, width = info["shape"]
    t = info["transform"]
    visible = np.zeros(info["shape"], dtype=bool)

    ds = gdal.Open(str(dem_path))
    band = ds.GetRasterBand(1)
    left, top = t.c, t.f
    right, bottom = left + t.a * width, top + t.e * height

    n = len(points)
    for k, (_, row) in enumerate(points.iterrows(), start=1):
        x, y = row.geometry.x, row.geometry.y
        if not (left <= x <= right and bottom <= y <= top):
            continue  # παρατηρητής εκτός DEM

        vs_name = f"/vsimem/viewshed_{k}.tif"
        vs = gdal.ViewshedGenerate(
            band, "GTiff", vs_name, [],
            x, y,
            float(row["observ_hgt"]), float(row["target_height"]),
            1, 0, 0, 0,          # ορατό, μη ορατό, εκτός εμβέλειας, nodata
            1.0,                 # χωρίς διόρθωση καμπυλότητας
            gdal.GVM_Edge,
            float(row["radius"]),
        )
        arr = vs.GetRasterBand(1).ReadAsArray()
        gt = vs.GetGeoTransform()
        vs = None
        gdal.Unlink(vs_name)

        col0 = int(round((gt[0] - t.c) / t.a))
        row0 = int(round((gt[3] - t.f) / t.e))
        r0, c0 = max(row0, 0), max(col0, 0)
        r1 = min(row0 + arr.shape[0], height)
        c1 = min(col0 + arr.shape[1], width)
        if r1 > r0 and c1 > c0:
            visible[r0:r1, c0:c1] |= arr[r0 - row0:r1 - row0, c0 - col0:c1 - col0] == 1

        if k % 50 == 0 or k == n:
            print(f"   viewshed: {k}/{n}")

    ds = None
    return visible


# ----------------------------------------------------------------------------
# Provenance & μεταδεδομένα
# ----------------------------------------------------------------------------
def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def file_group(path):
    """Το αρχείο μαζί με τα συνοδευτικά του (π.χ. .shp + .dbf + .shx + .prj)."""
    path = Path(path)
    return sorted(p for p in path.parent.glob(path.stem + ".*") if p.is_file())


def input_manifest(paths, base):
    manifest = {}
    for key, p in paths.items():
        manifest[key] = [
            {"file": str(f.relative_to(base)), "bytes": f.stat().st_size, "sha256": sha256(f)}
            for f in file_group(p)
        ]
    return manifest


def package_versions():
    out = {"python": platform.python_version(), "platform": platform.platform()}
    for pkg in ("numpy", "geopandas", "rasterio", "shapely", "pyproj", "pyogrio", "PyYAML", "GDAL"):
        try:
            out[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            pass
    try:
        from osgeo import gdal
        out["gdal_runtime"] = gdal.VersionInfo("RELEASE_NAME")
    except ImportError:
        pass
    return out


def git_info(base):
    try:
        kw = dict(cwd=base, stderr=subprocess.DEVNULL, text=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], **kw).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], **kw).strip())
        return {"commit": commit, "uncommitted_changes": dirty}
    except Exception:
        return None


def write_provenance(path, cfg, manifest, output_file, stats, started, seconds, base):
    prov = {
        "software": {"name": "xorothetisi_aiolikon", "version": __version__,
                     "git": git_info(base)},
        "run": {"started_utc": started.isoformat(timespec="seconds"),
                "duration_seconds": round(seconds, 1),
                "command": " ".join(sys.argv)},
        "environment": package_versions(),
        "parameters": {"region_name": cfg["region_name"], **cfg["parameters"]},
        "inputs": manifest,
        "outputs": {
            "file": str(output_file.relative_to(base)),
            "sha256": sha256(output_file),
            "bytes": output_file.stat().st_size,
            **stats,
        },
    }
    Path(path).write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")


def write_datapackage(path, cfg, output_file, stats, crs, base):
    meta = cfg.get("metadata", {})
    sources = [
        {"title": s.get("title"), "path": s.get("url"), "version": s.get("version"),
         "license": s.get("license"), "role": key}
        for key, s in meta.get("sources", {}).items()
    ]
    pkg = {
        "profile": "data-package",
        "name": "xorothetisi-aiolikon-output",
        "title": meta.get("title"),
        "description": meta.get("description"),
        "version": __version__,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "keywords": meta.get("keywords", []),
        "contributors": [
            {"title": a.get("name"), "role": "author", "path": a.get("orcid"),
             "organization": a.get("affiliation")}
            for a in meta.get("authors", [])
        ],
        "licenses": [{"name": meta.get("license_data", "CC-BY-4.0"),
                      "path": "https://creativecommons.org/licenses/by/4.0/"}],
        "sources": sources,
        "resources": [{
            "name": "xorothetisi_areas",
            "path": str(output_file.relative_to(base)),
            "format": "gpkg",
            "mediatype": "application/geopackage+sqlite3",
            "bytes": output_file.stat().st_size,
            "hash": f"sha256:{sha256(output_file)}",
            "crs": str(crs),
            "layers": ["xorothetisi_areas", "settlements_used"],
            "schema": {"fields": [
                {"name": "Allowed", "type": "integer",
                 "description": "1 = περιοχή που πληροί όλα τα κριτήρια χωροθέτησης"},
            ]},
            "statistics": stats,
        }],
    }
    Path(path).write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------------
# Κύρια ροή
# ----------------------------------------------------------------------------
def run(cfg, base):
    base = Path(base).resolve()
    started = datetime.now(timezone.utc)
    t0 = time.time()

    par = cfg["parameters"]
    inp = {k: base / v for k, v in cfg["inputs"].items()}
    output_file = base / cfg["output"]
    if output_file.suffix.lower() != ".gpkg":
        raise ValueError("Το output πρέπει να είναι GeoPackage (.gpkg).")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    region_name = cfg["region_name"]

    print("1/9 Ανάγνωση DEM")
    dem, info = read_dem(inp["dem"])
    if info["crs"] is None or info["crs"].is_geographic:
        raise ValueError("Το DEM πρέπει να έχει προβολικό ΣΑ σε μέτρα (π.χ. EPSG:2100).")

    print("2/9 Εξαγωγή Περιφερειακής Ενότητας")
    regions = gpd.read_file(inp["regional_units"]).to_crs(info["crs"])
    region = regions[regions[REGION_FIELD] == region_name]
    if region.empty:
        raise ValueError(f"Δεν βρέθηκε η ΠΕ '{region_name}' στο πεδίο {REGION_FIELD}.")

    print("3/9 Buffer και εξαγωγή οικισμών")
    buffer_gdf = gpd.GeoDataFrame(
        geometry=region.geometry.buffer(par["buffer_distance"], quad_segs=5), crs=region.crs)
    settlements = gpd.read_file(inp["settlements"]).to_crs(info["crs"])
    settlements = settlements[settlements.geometry.intersects(buffer_gdf.union_all())]
    settlements = settlements.reset_index(drop=True).copy()
    if not (settlements.geom_type == "Point").all():
        settlements["geometry"] = settlements.geometry.centroid
    settlements["observ_hgt"] = par["observer_height"]
    settlements["target_height"] = par["target_height"]
    settlements["radius"] = par["viewshed_radius"]
    settlements["ID"] = settlements.index
    print(f"   {len(settlements)} οικισμοί")

    print("4/9 Viewshed")
    with tempfile.TemporaryDirectory() as tmp:
        filled_path = os.path.join(tmp, "dem_filled.tif")
        write_filled_dem(dem, info, filled_path)
        visible = viewshed_union(filled_path, settlements, info)

    print("5/9 Rasterize περιοχών Natura")
    natura = gpd.read_file(inp["natura"]).to_crs(info["crs"])
    natura_mask = rasterize_mask(natura, info)

    print("6/9 Μη επιτρεπόμενες περιοχές")
    not_allowed = visible | natura_mask

    print("7/9 Άνεμος, κλίση, επιτρεπόμενες περιοχές")
    wind = reproject_to_dem_grid(inp["wind"], info)
    with np.errstate(invalid="ignore"):
        wind_ok = wind > par["min_wind_speed"]
        slope_ok = slope_degrees(dem, info["xres"], info["yres"]) < par["max_slope"]
    allowed = wind_ok & slope_ok

    print("8/9 Περιοχές χωροθέτησης και αποκοπή στα όρια της ΠΕ")
    siting = allowed & ~not_allowed & rasterize_mask(region, info)

    print("9/9 Μετατροπή σε πολύγωνα και αποθήκευση")
    polys = [
        {"geometry": geom, "properties": {"Allowed": int(val)}}
        for geom, val in features.shapes(
            siting.astype("uint8"), mask=siting, transform=info["transform"], connectivity=4)
    ]
    out = (gpd.GeoDataFrame.from_features(polys, crs=info["crs"]) if polys else
           gpd.GeoDataFrame({"Allowed": []}, geometry=[], crs=info["crs"]))

    if output_file.exists():
        output_file.unlink()
    out.to_file(output_file, layer="xorothetisi_areas", driver="GPKG")
    settlements.to_file(output_file, layer="settlements_used", driver="GPKG")

    stats = {
        "n_polygons": int(len(out)),
        "total_area_km2": round(float(out.area.sum()) / 1e6, 3),
        "n_settlements_used": int(len(settlements)),
    }
    out_dir = output_file.parent
    manifest = input_manifest(inp, base)
    write_provenance(out_dir / "provenance.json", cfg, manifest, output_file, stats,
                     started, time.time() - t0, base)
    write_datapackage(out_dir / "datapackage.json", cfg, output_file, stats, info["crs"], base)
    print(f"Έτοιμο: {stats['n_polygons']} πολύγωνα, {stats['total_area_km2']} km² -> {output_file}")
    return out


def main():
    ap = argparse.ArgumentParser(description="Χωροθέτηση περιοχών (αναπαραγώγιμη ροή)")
    ap.add_argument("--config", default="config.yaml", help="Αρχείο ρυθμίσεων YAML")
    args = ap.parse_args()
    cfg_path = Path(args.config).resolve()
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    run(cfg, cfg_path.parent)


if __name__ == "__main__":
    main()
