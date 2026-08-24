"""
Fix by Claude:

One-off recovery: build annual kernels from simulations that already ran.

`sim_run.py` completed the HYSPLIT simulation for the first tranche of
plant-years but failed at the kernel-writing step, because `kernels/annual/`
did not exist and netCDF4 reports a missing parent directory as
`PermissionError`. The cdumps and their NetCDF conversions are intact, so the
kernels can be built without re-running anything.

This script walks `RUNS_DIR`, and for every run directory holding a non-empty
NetCDF cdump, computes and saves the annual kernel via `AnnualKernel.execute()`.
HYSPLIT is not re-run: `HYSPLITRun.execute()` returns immediately when a
non-empty NetCDF already exists, so each job is a read, a mean over the time
axis, and a write.

Plant and year come from the run directory name, and the sensible heat from the
run's own EMITIMES file rather than the panel, so each kernel records the heat
HYSPLIT actually used. A run directory with no EMITIMES is a baseline run with
no plume rise and is skipped, as are ensemble directories carrying a member tag.

Intended to be run once, before resuming `sim_run.py`.

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code" / "simulation"))

from hysplit import AnnualKernel, PlantYear  # noqa: E402
from hysplit.paths import ANNUAL_DIR, RUNS_DIR  # noqa: E402


# ==============================================================================
# read back what the run actually used
# ==============================================================================

def parse_run_dir(run_dir: Path) -> tuple[str, int]:
    """
    `<plant_id>_<year_maj>` -> `(plant_id, year_maj)`. `rsplit` is safe for
    plant ids containing underscores.

    Raises `ValueError` if the trailing field is not a year, which is the case
    for ensemble directories tagged `_k<n>`.
    """
    plant_id, year_str = run_dir.name.rsplit("_", 1)
    return plant_id, int(year_str)


def emitimes_heat_w(emitimes_path: Path) -> float:
    """
    Sensible heat in watts from an EMITIMES file: the last field of its single
    data record, which is the value HYSPLIT read for this run.

    Raises `ValueError` if the last record does not parse as a heat value.
    """
    records = [
        ln for ln in emitimes_path.read_text().splitlines() if ln.strip()
    ]
    return float(records[-1].split()[-1])


# ==============================================================================
# backfill
# ==============================================================================

def main() -> None:
    ANNUAL_DIR.mkdir(parents=True, exist_ok=True)

    run_dirs = sorted(p for p in RUNS_DIR.iterdir() if p.is_dir())
    print(f"{len(run_dirs)} run directories under {RUNS_DIR}\n")

    n_built = n_done = n_nosim = n_skip = n_fail = 0
    t0 = time.time()

    for run_dir in run_dirs:
        try:
            plant_id, year_maj = parse_run_dir(run_dir)
        except ValueError:
            print(f"  SKIP     {run_dir.name}: not a production run directory")
            n_skip += 1
            continue

        # a run without EMITIMES had no plume rise; keep it out of the
        # production kernel set.
        emitimes = run_dir / "EMITIMES"
        if not emitimes.exists():
            print(f"  SKIP     {run_dir.name}: no EMITIMES (baseline run)")
            n_skip += 1
            continue

        try:
            heat_w = emitimes_heat_w(emitimes)
            py = PlantYear.from_panel(plant_id=plant_id, year_maj=year_maj)
            ak = AnnualKernel(plant_year=py, heat_w=heat_w)
        except (ValueError, IndexError, KeyError) as e:
            print(f"  FAIL     {run_dir.name}: {type(e).__name__}: {e}")
            n_fail += 1
            continue

        if ak.already_done():
            n_done += 1
            continue

        nc = ak.run.nc_path
        if not (nc.exists() and nc.stat().st_size > 0):
            print(f"  NO SIM   {run_dir.name}: no completed cdump NetCDF")
            n_nosim += 1
            continue

        try:
            ak.execute()
            n_built += 1
        except Exception as e:  # noqa: BLE001 - report and continue
            print(f"  FAIL     {run_dir.name}: {type(e).__name__}: {e}")
            n_fail += 1

    print(
        f"\ndone in {time.time() - t0:.0f}s: {n_built} kernels built, "
        f"{n_done} already present, {n_nosim} without a completed "
        f"simulation, {n_skip} skipped, {n_fail} failed"
    )
    print(f"kernels now in {ANNUAL_DIR}: "
          f"{len(list(ANNUAL_DIR.glob('kernel_*.nc')))}")


# ==============================================================================

if __name__ == "__main__":
    main()
