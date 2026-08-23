"""
Parallel runner for the 1981/82 HEAT plume-rise ensemble.

Crosses every plant operating in the calibration year with the ensemble members,
running one HYSPLIT simulation per (plant, member). Sensible heat is read from 
the panel's precomputed `heat_w_k1..k7` columns and passed to `AnnualKernel`. 
Coal, oil and gas turbines all vary with the member, so every plant runs once 
per member (105 plants x 7 = 735 runs for 1981/82).

Kernels are written under `ENSEMBLE_ROOT`, keeping the ensemble in its own
subtree, and are consumed by `ensemble_treatment.py`.

Per-job CSV rows are appended to `ENSEMBLE_LOG_PATH`:
    timestamp, batch_id, hostname, plant_id, year_maj, member_tag, heat_w,
    status, duration_seconds, kernel_path, error_type, error_msg

Status is OK / SKIPPED (kernel existed) / FAIL. Failures do not abort the batch.
Idempotent via `AnnualKernel.already_done()`.

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

from __future__ import annotations

import csv
import socket
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
from hysplit import AnnualKernel, PlantYear
from hysplit.paths import DROPBOX_DIR, ENSEMBLE_ROOT, PANEL_PATH

# ==============================================================================

ENSEMBLE_LOG_PATH = DROPBOX_DIR / "ensemble_run_log.csv"

YEAR_MAJ = 1981          # calibration financial year: 1 Apr 1981 - 31 Mar 1982
MAX_WORKERS = 10
N_JOBS = None            # dress rehearsal: first N jobs. None for full run.

LOG_FIELDS = [
    "timestamp", "batch_id", "hostname",
    "plant_id", "year_maj", "member_tag", "heat_w",
    "status", "duration_seconds", "kernel_path", "error_type", "error_msg",
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


# ==============================================================================
# formatting
# ==============================================================================

def _fmt(seconds: float) -> str:
    """Seconds as a compact duration string, e.g. "2h 14m 6s"."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


# ==============================================================================
# orchestrator
# ==============================================================================

def run_parallel(
    jobs: list[tuple[str, int, int, float]],
    max_workers: int,
    log_path: Path = ENSEMBLE_LOG_PATH,
) -> None:
    """
    Run `jobs` across a process pool, logging each result as it completes.

    Every job gets a CSV row appended to `log_path` (header written only if the
    file is new or empty), flushed after each write so an interrupted batch 
    leaves a usable log. Progress, running counts and a rough ETA are printed 
    per job; a summary and the full list of failures print at the end.

    The batch is tagged with a `batch_id` and hostname so repeated or resumed 
    runs remain distinguishable in the same log file.
    """
    n_total = len(jobs)
    n_ok = n_skip = n_fail = 0
    durations: list[float] = []
    failures: list[str] = []

    batch_id = (
        datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    hostname = socket.gethostname()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_path.exists() or log_path.stat().st_size == 0

    t_start = time.time()
    print(f"starting: {n_total} jobs, {max_workers} workers")
    print(f"batch_id: {batch_id}")
    print(f"log:      {log_path}\n")

    with open(log_path, "a", newline="") as log_file:
        writer = csv.DictWriter(log_file, fieldnames=LOG_FIELDS)
        if write_header:
            writer.writeheader()
            log_file.flush()

        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(_run_one, pid, yr, k, hw): (pid, yr, k)
                for pid, yr, k, hw in jobs
            }
            for fut in as_completed(futures):
                r = fut.result()
                dur = r["duration_seconds"]
                durations.append(dur)

                if r["status"] == "OK":
                    n_ok += 1
                elif r["status"] == "SKIPPED":
                    n_skip += 1
                else:
                    n_fail += 1
                    failures.append(
                        f"{r['plant_id']} {r['member_tag']}: "
                        f"{r['error_type']}: {r['error_msg']}"
                    )

                try:
                    writer.writerow({
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "batch_id": batch_id,
                        "hostname": hostname,
                        "duration_seconds": f"{dur:.1f}",
                        **{k: r[k] for k in (
                            "plant_id", "year_maj", "member_tag", "heat_w",
                            "status", "kernel_path", "error_type", "error_msg",
                        )},
                    })
                    log_file.flush()
                except Exception as log_err:            # noqa: BLE001
                    print(f"  WARN: failed to write log row: {log_err}")

                n_done = n_ok + n_skip + n_fail
                elapsed = time.time() - t_start
                mean_t = sum(durations) / len(durations)
                eta = ((n_total - n_done) / max_workers) * mean_t
                print(
                    f"[{n_done:>4}/{n_total}] {r['status']:<7} "
                    f"{r['plant_id']:<10} {r['member_tag']:<4} "
                    f"last={_fmt(dur):<9} mean={_fmt(mean_t):<9} "
                    f"elapsed={_fmt(elapsed):<11} eta={_fmt(eta):<11} "
                    f"fails={n_fail}"
                )

    total_elapsed = time.time() - t_start
    mean_t = sum(durations) / len(durations) if durations else 0.0
    print(
        f"\ndone: {n_ok} ok, {n_skip} skipped, {n_fail} failed, "
        f"wall-clock {_fmt(total_elapsed)}, mean per job {_fmt(mean_t)}"
    )
    if failures:
        print("\nfailures:")
        for f in failures:
            print(f"  {f}")


if __name__ == "__main__":
    all_jobs = build_jobs()
    print(f"{len(all_jobs)} ensemble jobs for FY{YEAR_MAJ}")

    jobs = all_jobs if N_JOBS is None else all_jobs[:N_JOBS]
    run_parallel(jobs, max_workers=MAX_WORKERS)
