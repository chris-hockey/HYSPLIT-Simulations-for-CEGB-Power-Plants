"""
Parallel runner for annual HYSPLIT kernels, with live progress reporting
and an append-only CSV log written to Dropbox.

Builds the (plant_id, year_maj) job list from the CEGB panel, then slices
to the first N for a dress rehearsal (set N_JOBS = None for the full run).

Per-job stdout: last duration, mean duration, completed/total, elapsed,
ETA, running failure count.

Per-job CSV row appended to RUN_LOG_PATH:
    timestamp, batch_id, hostname, plant_id, year_maj, status,
    duration_seconds, kernel_path, error_type, error_msg

Status is OK (ran successfully), SKIPPED (kernel already existed), or
FAIL. The log is append-only across batches; one header is written when
the file is first created, and every row is flushed immediately so the
Dropbox daemon syncs progress in near-real time.

Failures do not abort the batch. Idempotent via AnnualKernel.already_done().
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

from hysplit import PlantYear, AnnualKernel
from hysplit.paths import PANEL_PATH, RUN_LOG_PATH


# ----------------------------------------------------------------------
# config
# ----------------------------------------------------------------------

MAX_WORKERS = 6
N_JOBS = None         # dress rehearsal: first N jobs. None for full run.

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


# ----------------------------------------------------------------------
# job list
# ----------------------------------------------------------------------

def build_jobs(panel_path: Path = PANEL_PATH) -> list[tuple[str, int]]:
    """
    All unique (plant_id, year_maj) pairs from the panel, sorted by
    (plant_id, year_maj) for determinism.
    """
    df = pd.read_csv(panel_path)
    pairs = (
        df[["plant_id", "year_maj"]]
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
) -> tuple[str, int, Path | None, str, str | None, str | None, float]:
    """
    Run one plant-year kernel.

    Returns:
        (plant_id, year_maj, kernel_path, status, error_type, error_msg,
        seconds)
        where status ∈ {"OK", "SKIPPED", "FAIL"}.
    """
    t0 = time.time()
    try:
        py = PlantYear.from_panel(plant_id=plant_id, year_maj=year_maj)
        ak = AnnualKernel(plant_year=py)
        was_done = ak.already_done()
        out = ak.execute()
        status = "SKIPPED" if was_done else "OK"
        return plant_id, year_maj, out, status, None, None, time.time() - t0
    except Exception as e:
        return (
            plant_id, year_maj, None, "FAIL",
            type(e).__name__, str(e), time.time() - t0,
        )


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

def run_parallel(
    jobs: list[tuple[str, int]],
    max_workers: int,
    log_path: Path = RUN_LOG_PATH,
) -> None:
    n_total = len(jobs)
    n_ok = n_skip = n_fail = 0
    failures: list[tuple[str, int, str]] = []
    durations: list[float] = []

    batch_id = (
        datetime.now().strftime("%Y%m%dT%H%M%S")
        + "_" + uuid.uuid4().hex[:6]
    )
    hostname = socket.gethostname()

    # open the log: write header iff file is new/empty
    log_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_path.exists() or log_path.stat().st_size == 0

    t_start = time.time()
    print(f"starting: {n_total} jobs, {max_workers} workers")
    print(f"batch_id: {batch_id}")
    print(f"host:     {hostname}")
    print(f"log:      {log_path}\n")

    with open(log_path, "a", newline="") as log_file:
        writer = csv.DictWriter(log_file, fieldnames=LOG_FIELDS)
        if write_header:
            writer.writeheader()
            log_file.flush()

        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(_run_one, pid, yr): (pid, yr) for pid, yr in jobs
            }
            for fut in as_completed(futures):
                pid, yr, path, status, err_type, err_msg, dur = fut.result()
                durations.append(dur)

                if status == "OK":
                    n_ok += 1
                    detail = path.name
                elif status == "SKIPPED":
                    n_skip += 1
                    detail = f"{path.name} (already done)"
                else:
                    n_fail += 1
                    detail = f"{err_type}: {err_msg}"
                    failures.append((pid, yr, detail))

                # write row + flush so Dropbox picks it up immediately
                try:
                    writer.writerow({
                        "timestamp":        datetime.now().isoformat(timespec="seconds"),
                        "batch_id":         batch_id,
                        "hostname":         hostname,
                        "plant_id":         pid,
                        "year_maj":         yr,
                        "status":           status,
                        "duration_seconds": f"{dur:.1f}",
                        "kernel_path":      str(path) if path else "",
                        "error_type":       err_type or "",
                        "error_msg":        err_msg or "",
                    })
                    log_file.flush()
                except Exception as log_err:
                    print(f"  WARN: failed to write log row: {log_err}")

                n_done = n_ok + n_skip + n_fail
                elapsed = time.time() - t_start
                mean_t = sum(durations) / len(durations)
                eta = ((n_total - n_done) / max_workers) * mean_t

                print(
                    f"[{n_done:>4}/{n_total}] {status:<7} "
                    f"{pid:<10} FY{yr}  "
                    f"last={_fmt(dur):<10} "
                    f"mean={_fmt(mean_t):<10} "
                    f"elapsed={_fmt(elapsed):<12} "
                    f"eta={_fmt(eta):<12} "
                    f"fails={n_fail}  "
                    f"->  {detail}"
                )

    # ------------------------------------------------------------------
    # summary
    # ------------------------------------------------------------------
    total_elapsed = time.time() - t_start
    mean_t = sum(durations) / len(durations) if durations else 0.0
    print(
        f"\ndone: {n_ok} ok, {n_skip} skipped, {n_fail} failed, "
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
