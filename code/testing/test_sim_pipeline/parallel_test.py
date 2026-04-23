"""
Parallel runner for annual HYSPLIT kernels, with live progress reporting.

Builds the (plant_id, year_maj) job list from the CEGB panel — the same way
the full production run will — then slices to the first N for a dress rehearsal.

Reports per-job:
    - time for the most recent job
    - mean time per completed job
    - completed / total
    - wall-clock elapsed
    - ETA based on mean time per job and worker count
    - running failure count and cause

Failures do not abort the batch. Idempotent via AnnualKernel.already_done(),
so re-running the same jobs skips completed work.
"""
from __future__ import annotations
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from hysplit import PlantYear, AnnualKernel
from hysplit.paths import PANEL_PATH


# ----------------------------------------------------------------------
# config
# ----------------------------------------------------------------------

MAX_WORKERS = 10
N_JOBS = 10          # dress rehearsal: first N jobs from the full list
# set to None for full production run


# ----------------------------------------------------------------------
# job list
# ----------------------------------------------------------------------

def build_jobs(panel_path: Path = PANEL_PATH) -> list[tuple[str, int]]:
    """
    All unique (plant_id, year_maj) pairs from the panel where the plant has
    non-zero fuel input. Sorted by (plant_id, year_maj) for determinism.
    """
    df = pd.read_csv(panel_path)
    pairs = (
        df[["year_maj", "plant_id"]]
        .drop_duplicates()
        .sort_values(["plant_id", "year_maj"])
        .itertuples(index=False, name=None)
    )
    return [(str(pid), int(yr)) for pid, yr in pairs]


# ----------------------------------------------------------------------
# worker
# ----------------------------------------------------------------------

def _run_one(
    plant_id: str,
    year_maj: int,
) -> tuple[str, int, Path | None, str | None, float]:
    """Run one plant-year kernel. Returns (id, year, path, err, seconds)."""
    t0 = time.time()
    try:
        py = PlantYear.from_panel(plant_id=plant_id, year_maj=year_maj)
        ak = AnnualKernel(plant_year=py)
        out = ak.execute()
        return plant_id, year_maj, out, None, time.time() - t0
    except Exception as e:
        return plant_id, year_maj, None, f"{type(e).__name__}: {e}", time.time() - t0


# ----------------------------------------------------------------------
# formatting
# ----------------------------------------------------------------------

def _fmt(seconds: float) -> str:
    """'1h 23m 45s', '4m 12s', '15s'."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


# ----------------------------------------------------------------------
# orchestrator
# ----------------------------------------------------------------------

def run_parallel(jobs: list[tuple[str, int]], max_workers: int) -> None:
    n_total = len(jobs)
    n_ok = 0
    n_fail = 0
    failures: list[tuple[str, int, str]] = []
    durations: list[float] = []

    t_start = time.time()
    print(f"starting: {n_total} jobs, {max_workers} workers\n")

    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_run_one, pid, yr): (pid, yr) for pid, yr in jobs}
        for fut in as_completed(futures):
            pid, yr, path, err, dur = fut.result()
            durations.append(dur)

            if err is None:
                n_ok += 1
                status = "OK"
                detail = path.name
            else:
                n_fail += 1
                status = "FAIL"
                detail = err
                failures.append((pid, yr, err))

            n_done = n_ok + n_fail
            elapsed = time.time() - t_start
            mean_t = sum(durations) / len(durations)
            n_left = n_total - n_done
            eta = (n_left / max_workers) * mean_t

            print(
                f"[{n_done:>4}/{n_total}] {status:<4} "
                f"{pid:<10} FY{yr}  "
                f"last={_fmt(dur):<10} "
                f"mean={_fmt(mean_t):<10} "
                f"elapsed={_fmt(elapsed):<12} "
                f"eta={_fmt(eta):<12} "
                f"fails={n_fail}  "
                f"->  {detail}"
            )

    # --------------------------------------------------------------
    # summary
    # --------------------------------------------------------------
    total_elapsed = time.time() - t_start
    mean_t = sum(durations) / len(durations) if durations else 0.0
    print(
        f"\ndone: {n_ok} ok, {n_fail} failed, "
        f"wall-clock {_fmt(total_elapsed)}, "
        f"mean per job {_fmt(mean_t)}"
    )
    if failures:
        print("\nfailures:")
        for pid, yr, err in failures:
            print(f"  {pid} FY{yr}: {err}")


if __name__ == "__main__":
    all_jobs = build_jobs()
    print(f"{len(all_jobs)} total plant-years in panel")

    jobs = all_jobs if N_JOBS is None else all_jobs[:N_JOBS]
    run_parallel(jobs, max_workers=MAX_WORKERS)
