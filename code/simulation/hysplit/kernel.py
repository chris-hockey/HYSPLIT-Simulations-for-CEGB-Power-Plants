"""
Annual transport kernel for one plant-year (optionally one HEAT ensemble
member).

An `AnnualKernel` wraps the `HYSPLITRun` for a `PlantYear` and produces a
(lat, lon) annual kernel by aggregating the daily-mean concentration records
in the run's NetCDF output along the time axis.

`heat_w` / `member_tag` are passed straight through to `HYSPLITRun`: when
`heat_w` is not None the run applies plume rise and the kernel is written to a
member-tagged path with the heat recorded in its attributes. The daily records
themselves remain in `self.run.nc_path` for later monitor-level extraction;
this class only writes the annual mean used by the exposure pipeline.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

import xarray as xr

from .plant import PlantYear
from .run import HYSPLITRun
from .paths import RUNS_DIR, ANNUAL_DIR, NUMPAR, TAIL_HRS, SAMPLE_HRS


@dataclass
class AnnualKernel:
    """
    Annual transport kernel for one plant-year.

    Runs the continuous-release FY simulation (idempotent) and aggregates the
    daily concentration records to a (lat, lon) kernel, saved to NetCDF with
    fuel input stored as an attribute for downstream scaling.

    `heat_w`     sensible heat in watts (None = baseline, no plume rise).
    `member_tag` ensemble-member path suffix, e.g. "k4".
    `out_root`   if set, runs go to out_root/"runs" and kernels to
                 out_root/"kernels" (keeps the ensemble in its own subtree);
                 None uses the default RUNS_DIR / ANNUAL_DIR.
    """
    plant_year: PlantYear
    heat_w:     float | None = None
    member_tag: str | None = None
    out_root:   Path | None = None
    run: HYSPLITRun = field(init=False, repr=False)

    def __post_init__(self) -> None:
        runs_dir = (self.out_root / "runs") if self.out_root else RUNS_DIR
        self.run = HYSPLITRun(
            plant_year=self.plant_year,
            heat_w=self.heat_w,
            member_tag=self.member_tag,
            runs_dir=runs_dir,
        )

    @property
    def kernel_path(self) -> Path:
        annual_dir = (self.out_root /
                      "kernels") if self.out_root else ANNUAL_DIR
        annual_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"_{self.member_tag}" if self.member_tag else ""
        return (
            annual_dir
            / f"kernel_{self.plant_year.plant_id}"
              f"_{self.plant_year.year_maj}{suffix}.nc"
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

        return self._aggregate_and_save()

    def _aggregate_and_save(self) -> Path:
        ds = xr.open_dataset(self.run.nc_path)
        conc = ds["TEST"].isel(levels=0)        # (time, lat, lon)
        annual = conc.mean(dim="time")          # (lat, lon)
        n_time = int(conc.sizes["time"])

        py = self.plant_year
        result = xr.Dataset(
            {"transport_kernel": (["latitude", "longitude"], annual.values)},
            coords={
                "latitude":  conc["latitude"].values,
                "longitude": conc["longitude"].values,
            },
            attrs={
                "plant_id":        py.plant_id,
                "plant_name":      py.plant_name,
                "year_maj":        py.year_maj,
                "fuel_input_gwh":  py.fuel_input_gwh,
                "member_tag":      self.member_tag if self.member_tag else "",
                "heat_w":          self.heat_w if self.heat_w is not None else float("nan"),
                "n_daily_records": n_time,
                "emit_hrs":        self.run.emit_hrs,
                "run_hrs":         self.run.run_hrs,
                "tail_hrs":        TAIL_HRS,
                "sample_hrs":      SAMPLE_HRS,
                "numpar":          NUMPAR,
                "description": (
                    "Annual transport kernel: mean across the time axis of the "
                    "daily-mean concentration records from one continuous-release "
                    "HYSPLIT simulation covering the financial year (Apr year_maj "
                    "to Apr year_maj+1), plus a short tail for late-emitted "
                    "particles to clear the domain. Units are concentration per "
                    "unit emission; multiply by fuel input (stored here) for "
                    "plant-specific exposure. heat_w is the EMITIMES sensible "
                    "heat in watts for this ensemble member (NaN = baseline)."
                ),
            },
        )
        ds.close()
        result.to_netcdf(self.kernel_path)
        print(f"  annual kernel saved: {self.kernel_path.name}")
        return self.kernel_path
