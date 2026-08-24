"""
Annual transport kernel for one plant-year (or optionally one HEAT ensemble
member, which is used in the HEAT ensemble exercise).

An `AnnualKernel` wraps the `HYSPLITRun` for a `PlantYear` and produces a
(lat, lon) annual kernel by taking the mean of the daily-mean concentration
records in the run's NetCDF output along the time axis.

`execute()` runs the FY simulation via `HYSPLITRun` (idempotent) and computes
the kernel; `already_done()` reports whether the kernel already exists.
Kernels are written to `ANNUAL_DIR`, or to `out_root/"kernels"` when an
`out_root` is given.

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import xarray as xr

from .paths import ANNUAL_DIR, NUMPAR, RUNS_DIR, SAMPLE_HRS, TAIL_HRS
from .plant import PlantYear
from .run import HYSPLITRun


# ==============================================================================

@dataclass
class AnnualKernel:
    """
    Annual transport kernel for one plant-year.

    Runs the continuous-release FY simulation (idempotent) and takes the mean
    of the daily concentration records over time, giving a (lat, lon) kernel
    saved to NetCDF with fuel input stored as an attribute for downstream
    scaling.

    `heat_w`: sensible heat in watts (None = baseline, no plume rise).
    `member_tag`: ensemble-member path suffix, e.g. "k4" (useful in the
                  ensemble exercise).
    `out_root`: if set, runs go to out_root/"runs" and kernels to
                out_root/"kernels" (keeps the ensemble in its own subtree);
                None uses the default RUNS_DIR / ANNUAL_DIR.
    """
    plant_year: PlantYear
    heat_w: float | None = None
    member_tag: str | None = None
    out_root: Path | None = None
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
        annual_dir = (
            (self.out_root / "kernels") if self.out_root else ANNUAL_DIR
        )
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
        Run the FY simulation (if needed) and compute the annual kernel.

        `overwrite` recomputes the kernel from an existing simulation; the
        simulation itself is separately idempotent and is not re-run.

        Raises `RuntimeError` if the HYSPLIT log does not report
        "Complete Hysplit", or if `con2cdf4` exits non-zero.
        """
        if self.already_done() and not overwrite:
            print(f"Annual kernel exists, skipping: {self.kernel_path.name}")
            return self.kernel_path

        print(f"--- {self.run.tag} ---")
        self.run.execute()
        print(f"  simulation complete: {self.run.nc_path.name}")

        return self._compute_and_save()

    def _compute_and_save(self) -> Path:
        ds = xr.open_dataset(self.run.nc_path)
        conc = ds["TEST"].isel(levels=0)  # (time, lat, lon)
        annual = conc.mean(dim="time")  # (lat, lon)
        n_time = int(conc.sizes["time"])

        py = self.plant_year
        result = xr.Dataset(
            {"transport_kernel": (["latitude", "longitude"], annual.values)},
            coords={
                "latitude":  conc["latitude"].values,
                "longitude": conc["longitude"].values,
            },
            attrs={
                "plant_id": py.plant_id,
                "plant_name": py.plant_name,
                "year_maj": py.year_maj,
                "fuel_input_gwh": py.fuel_input_gwh,
                "member_tag": self.member_tag if self.member_tag else "",
                "heat_w": (
                    self.heat_w if self.heat_w is not None else float("nan")
                ),
                "n_daily_records": n_time,
                "emit_hrs": self.run.emit_hrs,
                "run_hrs": self.run.run_hrs,
                "tail_hrs": TAIL_HRS,
                "sample_hrs": SAMPLE_HRS,
                "numpar": NUMPAR,
                "description": (
                    "Annual transport kernel: mean across the time axis of "
                    "the daily-mean concentration records from one "
                    "continuous-release HYSPLIT simulation covering the "
                    "financial year (Apr year_maj to Apr year_maj+1), plus "
                    "a short tail (see tail_hrs) for late-emitted particles "
                    "to clear the domain. Units are concentration per unit "
                    "emission; multiply by fuel input (stored here) for "
                    "plant-specific exposure. heat_w is the EMITIMES "
                    "sensible heat in watts for this ensemble member "
                    "(NaN = baseline)."
                ),
            },
        )
        ds.close()
        self.kernel_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_netcdf(self.kernel_path)
        print(f"  annual kernel saved: {self.kernel_path.name}")
        return self.kernel_path
