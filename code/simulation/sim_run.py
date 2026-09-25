"""
Parallel runner for annual HYSPLIT kernels, using the shared batch runner in
`hysplit.batch`.

Builds the (plant_id, year_maj, heat_w) job list from the CEGB panel, and can
select the first N for a test run (set `N_JOBS = None` for the full run).
`heat_w` is the calibration-selected sensible heat for the plant's fuel
category, set in `1_pp_cleaning.py`; passing it makes each run write an EMITIMES
file and switch on Briggs plume rise, so particles are released at the effective
rather than the physical stack height.

Kernels are written to `ANNUAL_DIR` via `AnnualKernel`'s default output root.
One CSV row per job is appended to `RUN_LOG_PATH` (logs/`):

    timestamp, batch_id, hostname, plant_id, year_maj, status,
    duration_seconds, kernel_path, error_type, error_msg

Status is OK (ran), SKIPPED (kernel already existed), or FAIL. Failures do not
abort the batch. Idempotent via `AnnualKernel.already_done()`.

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from hysplit import AnnualKernel, PlantYear
from hysplit.batch import run_batch
from hysplit.paths import PANEL_PATH, RUN_LOG_PATH


# ==============================================================================

# Run in parallel across 10 cores (change for your own machine)
MAX_WORKERS = 10
N_JOBS = None  # Specify a number for a test of N plant-years, None for full run

LOG_FIELDS = [
    "timestamp",
    "batch_id",
    "hostname",
    "plant_id",
    "year_maj",
    "status",
    "duration_seconds",
    "kernel_path",
    "error_type",
    "error_msg",
]


# ==============================================================================
# job list
# ==============================================================================

def build_jobs(panel_path: Path = PANEL_PATH) -> list[tuple[str, int, float]]:
    """
    All unique (plant_id, year_maj, heat_w) triples from the CEGB panel, sorted
    by (plant_id, year_maj) for determinism.

    Raises `KeyError` if the panel has no `heat_w` column (re-run
    `1_pp_cleaning.py` and `2_stack_pred.py`), and `ValueError` if any retained
    plant-year has a missing heat value.
    """
    df = pd.read_csv(panel_path)

    if "heat_w" not in df.columns:
        raise KeyError(
            f"no 'heat_w' column in {panel_path}; re-run 1_pp_cleaning.py "
            f"and 2_stack_pred.py to rebuild the panel with plume-rise heat."
        )

    jobs = (
        df[["plant_id", "year_maj", "heat_w"]]
        .drop_duplicates(subset=["plant_id", "year_maj"])
        .sort_values(["plant_id", "year_maj"])
    )

    if jobs["heat_w"].isna().any():
        n_bad = int(jobs["heat_w"].isna().sum())
        raise ValueError(
            f"{n_bad} plant-years have a missing heat_w; these would be "
            f"written into EMITIMES as 'nan'."
        )

    return [
        (str(pid), int(yr), float(heat))
        for pid, yr, heat in jobs.itertuples(index=False, name=None)
    ]


# ==============================================================================
# worker
# ==============================================================================

def _run_one(plant_id: str, year_maj: int, heat_w: float) -> dict:
    """
    Run one plant-year kernel at the given sensible heat (W), returning a dict of
    log fields. Status is "OK", "SKIPPED" or "FAIL".

    Never raises: any exception is caught and recorded as a FAIL row so a single
    bad plant-year does not abort the batch.
    """
    t0 = time.time()
    base = {
        "plant_id": plant_id, "year_maj": year_maj,
        "kernel_path": "", "error_type": "", "error_msg": "",
    }
    try:
        py = PlantYear.from_panel(plant_id=plant_id, year_maj=year_maj)
        ak = AnnualKernel(plant_year=py, heat_w=heat_w)
        was_done = ak.already_done()
        out = ak.execute()
        base.update(status="SKIPPED" if was_done else "OK",
                    kernel_path=str(out))
    except Exception as e:                # noqa: BLE001 - log, do not abort batch
        base.update(status="FAIL", error_type=type(
            e).__name__, error_msg=str(e))
    base["duration_seconds"] = time.time() - t0
    return base


def _describe(r: dict) -> str:
    """One-line identity for the progress and failure lines."""
    return f"{r['plant_id']:<10} FY{r['year_maj']}"


# ==============================================================================

if __name__ == "__main__":
    all_jobs = build_jobs()
    print(f"{len(all_jobs)} total plant-years in panel")

    jobs = all_jobs if N_JOBS is None else all_jobs[:N_JOBS]
    run_batch(jobs, _run_one, LOG_FIELDS, RUN_LOG_PATH, _describe, MAX_WORKERS)
