"""
One HYSPLIT concentration simulation per plant financial year (1 April t -
31 March t+1).

Each `HYSPLITRun` emits continuously at unit rate from 00Z 1 April of
`plant_year.year_maj` to 00Z 1 April `plant_year.year_maj + 1`, then
tracks particles for `TAIL_HRS` more hours so the final cohort can clear
the domain.

Output is sampled every `SAMPLE_HRS` (24h), producing one NetCDF file
with ~365 daily-mean concentrations.

HEAT ensemble:
'heat_w' is the sensible heat in watts (from the panel's precomputed 
'heat_w_k{m}' column). When it is not None, that heat is injected via an 
EMITIMES file at unit release rate so HYSPLIT applies Briggs plume rise
(PLRISE=1) above the physical stack; `member_tag` (e.g. "k4") suffixes the run/
kernel paths to keep members apart. Only the EMITIMES `Heat` value differs
between members - CONTROL grid, met, tracer, release rate, duration and sampling
are identical. `heat_w = 0.0` is a valid member (k1): EMITIMES with zero heat
means no plume rise.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .paths import (
    ARL_DIR,
    CON2CDF4,
    GRID_CENTRE,
    GRID_SPACING,
    GRID_SPAN,
    HYCS_STD,
    MAXPAR,
    NUMPAR,
    OUTPUT_HT_M,
    RUNS_DIR,
    SAMPLE_HRS,
    TAIL_HRS,
)
from .plant import PlantYear

# HYSPLIT compilation limit for the 1-grid-N-files CONTROL format.
_MAX_FILES_PER_GRID = 128


def _arl_filename(year: int, month: int) -> str:
    return f"era5_{year}_{month:02d}.arl"


def _fy_bounds(year_maj: int) -> tuple[datetime, datetime]:
    """Financial year as 1 Apr year_maj 00Z, 1 Apr year_maj+1 00Z."""
    return datetime(year_maj, 4, 1), datetime(year_maj + 1, 4, 1)


def _fy_emit_hours(year_maj: int) -> int:
    """Hours in the FY (8760, or 8784 if spanning a leap Feb)."""
    start, end = _fy_bounds(year_maj)
    return int((end - start).total_seconds() // 3600)


def _months_covering(start: datetime, hours: int) -> list[tuple[int, int]]:
    """(year, month) pairs for each calendar month touched by [start, start+hours]."""
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
    One HYSPLIT concentration simulation covering a full Apr-Mar financial
    year.

    Emits continuously at unit rate from 00Z on 1 April
    `plant_year.year_maj` through 00Z on 1 April `plant_year.year_maj + 1`,
    then tracks `TAIL_HRS` more hours. Produces one cdump file with ~365
    daily-mean concentration records.

    `heat_w`     sensible heat in watts (None = baseline, no EMITIMES/plume rise).
    `member_tag` path suffix identifying the ensemble member, e.g. "k4".
    """
    plant_year: PlantYear
    heat_w:     float | None = None
    member_tag: str | None = None
    runs_dir:   Path = RUNS_DIR   # output root for this run's directory
    cdump_path: Path = field(init=False, repr=False)
    nc_path:    Path = field(init=False, repr=False)
    run_dir:    Path = field(init=False, repr=False)
    emit_hrs:   int = field(init=False, repr=False)
    run_hrs:    int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        py = self.plant_year
        self.emit_hrs = _fy_emit_hours(py.year_maj)
        self.run_hrs = self.emit_hrs + TAIL_HRS

        suffix = f"_{self.member_tag}" if self.member_tag else ""
        self.run_dir = self.runs_dir / f"{py.plant_id}_{py.year_maj}{suffix}"
        base = f"cdump_{py.plant_id}_{py.year_maj}{suffix}"
        self.cdump_path = self.run_dir / base
        self.nc_path = self.cdump_path.with_suffix(".nc")

    @property
    def _use_emitimes(self) -> bool:
        # A heat value (including 0.0) means emit via EMITIMES with plume rise
        # active; None means the original CONTROL-driven baseline.
        return self.heat_w is not None

    # config writers:
    def _write_setup_cfg(self) -> None:
        lines = [
            "&SETUP",
            f"NUMPAR = {NUMPAR},",
            f"MAXPAR = {MAXPAR},",
            "INITD = 0,",
            "KHMAX = 9999,",
            "DELT = 0.0,",
            "KDEF = 0,",
            "KBLS = 2,",
        ]
        if self._use_emitimes:
            # Briggs plume rise, driven by the EMITIMES Heat column.
            lines += ["PLRISE = 1,", "EFILE = 'EMITIMES',"]
        lines.append("/")   # single closing slash, AFTER PLRISE/EFILE
        (self.run_dir / "SETUP.CFG").write_text("\n".join(lines) + "\n")

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

    def _write_emitimes(self) -> None:
        """
        Continuous unit-rate release for the whole FY, carrying sensible heat.

        One source, one pollutant -> one data record. `Hgt` is the physical
        stack height (Briggs rise is added on top); `Rate` is a unit mass rate
        (1.0) so mass is injected into the buoyant plume; `Heat` is in watts.
        The release duration is packed as HHmm (hours then two-digit minutes),
        and the cycle-header duration covers the full run (emission + tail) so
        the cycle never expires mid-simulation.
        """
        py = self.plant_year
        start, _ = _fy_bounds(py.year_maj)
        yy, mm, dd, hh = start.year, start.month, start.day, start.hour

        dur_hhmm = f"{self.emit_hrs:d}00"          # e.g. 8760 h -> "876000"
        cycle_valid_hrs = self.run_hrs             # covers emission + tail

        lines = [
            "YYYY MM DD HH    DURATION(HHHH) #RECORDS",
            "YYYY MM DD HH MM DURATION(HHMM) LAT LON HGT(m) RATE(/h) AREA(m2) HEAT(W)",
            f"{yy:04d} {mm:02d} {dd:02d} {hh:02d} {cycle_valid_hrs:d} 1",
            (
                f"{yy:04d} {mm:02d} {dd:02d} {hh:02d} 00 {dur_hhmm} "
                f"{py.lat:.4f} {py.lon:.4f} {py.stack_ht_m:.1f} "
                f"1.0 0.0 {self.heat_w:.1f}"
            ),
        ]
        (self.run_dir / "EMITIMES").write_text("\n".join(lines) + "\n")

    def _write_control(self) -> None:
        py = self.plant_year
        start, _ = _fy_bounds(py.year_maj)
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
                f"{n_files} ARL files needed for FY{py.year_maj}, "
                f"exceeds HYSPLIT compilation limit of "
                f"{_MAX_FILES_PER_GRID} per grid."
            )
        grid_header = f"1 {n_files}"
        met_block = "\n".join(
            f"{ARL_DIR}/\n{_arl_filename(y, m)}"
            for y, m in months
        )

        # With EMITIMES, the CONTROL emission rate AND duration are zeroed so
        # the two mechanisms do not double-count; the EMITIMES record supplies
        # the actual (unit) release. Baseline runs emit from CONTROL directly.
        emit_rate = "0.0" if self._use_emitimes else "1.0"
        emit_dur = "0" if self._use_emitimes else f"{self.emit_hrs}"

        lines = [
            f"{yy:02d} {mm:02d} {dd:02d} {hh:02d}",
            "1",
            f"{py.lat} {py.lon} {py.stack_ht_m}",
            f"{self.run_hrs}",
            "0",
            "10000.0",
            grid_header,
            met_block,
            "1",
            "TEST",
            emit_rate,                                  # emission rate
            emit_dur,                                   # release hours
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
            f"00 {SAMPLE_HRS:02d} 00",                  # daily averages
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
        if self._use_emitimes:
            self._write_emitimes()

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
        py = self.plant_year
        yy_next = (py.year_maj + 1) % 100
        member = f" [{self.member_tag}]" if self.member_tag else ""
        return f"{py.plant_id} FY{py.year_maj}/{yy_next:02d}{member}"
