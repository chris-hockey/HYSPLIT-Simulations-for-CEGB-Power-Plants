"""
Monthly transport kernels from the daily-sampled FY simulations.

`AnnualKernel._aggregate_and_save` collapses each run's ~365 daily-mean
records with `conc.mean("time")`, so the annual kernels have no time axis
and cannot be split back into months. This script recovers the monthly
resolution straight from the source: it re-reads the daily NetCDF written
by each `HYSPLITRun` and averages the daily records within each
financial-year month, producing 12 monthly-mean (lat, lon) kernels per
plant-year -- the c_{jsm} needed before applying a sub-annual emission
weight.

Source : RUNS_DIR/<plant>_<year>/cdump_<plant>_<year>.nc  (daily run
         output; the annual step does not delete it).
Output : MONTHLY_DIR/monthly_<plant>_<year>.nc, one dataset per
         plant-year with a `month` dimension (int YYYYMM, April->March)
         and fuel input carried as an attribute for downstream scaling.
         Idempotent: existing outputs are skipped.

Downstream: E_smt = sum_j c_{jsm} * f_{jt} * w_{mt}. Multiply
`transport_kernel` by the plant's `fuel_input_gwh` (attr) and a monthly
emission weight w keyed on `month`, then sum over months. Keep these as
monthly MEANS -- do not sum daily grids -- so the month-length factor
cancels and the product is a well-defined dose (see chat derivation).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from hysplit import PlantYear, HYSPLITRun
from hysplit.paths import RUNS_DIR, MONTHLY_DIR, SAMPLE_HRS

# con2cdf4 stamps each record with its sampling-window END time (matching
# hysplitdata's `ending_datetime`). Shifting back half a window puts the
# label on the window midpoint, so each daily record is assigned to the
# calendar month it actually covers -- not the month its end tips into
# (e.g. the 30 Apr -> 1 May window ends in May but belongs to April).
# If inspection shows the coord is the window START, negate this offset.
_MID_OFFSET = np.timedelta64(SAMPLE_HRS // 2, "h")


def monthly_kernel_path(plant_id: str, year_maj: int) -> Path:
    MONTHLY_DIR.mkdir(parents=True, exist_ok=True)
    return MONTHLY_DIR / f"monthly_{plant_id}_{year_maj}.nc"


def _parse_run_dir(run_dir: Path) -> tuple[str, int]:
    """'<plant_id>_<year_maj>' -> (plant_id, year_maj). rsplit is safe
    for plant_ids that themselves contain underscores."""
    plant_id, year_str = run_dir.name.rsplit("_", 1)
    return plant_id, int(year_str)


def build_monthly_kernel(
    plant_year: PlantYear,
    overwrite: bool = False,
) -> Path:
    """Aggregate one plant-year's daily run NetCDF to 12 monthly-mean
    kernels and save. Returns the output path."""
    out_path = monthly_kernel_path(plant_year.plant_id, plant_year.year_maj)
    if out_path.exists() and not overwrite:
        print(f"exists, skipping: {out_path.name}")
        return out_path

    daily_nc = HYSPLITRun(plant_year=plant_year).nc_path
    if not daily_nc.exists():
        raise FileNotFoundError(
            f"daily run output missing: {daily_nc}. Re-run the simulation "
            f"for {plant_year.plant_id} FY{plant_year.year_maj}."
        )

    ds = xr.open_dataset(daily_nc)
    # (time, lat, lon), per unit emission
    conc = ds["TEST"].isel(levels=0)

    # Assign each daily record to a calendar month via its window midpoint.
    # HYSPLIT's CONTROL uses a 2-digit start year, so con2cdf4 can resolve the
    # wrong century (e.g. FY1973 is stamped 2073). Month, day, and record
    # order are correct; only the year is shifted by a constant. Recover the
    # true calendar year from the known FY start so month assignment is
    # century-proof, and so the opening April (year_maj) stays distinct from
    # the ~72h tail April (year_maj+1).
    mid = conc["time"] - _MID_OFFSET
    stamped_year = mid.dt.year.values
    year_shift = int(stamped_year.min()) - plant_year.year_maj
    yyyymm = ((stamped_year - year_shift) * 100
              + mid.dt.month.values).astype("int64")
    conc = conc.assign_coords(yyyymm=("time", yyyymm))

    # The 12 financial-year months in chronological (April->March) order.
    # As YYYYMM ints these already sort chronologically, matching groupby's
    # ascending order; the ~72h tail spills into April of year_maj+1, whose
    # YYYYMM is outside this list and is therefore dropped.
    fy_months = [y * 100 + m for (y, m) in plant_year.calendar_months()]

    monthly = conc.groupby("yyyymm").mean("time")
    present = [m for m in fy_months if m in monthly["yyyymm"].values]
    missing = [m for m in fy_months if m not in present]
    if missing:
        print(f"  WARN {plant_year.plant_id} FY{plant_year.year_maj}: "
              f"no records for {missing}")
    if not present:
        raise ValueError(
            f"{plant_year.plant_id} FY{plant_year.year_maj}: no FY months "
            f"matched the daily records (year_shift={year_shift}); daily "
            f"YYYYMM seen e.g. {sorted(set(yyyymm.tolist()))[:3]}. "
            f"Check the time-stamp convention in the source NetCDF."
        )
    monthly = monthly.sel(yyyymm=present)

    # Records per retained month -- a truncated run shows up as a short month.
    counts = pd.Series(yyyymm).value_counts()
    n_records = np.array([int(counts.get(m, 0)) for m in present])

    ds.close()

    result = xr.Dataset(
        {"transport_kernel": (["month", "latitude", "longitude"],
                              monthly.values)},
        coords={
            "month":     present,
            "latitude":  conc["latitude"].values,
            "longitude": conc["longitude"].values,
            "n_records": ("month", n_records),
        },
        attrs={
            "plant_id":       plant_year.plant_id,
            "plant_name":     plant_year.plant_name,
            "year_maj":       plant_year.year_maj,
            "fuel_input_gwh": plant_year.fuel_input_gwh,
            "sample_hrs":     SAMPLE_HRS,
            "month_format":   "int YYYYMM; financial year April year_maj to March year_maj+1",
            "description": (
                "Monthly-mean transport kernels: for each financial-year "
                "month, the mean over that month's daily-mean concentration "
                "records from the continuous unit-emission FY simulation. "
                "Units are concentration per unit emission rate; multiply by "
                "fuel_input_gwh and a monthly emission weight, then sum over "
                "months, for a sub-annual exposure measure."
            ),
        },
    )
    result.to_netcdf(out_path)
    print(f"saved {out_path.name}  (months={len(present)}, "
          f"records {n_records.min()}-{n_records.max()})")
    return out_path


def main(overwrite: bool = False) -> None:
    run_dirs = sorted(p for p in RUNS_DIR.iterdir() if p.is_dir())
    if not run_dirs:
        print(f"no run directories under {RUNS_DIR}")
        return

    n_ok = n_skip = n_fail = 0
    for run_dir in run_dirs:
        try:
            plant_id, year_maj = _parse_run_dir(run_dir)
            py = PlantYear.from_panel(plant_id=plant_id, year_maj=year_maj)
            existed = monthly_kernel_path(plant_id, year_maj).exists()
            build_monthly_kernel(py, overwrite=overwrite)
            n_skip += existed and not overwrite
            n_ok += not (existed and not overwrite)
        except Exception as e:
            n_fail += 1
            print(f"  FAIL {run_dir.name}: {type(e).__name__}: {e}")

    print(f"\ndone: {n_ok} built, {n_skip} skipped, {n_fail} failed")


if __name__ == "__main__":
    main()
