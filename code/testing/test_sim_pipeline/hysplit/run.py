"""
Utilities for configuring and running daily HYSPLIT concentration simulations.

This module defines helper functions for ARL file handling and date logic, and
provides the `HYSPLITRun` class, which represents a single daily simulation for
a given plant and date. A `HYSPLITRun` can write the required HYSPLIT config
files, execute `hycs_std`, and convert the resulting concentration output to
NetCDF.
"""

from __future__ import annotations
import calendar
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .plant import Plant
from .paths import (
    HYCS_STD,
    CON2CDF4,
    ARL_DIR,
    GRID_CENTRE,
    GRID_SPACING,
    GRID_SPAN,
    OUTPUT_HT_M,
    RUN_HRS,
    EMIT_HRS,
    RUNS_DIR,
)


def _arl_filename(year: int, month: int) -> str:
    return f"era5_{year}_{month:02d}.arl"


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _spills_into_next_month(day: int, year: int, month: int) -> bool:
    """True if a RUN_HRS run starting at day 00Z crosses into next month."""
    n_days = calendar.monthrange(year, month)[1]
    return (day - 1) * 24 + RUN_HRS > n_days * 24


@dataclass
class HYSPLITRun:
    """
    One daily HYSPLIT concentration simulation.

    Releases emissions for EMIT_HRS hours from 00Z on (year, month, day),
    tracks for RUN_HRS hours total. Produces one concentration record.
    """
    plant:    Plant
    year_maj: int      # for directory naming only
    year:     int      # calendar year
    month:    int      # calendar month
    day:      int
    cdump_path: Path = field(init=False, repr=False)
    nc_path:    Path = field(init=False, repr=False)
    run_dir:    Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.run_dir = (
            RUNS_DIR
            / f"{self.plant.plant_id}_{self.year_maj}"
            / f"{self.month:02d}"
            / f"day_{self.day:02d}"
        )
        tag = (
            f"cdump_{self.plant.plant_id}"
            f"_{self.year}{self.month:02d}"
            f"_d{self.day:02d}"
        )
        self.cdump_path = self.run_dir / tag
        self.nc_path = self.cdump_path.with_suffix(".nc")

    # ------------------------------------------------------------------
    # config writers
    # ------------------------------------------------------------------

    def _write_setup_cfg(self) -> None:
        (self.run_dir / "SETUP.CFG").write_text(
            "&SETUP\n"
            "NUMPAR = 10000,\n"
            "MAXPAR = 10000,\n"
            "INITD = 0,\n"
            "KHMAX = 9999,\n"
            "DELT = 0.0,\n"
            "KDEF = 1,\n"
            "/\n"
        )
        bdyfiles = (
            Path.home()
            / "opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/bdyfiles"
        )
        (self.run_dir / "ASCDATA.CFG").write_text(
            "-90.0  -180.0  lat/lon of lower left corner (last record in file)\n"
            "1.0     1.0    lat/lon spacing in degrees between data points\n"
            "180     360    lat/lon number of data points\n"
            "2              default land use category\n"
            "0.2            default roughness length (meters)\n"
            f"'{bdyfiles}/' directory location of data files\n"
        )

    def _write_control(self) -> None:
        yy = self.year % 100

        if _spills_into_next_month(self.day, self.year, self.month):
            ny, nm = _next_month(self.year, self.month)
            n_met = 2
            met_block = (
                f"{ARL_DIR}/\n{_arl_filename(self.year, self.month)}\n"
                f"{ARL_DIR}/\n{_arl_filename(ny, nm)}\n"
            )
        else:
            n_met = 1
            met_block = (
                f"{ARL_DIR}/\n{_arl_filename(self.year, self.month)}\n"
            )

        lines = [
            f"{yy:02d} {self.month:02d} {self.day:02d} 00",
            "1",
            f"{self.plant.lat} {self.plant.lon} {self.plant.stack_ht_m}",
            f"{RUN_HRS}",
            "0",
            "10000.0",
            f"{n_met}",
            met_block.rstrip("\n"),
            "1",
            "TEST",
            "1.0",
            f"{EMIT_HRS}",
            f"{yy:02d} {self.month:02d} {self.day:02d} 00 00",
            "1",
            f"{GRID_CENTRE[0]} {GRID_CENTRE[1]}",
            f"{GRID_SPACING[0]} {GRID_SPACING[1]}",
            f"{GRID_SPAN[0]} {GRID_SPAN[1]}",
            f"{self.run_dir}/",
            self.cdump_path.name,
            "1",
            f"{OUTPUT_HT_M}",
            "00 00 00 00 00",
            "00 00 00 00 00",
            f"00 {RUN_HRS:02d} 00",
            "1",
            "0.0 0.0 0.0",
            "0.0 0.0 0.0 0.0 0.0",
            "0.0 0.0 0.0",
            "0.0",
            "0.0",
        ]
        (self.run_dir / "CONTROL").write_text("\n".join(lines) + "\n")

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------

    def execute(self) -> None:
        """
        Write HYSPLIT config files, run `hycs_std`, and convert the output to NetCDF.

        Idempotent: if the NetCDF output already exists and is non-empty,
        returns without re-running. Safe to call on resume after a failed
        monthly kernel.

        Raises:
            RuntimeError: If the HYSPLIT run or NetCDF conversion fails.
        """
        if self.nc_path.exists() and self.nc_path.stat().st_size > 0:
            return

        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._write_setup_cfg()
        self._write_control()

        log_path = self.run_dir / "run.log"
        with open(log_path, "w") as log:
            subprocess.run(
                [str(HYCS_STD)],
                cwd=self.run_dir,
                stdout=log,
                stderr=log,
            )

        if "Complete Hysplit" not in log_path.read_text():
            raise RuntimeError(
                f"HYSPLIT failed for {self.tag}\n"
                f"Check log: {log_path}"
            )

        try:
            subprocess.run(
                [str(CON2CDF4), str(self.cdump_path), str(self.nc_path)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"con2cdf4 failed for {self.tag}\n"
                f"Check log: {log_path}"
            ) from e

    @property
    def tag(self) -> str:
        return (
            f"{self.plant.plant_id} "
            f"{self.year}-{self.month:02d}-{self.day:02d}"
        )
