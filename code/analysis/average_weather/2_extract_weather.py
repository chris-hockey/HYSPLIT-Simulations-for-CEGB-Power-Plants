"""
Extract and crop ERA5 weather fields to the England domain, for the
meteorological representativeness check.

Reads the merged GRIB files from 1_merge_grib.sh and writes three NetCDF
files: instantaneous surface fields (boundary-layer height, 2m temperature,
10m winds), total precipitation, and 925 hPa temperature and wind components.
Precipitation is read separately because accumulated variables carry a
different temporal structure in the ERA5 GRIB than instantaneous ones.

The 925 hPa level (~750-800 m) is retained as the level at which plume-rise
typically places the plume centreline.

Written to data/final/merged_weather/, the input to 3_plot_weather.py.

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

import logging
import time
from pathlib import Path

import xarray as xr

PROJECT_ROOT = Path(__file__).resolve().parents[3]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
main_start_time = time.time()


# ==============================================================================

WEST = -7.25
EAST = 2.75
SOUTH = 49.00
NORTH = 56.50

SINGLE_GRIB = PROJECT_ROOT / "data" / "intermediate" / "all_singles.grib"
PRESSURE_GRIB = PROJECT_ROOT / "data" / "intermediate" / "pressure_925_tuv.grib"
OUT_DIR = Path(PROJECT_ROOT / "data" / "final" / "merged_weather")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def size_mb(path: Path) -> float:
    """Return file size in MB."""
    return path.stat().st_size / 1024**2


# ==============================================================================
# surface instantaneous variables:
# (accumulated variables such as total precipitation are stored with a different
# temporal structure in the ERA5 GRIB and are therefore read separately)
# ==============================================================================

out = OUT_DIR / "instant_singles.nc"
start = time.perf_counter()
log.info(
    "Processing instantaneous surface variables from %s (%.1f MB)",
    SINGLE_GRIB.name,
    size_mb(SINGLE_GRIB),
)


instant = xr.open_dataset(
    SINGLE_GRIB,
    engine="cfgrib",
    backend_kwargs={
        "filter_by_keys": {
            "stepType": "instant",
        },
    },
)
instant = instant.sel(
    longitude=slice(WEST, EAST),
    latitude=slice(NORTH, SOUTH),
)
# retain only boundary layer height, temp, wind vectors
instant = instant[
    ["blh", "t2m", "u10", "v10",]
]

instant.to_netcdf(out)

log.info(
    "Created %s (%.1f MB) in %.1f seconds",
    out.name,
    size_mb(out),
    time.perf_counter() - start,
)


# ==============================================================================
# total precip separately:
# ==============================================================================

out = OUT_DIR / "total_precip.nc"
start = time.perf_counter()

log.info(
    "Processing total precipitation from %s (%.1f MB)",
    SINGLE_GRIB.name,
    size_mb(SINGLE_GRIB),
)


tp = xr.open_dataset(
    SINGLE_GRIB,
    engine="cfgrib",
    backend_kwargs={
        "filter_by_keys": {
            "shortName": "tp",
        },
    },
)
tp = tp.sel(
    longitude=slice(WEST, EAST),
    latitude=slice(NORTH, SOUTH),
)

tp.to_netcdf(out)

log.info(
    "Created %s (%.1f MB) in %.1f seconds",
    out.name,
    size_mb(out),
    time.perf_counter() - start,
)


# ==============================================================================
# 925 hPa pressure-level meteorology:
# already just retained the temp and wind vector components just the pressure
# level 925 hPa (lower troposphere, ~750-800metres up, where the majority of
# plume rise takes the plume centreline to), so just crop
# ==============================================================================

out = OUT_DIR / "pressure_925_tuv.nc"
start = time.perf_counter()

log.info(
    "Processing 925 hPa meteorology from %s (%.1f MB)",
    PRESSURE_GRIB.name,
    size_mb(PRESSURE_GRIB),
)


pres = xr.open_dataset(
    PRESSURE_GRIB,
    engine="cfgrib")

pres = pres.sel(
    longitude=slice(WEST, EAST),
    latitude=slice(NORTH, SOUTH),
)

pres.to_netcdf(out)

log.info(
    "Created %s (%.1f MB) in %.1f seconds",
    out.name,
    size_mb(out),
    time.perf_counter() - start,
)


# ==============================================================================

main_end_time = time.time()
log.info("Weather extraction complete. Total run time: %.2f seconds",
         main_end_time - main_start_time)
