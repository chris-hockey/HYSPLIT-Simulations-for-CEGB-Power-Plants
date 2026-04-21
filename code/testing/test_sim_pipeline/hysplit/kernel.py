from __future__ import annotations
import calendar
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import xarray as xr

from .plant import Plant, PlantYear
from .run import HYSPLITRun
from .paths import MONTHLY_DIR, ANNUAL_DIR


def _execute_run(run: HYSPLITRun) -> Path:
    """
    Top-level function for parallel execution.
    ProcessPoolExecutor requires picklable callables — bound methods
    are not picklable, so this wraps HYSPLITRun.execute().
    Returns nc_path on success, raises on failure.
    """
    run.execute()
    return run.nc_path


@dataclass
class MonthlyKernel:
    """
    All daily runs for one plant x calendar month.
    Averages daily 72-hour kernels into one monthly kernel NetCDF.
    Aborts on any failure.
    """
    plant:    Plant
    year_maj: int
    year:     int
    month:    int
    runs:     list[HYSPLITRun] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        n_days = calendar.monthrange(self.year, self.month)[1]
        self.runs = [
            HYSPLITRun(
                plant=self.plant,
                year_maj=self.year_maj,
                year=self.year,
                month=self.month,
                day=d,
            )
            for d in range(1, n_days + 1)
        ]

    @property
    def kernel_path(self) -> Path:
        MONTHLY_DIR.mkdir(parents=True, exist_ok=True)
        return (
            MONTHLY_DIR
            / f"kernel_{self.plant.plant_id}"
              f"_{self.year}{self.month:02d}.nc"
        )

    def already_done(self) -> bool:
        return self.kernel_path.exists()

    def execute(self, overwrite: bool = False) -> Path:
        if self.already_done() and not overwrite:
            print(
                f"  Monthly kernel exists, skipping: {self.kernel_path.name}")
            return self.kernel_path

        nc_paths_by_day = {}
        failed_run = None

        with ProcessPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(_execute_run, run): run
                for run in self.runs
            }
            for future in as_completed(futures):
                run = futures[future]
                try:
                    nc_path = future.result()
                    nc_paths_by_day[run.day] = nc_path
                    print(f"  {run.tag} ok")
                except Exception as e:
                    failed_run = (run, e)
                    # cancel remaining queued jobs
                    for f in futures:
                        f.cancel()
                    break

        if failed_run:
            run, e = failed_run
            raise RuntimeError(
                f"HYSPLIT failed for {run.tag}\n"
                f"Check log: {run.run_dir / 'run.log'}\n"
                f"Error: {e}"
            )

        # sort by day to ensure consistent ordering before averaging
        nc_paths = [nc_paths_by_day[d] for d in sorted(nc_paths_by_day)]
        return self._average_and_save(nc_paths)

    def _average_and_save(self, nc_paths: list[Path]) -> Path:
        grids = []
        for nc in nc_paths:
            ds = xr.open_dataset(nc)
            arr = ds["TEST"].isel(levels=0, time=0).values
            grids.append(arr)
            ds.close()

        kernel = np.stack(grids, axis=0).sum(axis=0)  # (lat, lon)

        ds_ref = xr.open_dataset(nc_paths[-1])
        conc = ds_ref["TEST"].isel(levels=0, time=0)

        result = xr.Dataset(
            {"transport_kernel": (["latitude", "longitude"], kernel)},
            coords={
                "latitude":  conc.latitude.values,
                "longitude": conc.longitude.values,
            },
            attrs={
                "plant_id":    self.plant.plant_id,
                "plant_name":  self.plant.plant_name,
                "year":        self.year,
                "month":       self.month,
                "n_days":      len(nc_paths),
                "run_hrs":     72,
                "emit_hrs":    24,
                "description": (
                    "Monthly average transport kernel. Mean 72-hour "
                    "concentration from a unit 24-hour release, "
                    "averaged across all days in the month."
                ),
            },
        )
        ds_ref.close()
        result.to_netcdf(self.kernel_path)
        print(f"  Monthly kernel saved: {self.kernel_path.name}")
        return self.kernel_path


@dataclass
class AnnualKernel:
    """
    Annual transport kernel for one plant-year.
    Runs 12 MonthlyKernels (April year_maj through March year_maj+1),
    averages them into one annual kernel NetCDF.
    Aborts on any failure.
    """
    plant_year:      PlantYear
    monthly_kernels: list[MonthlyKernel] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.monthly_kernels = [
            MonthlyKernel(
                plant=self.plant_year.plant,
                year_maj=self.plant_year.year_maj,
                year=cal_year,
                month=cal_month,
            )
            for cal_year, cal_month in self.plant_year.calendar_months()
        ]

    @property
    def kernel_path(self) -> Path:
        ANNUAL_DIR.mkdir(parents=True, exist_ok=True)
        return (
            ANNUAL_DIR
            / f"kernel_{self.plant_year.plant.plant_id}"
              f"_{self.plant_year.year_maj}.nc"
        )

    def already_done(self) -> bool:
        return self.kernel_path.exists()

    def execute(self, overwrite: bool = False) -> Path:
        """
        Run all 12 monthly kernels and average into annual kernel.
        Raises RuntimeError on any failure — nothing is saved partially.
        Returns annual kernel path.
        """
        if self.already_done() and not overwrite:
            print(f"Annual kernel exists, skipping: {self.kernel_path.name}")
            return self.kernel_path

        monthly_paths = []
        for mk in self.monthly_kernels:
            print(
                f"\n--- "
                f"{self.plant_year.plant.plant_id} "
                f"{mk.year}-{mk.month:02d} ---"
            )
            path = mk.execute(overwrite=overwrite)
            monthly_paths.append(path)

        return self._average_and_save(monthly_paths)

    def _average_and_save(self, monthly_paths: list[Path]) -> Path:
        grids = []
        for mp in monthly_paths:
            ds = xr.open_dataset(mp)
            arr = ds["transport_kernel"].values
            grids.append(arr)
            ds.close()

        annual = np.stack(grids, axis=0).sum(axis=0)  # (lat, lon)

        ds_ref = xr.open_dataset(monthly_paths[-1])

        result = xr.Dataset(
            {"transport_kernel": (["latitude", "longitude"], annual)},
            coords={
                "latitude":  ds_ref["transport_kernel"].latitude.values,
                "longitude": ds_ref["transport_kernel"].longitude.values,
            },
            attrs={
                "plant_id":       self.plant_year.plant.plant_id,
                "plant_name":     self.plant_year.plant.plant_name,
                "year_maj":       self.plant_year.year_maj,
                "fuel_input_gwh": self.plant_year.fuel_input_gwh,
                "n_months":       len(monthly_paths),
                "run_hrs":        72,
                "emit_hrs":       24,
                "description": (
                    "Annual average transport kernel. Mean of 12 monthly "
                    "kernels, April year_maj through March year_maj+1. "
                    "Fuel input stored as attribute for downstream scaling."
                ),
            },
        )
        ds_ref.close()
        result.to_netcdf(self.kernel_path)
        print(f"\nAnnual kernel saved: {self.kernel_path}")
        return self.kernel_path
