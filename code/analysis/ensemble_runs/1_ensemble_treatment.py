"""
Assign HYSPLIT ensemble exposure to pollution monitoring stations at monthly
intervals for the calibration exercise.

Reads the FY`YEAR_MAJ` ensemble cdumps under `ENSEMBLE_RUNS_DIR` (one per plant 
per member), maps each monitoring station to the 0.05° grid cell containing it, 
and takes each plant's monthly mean concentration at that cell. Exposure is the 
fuel-input-scaled sum of these across plants, formed separately for each fuel 
type (coal, oil, gas turbine) and each ensemble member k1-k7, giving 21 exposure
columns `e_{fuel}_{member}`, as described in the paper and technical appendix.

The result is merged onto the observed monthly SO2 and black smoke panel
(`data/raw/smokeso2_monthly.csv`) and written to
`data/final/ensemble_stations.csv`, one row per station-month, which is the
input to `ensemble_assessment.py`.

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "simulation"))

from hysplit.paths import ENSEMBLE_RUNS_DIR  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


main_start_time = time.time()


# ==============================================================================

CEGB_DATA = Path(PROJECT_ROOT / "data" / "final" /
                 "cegb_panel_with_stacks.csv")
POLLUTION_DATA = Path(PROJECT_ROOT / "data" / "raw" /
                      "smokeso2_monthly.csv")

OUT_DIR = Path(PROJECT_ROOT / "data" / "final")

YEAR_MAJ = 1981  # year of power plant output to scale by
SAMPLE_HRS = 24
FUELS = ("coal", "oil", "gt")


# ==============================================================================
# assign pollution montitoring station to it's nearest pollution grid cell
# ==============================================================================

def map_points_to_cells(
    lons: np.ndarray,
    lats: np.ndarray,
    grid_lats: np.ndarray,
    grid_lons: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Assign each (lon, lat) point to the 0.05° grid cell whose bounding box
    contains it. Returns (lat_idx, lon_idx, in_domain), index arrays into the
    grid's *original* axes (lat axis may be stored descending). Identical to
    HYSPLITWeights._build_cell_map in the main replication package.
    """
    lats_asc = np.sort(grid_lats)
    lons_asc = np.sort(grid_lons)
    lat_step = float(lats_asc[1] - lats_asc[0])
    lon_step = float(lons_asc[1] - lons_asc[0])
    lat_edges = np.append(lats_asc - lat_step / 2.0,
                          lats_asc[-1] + lat_step / 2.0)
    lon_edges = np.append(lons_asc - lon_step / 2.0,
                          lons_asc[-1] + lon_step / 2.0)

    lat_idx_asc = np.searchsorted(lat_edges, lats, side="right") - 1
    lon_idx_asc = np.searchsorted(lon_edges, lons, side="right") - 1

    in_domain = (
        (lat_idx_asc >= 0) & (lat_idx_asc < len(grid_lats))
        & (lon_idx_asc >= 0) & (lon_idx_asc < len(grid_lons))
    )
    if grid_lats[0] > grid_lats[-1]:                    # descending lat axis
        lat_idx = np.where(in_domain, len(grid_lats) - 1 - lat_idx_asc, 0)
    else:
        lat_idx = np.where(in_domain, lat_idx_asc, 0)
    lon_idx = np.where(in_domain, lon_idx_asc, 0)
    return lat_idx, lon_idx, in_domain


# ==============================================================================
# daily cdump -> clean-dated grid (end-stamp + 2-digit-century corrections)
# ==============================================================================

def load_daily_grid(
    cdump_nc: Path,
    year_maj: int,
    sample_hrs: int = SAMPLE_HRS,
) -> xr.DataArray:
    """
    Open a daily cdump and return TEST(date, latitude, longitude) on a clean
    calendar-date axis, restricted to the financial year (the ~72h tail is
    dropped). 

    TEST is the name of the tracer particle concentration simulated by
    HYSPLIT. HYSPLIT's con2cdf4 tool (used to process the simulation's output)
    stamps the window END and CONTROL's 2-digit year can put the century wrong
    therefore both are corrected.
    """
    ds = xr.open_dataset(Path(cdump_nc))
    conc = ds["TEST"].isel(levels=0)

    mid = conc["time"] - np.timedelta64(sample_hrs // 2, "h")
    stamped_year = mid.dt.year.values
    year_shift = int(stamped_year.min()) - year_maj
    dates = pd.to_datetime({
        "year":  stamped_year - year_shift,
        "month": mid.dt.month.values,
        "day":   mid.dt.day.values,
    }).values.astype("datetime64[D]")

    conc = conc.rename({"time": "date"}).assign_coords(
        date=("date", dates)).load()
    ds.close()

    start = np.datetime64(f"{year_maj:04d}-04-01")
    end = np.datetime64(f"{year_maj + 1:04d}-04-01")
    keep = (conc["date"].values >= start) & (conc["date"].values < end)
    return conc.isel(date=np.flatnonzero(keep))


# ==============================================================================
# file-name -> (plant_id, year_maj, member_tag)
# ==============================================================================

_CDUMP_RE = re.compile(r"^cdump_(?P<plant>.+)_(?P<year>\d{4})_(?P<k>k\d+)$")


def parse_cdump_name(cdump_nc: Path) -> tuple[str, int, str]:
    """
    cdump_<plant>_<year>_k<n>.nc -> (plant_id, year_maj, 'k<n>').
    """
    m = _CDUMP_RE.match(cdump_nc.stem)
    if not m:
        raise ValueError(f"unrecognised cdump name: {cdump_nc.name}")
    return m["plant"], int(m["year"]), m["k"]


# ==============================================================================
# assignment of treatment to pollution monitoring stations from ensemble run
# ==============================================================================

# monthly pollution panel: supplies universe of monitoring stations and the
# target to merge to
obs = pd.read_csv(POLLUTION_DATA)
obs = obs.loc[obs["year_maj"] == YEAR_MAJ]

# create plant lookup: plantid -> fuel_cat, fuel_input_gwh
panel = pd.read_csv(CEGB_DATA)
lut = (
    panel[panel["year_maj"] == YEAR_MAJ]
    .set_index("plant_id")[["fuel_cat", "fuel_input_gwh"]]
)

# unique stations
st = (
    obs[["station_id", "lon", "lat"]]
    .drop_duplicates("station_id")
    .sort_values("station_id")
    .reset_index(drop=True)
)
station_ids = st["station_id"].to_numpy()
n_st = len(station_ids)

# days per calendar month in the FY (row = month - 1)
fy_days = pd.date_range(f"{YEAR_MAJ}-04-01",
                        f"{YEAR_MAJ + 1}-03-31", freq="D")
days_in_month = np.bincount(fy_days.month.values - 1, minlength=12)

# cell map (built once from the first cdump's grid)
cdumps = sorted(ENSEMBLE_RUNS_DIR.glob(
    f"*_{YEAR_MAJ}_k*/cdump_*_{YEAR_MAJ}_k*.nc"))
if not cdumps:
    raise FileNotFoundError(
        f"no ensemble cdumps under {ENSEMBLE_RUNS_DIR} for FY{YEAR_MAJ}")
with xr.open_dataset(cdumps[0]) as ds0:
    grid_lats = ds0["latitude"].values
    grid_lons = ds0["longitude"].values
lat_idx, lon_idx, in_domain = map_points_to_cells(
    st["lon"].to_numpy(), st["lat"].to_numpy(), grid_lats, grid_lons
)
log.info("%d stations, %d/%d inside domain",
         n_st, int(in_domain.sum()), n_st)

# exposure = sum over plants of f_input * (the plant's monthly mean
# concentration at the station's cell)
acc: dict[tuple[str, str], np.ndarray] = {}
n_ok = n_skip = 0
for cdump in cdumps:
    plant, yr, mtag = parse_cdump_name(cdump)
    if plant not in lut.index:
        log.warning("no panel row for %s FY%d; skipping %s",
                    plant, yr, cdump.name)
        n_skip += 1
        continue
    fuel = str(lut.at[plant, "fuel_cat"])
    if fuel not in FUELS:
        log.warning("plant %s fuel_cat=%r not in %s; skipping",
                    plant, fuel, FUELS)
        n_skip += 1
        continue
    f_input = float(lut.at[plant, "fuel_input_gwh"])

    da = load_daily_grid(cdump, YEAR_MAJ, SAMPLE_HRS)
    samp = da.values[:, lat_idx, lon_idx]  # (days, station)
    samp = np.where(in_domain[None, :], samp, 0.0)
    # drop negatives
    np.clip(samp, 0.0, None, out=samp)

    mrow = pd.DatetimeIndex(da["date"].values).month.values - 1
    mmean = np.zeros((12, n_st))
    np.add.at(mmean, mrow, samp)
    mmean /= days_in_month[:, None]  # this plant's monthly mean conc

    key = (mtag, fuel)
    if key not in acc:
        acc[key] = np.zeros((12, n_st))
    acc[key] += f_input * mmean

    n_ok += 1
    if n_ok % 50 == 0:
        log.info("  %d/%d cdumps summed", n_ok, len(cdumps))

log.info("summed %d cdumps (%d skipped)", n_ok, n_skip)


# assemble the monthly panel; all 3x7 columns, 0 where a fuel is absent (should
# not happen)
members = sorted({m for m, _ in acc}, key=lambda t: int(t[1:]))
e_cols = [f"e_{fuel}_{m}" for m in members for fuel in FUELS]
monthly = pd.DataFrame({
    "station_id": np.repeat(station_ids, 12),
    "year_maj": YEAR_MAJ,
    "month_of_year": np.tile(np.arange(1, 13), n_st),
})
for col in e_cols:
    _, fuel, m = col.split("_")
    arr = acc.get((m, fuel))
    # station-major
    monthly[col] = (arr.T.reshape(-1) if arr is not None else 0.0)

# left join onto the pollution panel
merged = obs.merge(
    monthly, on=["station_id", "year_maj", "month_of_year"],
    how="left", validate="m:1",
)
n_na = int(merged[e_cols[0]].isna().sum())
if n_na:
    log.warning("%d/%d observed rows have no exposure match",
                n_na, len(merged))

OUT_DIR.mkdir(parents=True, exist_ok=True)
merged.to_csv(OUT_DIR / "ensemble_stations.csv", index=False)
log.info("saved %s  (%d rows, %d cols)",
         OUT_DIR.name, len(merged), merged.shape[1])

# ==============================================================================
main_end_time = time.time()
log.info("Total run time: %.1f seconds", main_end_time - main_start_time)
