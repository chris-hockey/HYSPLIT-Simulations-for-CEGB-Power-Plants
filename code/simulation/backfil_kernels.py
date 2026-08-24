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

Every kernel in `ANNUAL_DIR` is then validated (see `validate_kernels`), and the
script exits non-zero if any check fails.

Lives alongside `sim_run.py` in `code/simulation/` so it picks up the `hysplit`
package the same way. Intended to be run once, before resuming `sim_run.py`.

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import xarray as xr

from hysplit import AnnualKernel, PlantYear
from hysplit.paths import ANNUAL_DIR, ENSEMBLE_ROOT, RUNS_DIR


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
# validation
# ==============================================================================

def ensemble_twin(kernel_path: Path, heat_w: float) -> Path | None:
    """
    The calibration-ensemble kernel for the same plant-year run at the same
    heat, or None if there is none.

    Members are matched on their stored `heat_w` rather than on a member tag,
    so this does not need to know which member production selected, and stays
    correct if that selection changes. Only the ensemble year has counterparts.
    """
    pid_year = kernel_path.stem[len("kernel_"):]
    for cand in sorted(ENSEMBLE_ROOT.glob(f"kernels/kernel_{pid_year}_k*.nc")):
        with xr.open_dataset(cand) as ds:
            twin_heat = float(ds.attrs.get("heat_w", float("nan")))
        if np.isclose(twin_heat, heat_w, rtol=1e-6):
            return cand
    return None


def validate_kernels() -> bool:
    """
    Check every annual kernel in `ANNUAL_DIR` is usable, returning True if all
    checks pass.

    Each kernel must be finite, non-negative, carry some mass, record a
    sensible heat (a NaN means the run had no plume rise), and hold as many
    daily records as its run length implies. All kernels must share one grid,
    since they are summed across plants downstream. Where a calibration-
    ensemble kernel exists for the same plant-year and heat, the two must be
    identical: that confirms the production configuration reproduces the
    calibrated one.
    """
    paths = sorted(ANNUAL_DIR.glob("kernel_*.nc"))
    if not paths:
        print("\nvalidation: no kernels found")
        return False

    problems: list[str] = []
    ref_lats = ref_lons = None
    n_twin = n_match = 0

    for p in paths:
        with xr.open_dataset(p) as ds:
            arr = ds["transport_kernel"].values
            lats = ds["latitude"].values
            lons = ds["longitude"].values
            attrs = dict(ds.attrs)

        if not np.isfinite(arr).all():
            problems.append(f"{p.name}: non-finite values")
        if (arr < 0).any():
            problems.append(f"{p.name}: negative concentrations")
        if not arr.max() > 0:
            problems.append(f"{p.name}: no mass anywhere on the grid")

        # sampling covers the emission window, not the tail: a full run holds
        # one record per day of the financial year, 366 when it spans a leap
        # February. Anything short of that is a truncated run.
        emit_hrs = attrs.get("emit_hrs")
        sample_hrs = attrs.get("sample_hrs")
        n_records = attrs.get("n_daily_records")
        if None not in (emit_hrs, sample_hrs, n_records):
            expected = int(emit_hrs) // int(sample_hrs)
            if int(n_records) != expected:
                problems.append(
                    f"{p.name}: {int(n_records)} daily records, "
                    f"expected {expected}"
                )

        heat_w = float(attrs.get("heat_w", float("nan")))
        if not np.isfinite(heat_w):
            problems.append(f"{p.name}: no heat recorded (baseline run?)")

        if ref_lats is None:
            ref_lats, ref_lons = lats, lons
        elif not (np.array_equal(lats, ref_lats)
                  and np.array_equal(lons, ref_lons)):
            problems.append(f"{p.name}: grid differs from the other kernels")

        twin = ensemble_twin(p, heat_w) if np.isfinite(heat_w) else None
        if twin is not None:
            n_twin += 1
            with xr.open_dataset(twin) as ds_twin:
                same = np.array_equal(
                    arr, ds_twin["transport_kernel"].values
                )
            if same:
                n_match += 1
            else:
                problems.append(
                    f"{p.name}: differs from ensemble {twin.name}"
                )

    print(f"\nvalidation: {len(paths)} kernels checked, {n_twin} with an "
          f"ensemble counterpart ({n_match} identical)")

    if problems:
        print(f"{len(problems)} problems:")
        for msg in problems[:20]:
            print(f"  {msg}")
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more")
        return False

    print("all checks passed")
    return True


# ==============================================================================
# backfill
# ==============================================================================

def main() -> bool:
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

    return validate_kernels() and n_fail == 0


# ==============================================================================

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
