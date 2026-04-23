"""
One HYSPLIT concentration simulation per plant financial year (1 April t - 31
March t+1).

Each HYSPLITRun emits continuously at unit rate from 00Z 1 April of 'year_maj'
to 00Z of 1 April of 'year_maj' + 1, then tracks particle for 'TAIL_HRS" more
hours so the final corhort (particles released towards the end of the year) can
clear the domain.

Output sampled every 'SAMPLE_HRS' (24 hrs), overall producing 1 NetCDF file
containing ~365 daily-mean concentrations.
"""
from __future__ import annotations
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    NUMPAR,
    MAXPAR,
    TAIL_HRS,
    SAMPLE_HRS,
    RUNS_DIR,
)

# HYSPLIT compilation limit for the 1-grid-N-files CONTROL format.
_MAX_FILES_PER_GRID = 128


def _arl_filename(year: int, month: int) -> str:
    return f"era5_{year}_{month:02d}.arl"


def _fy_bounds(year_maj: int) -> tuple[datetime, datetime]:
    """Financial year as 1 Apr year_maj 00Z, 1 Apr year_maj+1 00Z"""
    return datetime(year_maj, 4, 1), datetime(year_maj + 1, 4, 1)


def _fy_emit_hours(year_maj: int) -> int:
    """Hours in the FY (8760, or 8784 if spanning a leap Feb)."""
    start, end = _fy_bounds(year_maj)
    return int((end - start).total_seconds() // 3600)


def _months_covering(start: datetime, hours: int) -> list[tuple[int, int]]:
    """(year, month) pairs for each calendar month touched by [start, start+hours]"""
    end = start + timedelta(hours=hours)
    months: list[tuple[int, int]] = []
    cur = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while cur <= end:
        months.append((cur.year, cur.month))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


@dataclass
class HYSPLITRun:
    """
    One HYSPLIT concentration simulation covering a full Apr-Mar financial year.

    Emits continuously at unit rate from 00Z on 1 April `year_maj` through
    00Z on 1 April `year_maj + 1`, then tracks TAIL_HRS more hours.
    Produces one cdump file with ~365 daily-mean concentration records.
    """
    plant:      Plant
    year_maj:   int
    cdump_path: Path = field(init=False, repr=False)
    nc_path:    Path = field(init=False, repr=False)
    run_dir:    Path = field(init=False, repr=False)
    emit_hrs:   int = field(init=False, repr=False)
    run_hrs:    int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.emit_hrs = _fy_emit_hours(self.year_maj)
        self.run_hrs = self.emit_hrs + TAIL_HRS

        self.run_dir = RUNS_DIR / f"{self.plant.plant_id}_{self.year_maj}"
        tag = f"cdump_{self.plant.plant_id}_{self.year_maj}"
        self.cdump_path = self.run_dir / tag
        self.nc_path = self.cdump_path.with_suffix(".nc")

    # config writers:
    def _write_setup_cfg(self) -> None:
        (self.run_dir / "SETUP.CFG").write_text(
            "&SETUP\n"
            f"NUMPAR = {NUMPAR},\n"
            f"MAXPAR = {MAXPAR},\n"
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
        start, _ = _fy_bounds(self.year_maj)
        yy, mm, dd, hh = start.year % 100, start.month, start.day, start.hour

        months = _months_covering(start, self.run_hrs)
        n_files = len(months)

        # An FY run needs ~13 ARL files; the default (one-number) CONTROL
        # format caps at 12, producing "DEFGRID limit" at runtime. The two-
        # number form declares "1 grid, n_files files" and raises the
        # per-grid cap to 128. All files share the same ARL_DIR, but the
        # format still requires one (dir, filename) pair per file.
        if n_files > _MAX_FILES_PER_GRID:
            raise RuntimeError(
                f"{n_files} ARL files needed for FY{self.year_maj}, "
                f"exceeds HYSPLIT compilation limit of "
                f"{_MAX_FILES_PER_GRID} per grid."
            )
        grid_header = f"1 {n_files}"
        met_block = "\n".join(
            f"{ARL_DIR}/\n{_arl_filename(y, m)}"
            for y, m in months
        )

        lines = [
            f"{yy:02d} {mm:02d} {dd:02d} {hh:02d}",
            "1",
            f"{self.plant.lat} {self.plant.lon} {self.plant.stack_ht_m}",
            f"{self.run_hrs}",
            "0",
            "10000.0",
            grid_header,
            met_block,
            "1",
            "TEST",
            "1.0",                                      # unit emission rate
            # continuous release, full FY
            f"{self.emit_hrs}",
            f"{yy:02d} {mm:02d} {dd:02d} {hh:02d} 00",  # emission start
            "1",
            f"{GRID_CENTRE[0]} {GRID_CENTRE[1]}",
            f"{GRID_SPACING[0]} {GRID_SPACING[1]}",
            f"{GRID_SPAN[0]} {GRID_SPAN[1]}",
            f"{self.run_dir}/",
            self.cdump_path.name,
            "1",
            f"{OUTPUT_HT_M}",
            "00 00 00 00 00",                           # sample start = sim start
            "00 00 00 00 00",                           # sample stop  = sim end
            # daily averages, daily output
            f"00 {SAMPLE_HRS:02d} 00",
            "1",
            "0.0 0.0 0.0",
            "0.0 0.0 0.0 0.0 0.0",
            "0.0 0.0 0.0",
            "0.0",
            "0.0",
        ]
        (self.run_dir / "CONTROL").write_text("\n".join(lines) + "\n")

    # execution:
    def execute(self) -> None:
        """
        Write config files, run hycs_std, and convert cdump to NetCDF.
        Idempotent: returns immediately if the NetCDF already exists
        and is non-empty.
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
        yy_next = (self.year_maj + 1) % 100
        return f"{self.plant.plant_id} FY{self.year_maj}/{yy_next:02d}"
