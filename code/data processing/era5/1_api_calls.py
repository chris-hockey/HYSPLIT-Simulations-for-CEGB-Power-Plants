"""
Download ERA5 pressure-level and single-level fields for HYSPLIT,
monthly chunks, parallel, resumable.

Study period: FY 1974/75 - 1987/88 (Apr 1974 - Mar 1988).
Pulls full calendar years 1973-1988 as buffer; resumability makes
the over-pull cheap.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import cdsapi

ROOT = "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/raw"
PRESSURE_DIR = os.path.join(ROOT, "pressures")
SINGLES_DIR = os.path.join(ROOT, "singles")
os.makedirs(PRESSURE_DIR, exist_ok=True)
os.makedirs(SINGLES_DIR,  exist_ok=True)

YEARS = range(1973, 1989)
MONTHS = range(1, 13)

AREA = [61.0, -12.0, 47.0, 8.0]       # N, W, S, E
DAYS = [f"{d:02d}" for d in range(1, 32)]
TIMES = ["00:00", "06:00", "12:00", "18:00"]

PL_BASE = {
    "product_type": ["reanalysis"],
    "variable": [
        "geopotential",
        "temperature",
        "u_component_of_wind",
        "v_component_of_wind",
        "vertical_velocity",
        "relative_humidity",
    ],
    "pressure_level": ["700", "850", "875", "900", "925", "950", "975", "1000"],
    "day": DAYS, "time": TIMES,
    "data_format": "grib", "download_format": "unarchived",
    "area": AREA,
}

SFC_BASE = {
    "product_type": ["reanalysis"],
    "variable": [
        "10m_u_component_of_wind",
        "10m_v_component_of_wind",
        "2m_temperature",
        "surface_pressure",
        "total_precipitation",
        "surface_latent_heat_flux",
        "surface_sensible_heat_flux",
        "total_cloud_cover",
        "boundary_layer_height",
    ],
    "day": DAYS, "time": TIMES,
    "data_format": "grib", "download_format": "unarchived",
    "area": AREA,
}


def fetch(dataset, base, year, month, target):
    """Download one month. Skips if file already exists and is non-empty."""
    if os.path.exists(target) and os.path.getsize(target) > 0:
        return f"SKIP {os.path.basename(target)}"
    req = {**base, "year": [str(year)], "month": [f"{month:02d}"]}
    cdsapi.Client().retrieve(dataset, req, target)
    return f"DONE {os.path.basename(target)}"


jobs = []
for y in YEARS:
    for m in MONTHS:
        tag = f"{y}_{m:02d}"
        jobs.append(("reanalysis-era5-pressure-levels", PL_BASE, y, m,
                     os.path.join(PRESSURE_DIR, f"era5_pl_{tag}.grib")))
        jobs.append(("reanalysis-era5-single-levels", SFC_BASE, y, m,
                     os.path.join(SINGLES_DIR,  f"era5_sfc_an_{tag}.grib")))

MAX_WORKERS = 11
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futures = [ex.submit(fetch, *j) for j in jobs]
    for f in as_completed(futures):
        try:
            print(f.result())
        except Exception as e:
            print(f"FAIL {e}")
