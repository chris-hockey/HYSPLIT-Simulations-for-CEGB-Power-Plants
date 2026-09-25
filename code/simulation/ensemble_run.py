"""
Parallel runner for the 1981/82 HEAT plume-rise ensemble, using the shared batch
runner in `hysplit.batch`.

Crosses every plant operating in the calibration year with the ensemble members,
running one HYSPLIT simulation per (plant, member). Sensible heat is read from
the panel's precomputed `heat_w_k1..k7` columns and passed to `AnnualKernel`.
Coal, oil and gas turbines all vary with the member, so every plant runs once
per member (105 plants x 7 = 735 runs for 1981/82).

Kernels are written under `ENSEMBLE_ROOT`, keeping the ensemble in its own
subtree, and are consumed by `1_ensemble_treatment.py`. One CSV row per job is
appended to `ENSEMBLE_LOG_PATH` (`logs/`):

    timestamp, batch_id, hostname, plant_id, year_maj, member_tag, heat_w,
    status, duration_seconds, kernel_path, error_type, error_msg

Status is OK / SKIPPED (kernel existed) / FAIL. Failures do not abort the batch.
Idempotent via `AnnualKernel.already_done()`.

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
from hysplit.paths import ENSEMBLE_LOG_PATH, ENSEMBLE_ROOT, PANEL_PATH

# ==============================================================================

YEAR_MAJ = 1981  # calibration financial year: 1 Apr 1981 - 31 Mar 1982
# Run in parallel across 10 cores (change for your own machine)
MAX_WORKERS = 10
N_JOBS = None  # Specify a number for a test of N plant-years, None for full run

LOG_FIELDS = [
    "timestamp",
    "batch_id",
    "hostname",
    "plant_id",
    "year_maj",
    "member_tag",
    "heat_w",
    "status",
    "duration_seconds",
    "kernel_path",
    "error_type",
    "error_msg",
]


# ==============================================================================
# job list
# ==============================================================================

def _heat_cols(df: pd.DataFrame) -> list[str]:
    """
    Panel heat columns ordered heat_w_k1, heat_w_k2, ... Sorted on the
    trailing integer rather than lexically, so k10 would follow k9.
    """
    return sorted(
        (c for c in df.columns if c.startswith("heat_w_k")),
        key=lambda c: int(c.rsplit("k", 1)[1]),
    )


def build_jobs(panel_path: Path = PANEL_PATH) -> list[tuple[str, int, int, float]]:
    """
    (plant_id, year_maj, member_number, heat_w) for every plant operating in
    YEAR_MAJ crossed with every heat_w_k* column. member_number is 1-based to
    match the k1..k7 columns/tags.

    Raises `RuntimeError` if the panel has no heat columns, which means it
    predates the HEAT ensemble step in 1_pp_cleaning.py.
    """
    df = pd.read_csv(panel_path)
    hcols = _heat_cols(df)
    if not hcols:
        raise RuntimeError(
            f"no heat_w_k* columns in {panel_path}; rebuild the panel "
            "(1_pp_cleaning.py) with the HEAT columns before running."
        )

    sub = (
        df[df["year_maj"] == YEAR_MAJ]
        .drop_duplicates(subset=["plant_id"])
        .sort_values("plant_id")
    )

    jobs: list[tuple[str, int, int, float]] = []
    for _, row in sub.iterrows():
        pid = str(row["plant_id"])
        for k, col in enumerate(hcols, start=1):
            jobs.append((pid, YEAR_MAJ, k, float(row[col])))
    return jobs


# ==============================================================================
# worker
# ==============================================================================

def _run_one(plant_id: str, year_maj: int, k_num: int, heat_w: float) -> dict:
    """
    Run one (plant, member) kernel and return a dict of log fields.

    Never raises: any exception is caught and recorded as a FAIL row so a
    single bad plant-year does not abort the batch.
    """
    t0 = time.time()
    tag = f"k{k_num}"
    base = {
        "plant_id": plant_id, "year_maj": year_maj, "member_tag": tag,
        "heat_w": heat_w, "kernel_path": "", "error_type": "", "error_msg": "",
    }
    try:
        py = PlantYear.from_panel(plant_id=plant_id, year_maj=year_maj)
        ak = AnnualKernel(
            plant_year=py, heat_w=heat_w, member_tag=tag, out_root=ENSEMBLE_ROOT
        )
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
    return f"{r['plant_id']:<10} {r['member_tag']}"


# ==============================================================================

if __name__ == "__main__":
    all_jobs = build_jobs()
    print(f"{len(all_jobs)} ensemble jobs for FY{YEAR_MAJ}")

    jobs = all_jobs if N_JOBS is None else all_jobs[:N_JOBS]
    run_batch(jobs, _run_one, LOG_FIELDS,
              ENSEMBLE_LOG_PATH, _describe, MAX_WORKERS)
