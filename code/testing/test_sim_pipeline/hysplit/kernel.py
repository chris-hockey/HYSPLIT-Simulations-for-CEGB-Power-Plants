"""
Annual transport kernel for one plant-year.

An `AnnualKernel` wraps the `HYSPLITRun` for a `PlantYear` and produces a
(lat, lon) annual kernel by summing the daily-mean concentration records in
the run's NetCDF output along the time axis.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

import xarray as xr

from .plant import PlantYear
from .run import HYSPLITRun
from .paths import ANNUAL_DIR, NUMPAR, TAIL_HRS, SAMPLE_HRS


@dataclass
class AnnualKernel:
    """
    Annual transport kernel for one plant-year.

    Runs the continuous-release FY simulation (idempotent) and sums the daily
    concentration records to produce a (lat, lon) kernel. The result is saved
    to NetCDF with fuel input stored as an attribute for downstream scaling.
    """
    plant_year: PlantYear
    run: HYSPLITRun = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.run = HYSPLITRun(
            plant=self.plant_year.plant,
            year_maj=self.plant_year.year_maj,
        )

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
        Run the FY simulation (if needed) and aggregate to an annual kernel.

        Raises:
            RuntimeError: if the HYSPLIT run or NetCDF conversion fails.
        """
        if self.already_done() and not overwrite:
            print(f"Annual kernel exists, skipping: {self.kernel_path.name}")
            return self.kernel_path

        print(f"--- {self.run.tag} ---")
        self.run.execute()
        print(f"  simulation complete: {self.run.nc_path.name}")

        return self._sum_and_save()

    def _sum_and_save(self) -> Path:
        ds = xr.open_dataset(self.run.nc_path)
        conc = ds["TEST"].isel(levels=0)        # (time, lat, lon)
        annual = conc.sum(dim="time")          # (lat, lon)
        n_time = int(conc.sizes["time"])

        result = xr.Dataset(
            {"transport_kernel": (["latitude", "longitude"], annual.values)},
            coords={
                "latitude":  conc["latitude"].values,
                "longitude": conc["longitude"].values,
            },
            attrs={
                "plant_id":        self.plant_year.plant.plant_id,
                "plant_name":      self.plant_year.plant.plant_name,
                "year_maj":        self.plant_year.year_maj,
                "fuel_input_gwh":  self.plant_year.fuel_input_gwh,
                "n_daily_records": n_time,
                "emit_hrs":        self.run.emit_hrs,
                "run_hrs":         self.run.run_hrs,
                "tail_hrs":        TAIL_HRS,
                "sample_hrs":      SAMPLE_HRS,
                "numpar":          NUMPAR,
                "description": (
                    "Annual transport kernel. Sum along the time axis of the "
                    "daily-mean concentration records from one continuous-"
                    "release HYSPLIT simulation covering the financial year "
                    "(Apr year_maj to Apr year_maj+1), plus a short tail for "
                    "late-emitted particles to clear the domain. Units are "
                    "concentration per unit emission; multiply by fuel input "
                    "(stored here) for plant-specific exposure."
                ),
            },
        )
        ds.close()
        result.to_netcdf(self.kernel_path)
        print(f"  annual kernel saved: {self.kernel_path.name}")
        return self.kernel_path
