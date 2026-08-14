"""
Assign treatment to pollution monitoring stations at daily, monthly and annual
frequencies
"""
from __future__ import annotations

import logging
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "simulation"))

from hysplit.paths import ENSEMBLE_RUNS_DIR  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ==============================================================================
# cdump_<plantid>_k<n>.nc
PANEL_PATH = Path(PROJECT_ROOT / "data" / "final" / "cegb_panel_with_stacks")
STATIONS_PATH = Path(PROJECT_ROOT / "data" / "intermediate" /
                     "pollution_stations" / " smokeso2_daily.csv")
OUT_DIR = Path(PROJECT_ROOT / "data" / "final" / "pollution_stations")

YEAR_MAJ = 1981
SAMPLE_HRS = 24
MAX_WORKERS = 6          # process pool size; 1 = serial
FUELS = ("coal", "oil", "gt")

# ==============================================================================
# Station -> grid cell (identical containment logic to HYSPLITWeights)
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
    grid's *original* axes (lat axis may be stored descending). Deliberately
    identical to HYSPLITWeights._build_cell_map so daily and annual exposure
    share the same cell assignment.
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
# Daily cdump -> clean-dated grid (end-stamp + 2-digit-century corrections)
# ==============================================================================


def load_daily_grid(
    cdump_nc: Path,
    year_maj: int,
    sample_hrs: int = SAMPLE_HRS,
) -> xr.DataArray:
    """
    Open a daily cdump and return TEST(date, latitude, longitude) on a clean
    calendar-date axis, restricted to the financial year (the ~72h tail is
    dropped). con2cdf4 stamps the window END and CONTROL's 2-digit year can put
    the century wrong; both are corrected. See subannual_kernels for the same
    logic with a written-out kernel.
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
# File-name -> (plant_id, year_maj, member_tag)
# ==============================================================================
_CDUMP_RE = re.compile(r"^cdump_(?P<plant>.+)_(?P<year>\d{4})_(?P<k>k\d+)$")


def parse_cdump_name(cdump_nc: Path) -> tuple[str, int, str]:
    """cdump_<plant>_<year>_k<n>.nc -> (plant_id, year_maj, 'k<n>')."""
    m = _CDUMP_RE.match(cdump_nc.stem)
    if not m:
        raise ValueError(f"unrecognised cdump name: {cdump_nc.name}")
    return m["plant"], int(m["year"]), m["k"]


# ==============================================================================
# Worker: sample one cdump at the stations and return its daily contribution
#
# The cell map, FY axis and run parameters are process-global (set once per
# worker by _init_worker) so they are not re-pickled for every job.
# ==============================================================================
_G: dict = {}


def _init_worker(lat_idx, lon_idx, in_domain, year_maj, sample_hrs, fy_start, n_days):
    _G.update(
        lat_idx=lat_idx, lon_idx=lon_idx, in_domain=in_domain,
        year_maj=year_maj, sample_hrs=sample_hrs,
        fy_start=fy_start, n_days=n_days, n_st=len(lat_idx),
    )


def _sample_one(job: tuple[str, str, str, float]):
    """(cdump_path, member, fuel, fuel_input) -> (member, fuel, contrib[float32])
    where contrib is (n_days, n_st) = f_input * concentration at each station."""
    cdump, member, fuel, f_input = job
    try:
        da = load_daily_grid(cdump, _G["year_maj"], _G["sample_hrs"])
        samp = da.values[:, _G["lat_idx"],
                         _G["lon_idx"]]        # (days, station)
        samp = np.where(_G["in_domain"][None, :], samp, 0.0)
        # drop negatives
        np.clip(samp, 0.0, None, out=samp)

        day_vals = da["date"].values.astype("datetime64[D]")
        rows = (day_vals - _G["fy_start"]
                ).astype("timedelta64[D]").astype(np.int64)

        contrib = np.zeros((_G["n_days"], _G["n_st"]), dtype=np.float32)
        contrib[rows] = (samp * f_input).astype(np.float32)
        return member, fuel, contrib
    except Exception as e:                                        # noqa: BLE001
        return "ERR", Path(cdump).name, f"{type(e).__name__}: {e}"

# ==============================================================================
# Build the panels
# ==============================================================================


def build_station_exposure(
    ENSEMBLE_RUNS_DIR: Path = ENSEMBLE_RUNS_DIR,
    panel_path: Path = PANEL_PATH,
    stations_path: Path = STATIONS_PATH,
    year_maj: int = YEAR_MAJ,
    max_workers: int = MAX_WORKERS,
) -> dict[str, pd.DataFrame]:
    """
    Stream every ensemble cdump for `year_maj` into daily/monthly/annual
    station-exposure panels. Returns {"daily", "monthly", "annual"} DataFrames.

    Sampling each cdump is independent work, so files are dispatched to a
    ProcessPoolExecutor; the station->cell map is built once and shared with
    workers via an initializer, and the parent sums the returned contributions.
    Numerically identical to a serial run (summation is associative); set
    max_workers=1 to force serial.
    """
    # plant lookup: (plant_id) -> fuel_cat, fuel_input_gwh, for this FY
    panel = pd.read_csv(panel_path)
    lut = (
        panel[panel["year_maj"] == year_maj]
        .drop_duplicates("plant_id")
        .set_index("plant_id")[["fuel_cat", "fuel_input_gwh"]]
    )

    # stations: unique (station_id, lon, lat)
    st = (
        pd.read_csv(stations_path)[["station_id", "lon", "lat"]]
        .drop_duplicates("station_id")
        .dropna(subset=["lon", "lat"])
        .sort_values("station_id")
        .reset_index(drop=True)
    )
    station_ids = st["station_id"].to_numpy()
    n_st = len(station_ids)

    # canonical financial-year day axis
    fy_dates = pd.date_range(
        f"{year_maj}-04-01", f"{year_maj + 1}-03-31", freq="D")
    n_days = len(fy_dates)
    fy_start = np.datetime64(f"{year_maj}-04-01")

    # cell map (built once from the first cdump's grid)
    cdumps = sorted(ENSEMBLE_RUNS_DIR.glob(
        f"*_{year_maj}_k*/cdump_*_{year_maj}_k*.nc"))
    if not cdumps:
        raise FileNotFoundError(
            f"no ensemble cdumps under {ENSEMBLE_RUNS_DIR} for FY{year_maj}")
    with xr.open_dataset(cdumps[0]) as ds0:
        grid_lats = ds0["latitude"].values
        grid_lons = ds0["longitude"].values
    lat_idx, lon_idx, in_domain = map_points_to_cells(
        st["lon"].to_numpy(), st["lat"].to_numpy(), grid_lats, grid_lons
    )
    log.info("%d stations, %d/%d inside domain",
             n_st, int(in_domain.sum()), n_st)

    # job list: parse name + panel lookup (no file reads yet)
    jobs: list[tuple[str, str, str, float]] = []
    n_skip = 0
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
        jobs.append((str(cdump), mtag, fuel, float(
            lut.at[plant, "fuel_input_gwh"])))

    log.info("dispatching %d cdumps across %d workers (%d skipped)",
             len(jobs), max_workers, n_skip)

    # dispatch + reduce
    acc: dict[tuple[str, str], np.ndarray] = {}
    n_ok = n_fail = 0
    init_args = (lat_idx, lon_idx, in_domain, year_maj,
                 SAMPLE_HRS, fy_start, n_days)
    with ProcessPoolExecutor(
        max_workers=max_workers, initializer=_init_worker, initargs=init_args
    ) as ex:
        futs = [ex.submit(_sample_one, job) for job in jobs]
        for fut in as_completed(futs):
            member, fuel, payload = fut.result()
            if member == "ERR":
                n_fail += 1
                # fuel=name, payload=msg
                log.warning("FAIL %s: %s", fuel, payload)
                continue
            key = (member, fuel)
            if key not in acc:
                # float64 accumulator
                acc[key] = np.zeros((n_days, n_st))
            acc[key] += payload
            n_ok += 1
            if n_ok % 50 == 0:
                log.info("  %d/%d cdumps summed", n_ok, len(jobs))

    log.info("summed %d cdumps (%d failed, %d skipped)", n_ok, n_fail, n_skip)

    # assemble the wide daily panel (all 3x7 columns, 0 where a fuel is absent)
    members = sorted({m for m, _ in acc}, key=lambda t: int(t[1:]))
    e_cols = [f"e_{fuel}_{m}" for m in members for fuel in FUELS]
    daily = pd.DataFrame(
        {"station_id": np.repeat(station_ids, n_days),
         "date": np.tile(fy_dates.values, n_st)}
    )
    for col in e_cols:
        _, fuel, m = col.split("_")
        arr = acc.get((m, fuel))
        # station-major
        daily[col] = (arr.T.reshape(-1) if arr is not None else 0.0)

    # monthly and annual are means of the daily panel
    daily["ym"] = pd.DatetimeIndex(
        daily["date"]).year * 100 + pd.DatetimeIndex(daily["date"]).month
    monthly = daily.groupby(["station_id", "ym"], as_index=False)[
        e_cols].mean()
    annual = daily.groupby("station_id", as_index=False)[e_cols].mean()
    annual["year_maj"] = year_maj

    daily = daily.drop(columns="ym")
    return {"daily": daily, "monthly": monthly, "annual": annual}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panels = build_station_exposure()
    for name, df in panels.items():
        out = OUT_DIR / f"station_hysplit_{name}.csv"
        df.to_csv(out, index=False)
        log.info("saved %s  (%d rows, %d cols)",
                 out.name, len(df), df.shape[1])


if __name__ == "__main__":
    main()
