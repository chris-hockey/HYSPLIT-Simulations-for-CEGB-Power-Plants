"""
Download ERA5 meteorological fields for HYSPLIT in monthly chunks, in
parallel and resumable.

Study period is FY 1974/75-1987/88 (Apr 1974 - Mar 1988); full calendar years
1973-1988 are pulled as a buffer, which resumability makes cheap.

Pressure-level fields (geopotential, temperature, U/V wind, vertical
velocity, relative humidity) on eight levels 700-1000 hPa, and single-level
surface fields (10m winds, 2m temperature, surface pressure, BLH, heat
fluxes, precipitation, cloud cover), 6-hourly on a box covering Britain. Plus
a single surface geopotential that is later used in the ARL conversions.

Written to data/raw/pressures and data/raw/singles as monthly GRIB files.
Downloads skip any target that already exists, so the script can be re-run
after interruption.

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cdsapi

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PRESSURE_DIR = RAW_DIR / "pressures"
SINGLES_DIR = RAW_DIR / "singles"
PRESSURE_DIR.mkdir(parents=True, exist_ok=True)
SINGLES_DIR.mkdir(parents=True, exist_ok=True)

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


# ==============================================================================

def fetch(dataset, base, year, month, target):
    """Download one month. Skips if file already exists and is non-empty."""
    if os.path.exists(target) and os.path.getsize(target) > 0:
        return f"SKIP {os.path.basename(target)}"
    req = {**base, "year": [str(year)], "month": [f"{month:02d}"]}
    cdsapi.Client().retrieve(dataset, req, target)
    return f"DONE {os.path.basename(target)}"


# Surface geopotential (terrain height): time-invariant, so one timestep is
# enough. era52arl needs it alongside the monthly surface fields. Skipped if
# the file is already present, so an existing copy is reused unchanged.
GEOPOT_DIR = RAW_DIR / "geopot"
GEOPOT_DIR.mkdir(parents=True, exist_ok=True)
GEOPOT_TARGET = GEOPOT_DIR / "geopot.grib"
if not (GEOPOT_TARGET.exists() and GEOPOT_TARGET.stat().st_size > 0):
    cdsapi.Client().retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": ["reanalysis"],
            "variable": ["geopotential"],
            "year": ["1981"], "month": ["01"], "day": ["01"], "time": ["00:00"],
            "data_format": "grib", "download_format": "unarchived",
            "area": AREA,
        },
        str(GEOPOT_TARGET),
    )

jobs = []
for y in YEARS:
    for m in MONTHS:
        tag = f"{y}_{m:02d}"
        jobs.append(("reanalysis-era5-pressure-levels", PL_BASE, y, m,
                     os.path.join(PRESSURE_DIR, f"era5_pl_{tag}.grib")))
        jobs.append(("reanalysis-era5-single-levels", SFC_BASE, y, m,
                     os.path.join(SINGLES_DIR,  f"era5_sfc_an_{tag}.grib")))

MAX_WORKERS = 12
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futures = [ex.submit(fetch, *j) for j in jobs]
    for f in as_completed(futures):
        try:
            print(f.result())
        except Exception as e:
            print(f"FAIL {e}")
