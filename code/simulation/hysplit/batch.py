"""
Shared parallel batch runner for HYSPLIT jobs.

`run_batch` runs a worker across a process pool, appends one CSV row per job to
a log, and prints progress with a running mean and ETA. Both `sim_run.py` (the
production kernels) and `ensemble_run.py` (the plume-rise ensemble) call it;
they differ only in the job list, the worker, the log columns, and the one-line
job description.

The worker is any top-level function submitted to the pool. It is called as
`worker(*job)` for each job tuple and must never raise: it returns a dict
carrying at least `status` ("OK", "SKIPPED" or "FAIL") and `duration_seconds`,
plus the run-specific columns named in `log_fields`. `run_batch` adds
`timestamp`, `batch_id` and `hostname`.

Skipped jobs (an existing kernel) finish in milliseconds, so they are excluded
from the mean and the ETA, which describe real runs only.

Author: Christopher Hockey
chrishockey2@gmail.com
September 2026
"""

from __future__ import annotations

import csv
import socket
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable


def fmt_duration(seconds: float) -> str:
    """Seconds as a compact duration string, e.g. "1h 23m 45s"."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def run_batch(
    jobs: list[tuple],
    worker: Callable[..., dict],
    log_fields: list[str],
    log_path: Path,
    describe: Callable[[dict], str],
    max_workers: int,
) -> None:
    """
    Run `jobs` across a process pool, logging each result as it completes.

    Every job gets a CSV row appended to `log_path` (header written only if the
    file is new or empty), flushed after each write so an external watcher sees
    progress and an interrupted batch leaves a usable log. A running count, mean
    and ETA print per job; a summary and the failures print at the end.

    `worker(*job)` returns a dict with at least `status` and `duration_seconds`;
    the mean and ETA cover non-skipped runs only. The batch is tagged with a
    `batch_id` and hostname so repeated or resumed runs stay distinguishable in
    one log file.
    """
    n_total = len(jobs)
    n_ok = n_skip = n_fail = 0
    durations: list[float] = []
    failures: list[dict] = []

    batch_id = (
        datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    hostname = socket.gethostname()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_path.exists() or log_path.stat().st_size == 0

    t_start = time.time()
    print(f"starting: {n_total} jobs, {max_workers} workers")
    print(f"batch_id: {batch_id}")
    print(f"host:     {hostname}")
    print(f"log:      {log_path}\n")

    with open(log_path, "a", newline="") as log_file:
        writer = csv.DictWriter(log_file, fieldnames=log_fields)
        if write_header:
            writer.writeheader()
            log_file.flush()

        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(worker, *job) for job in jobs]
            for fut in as_completed(futures):
                r = fut.result()
                status = r["status"]
                dur = r["duration_seconds"]

                if status == "OK":
                    n_ok += 1
                elif status == "SKIPPED":
                    n_skip += 1
                else:
                    n_fail += 1
                    failures.append(r)

                # skips finish in milliseconds; keep only real runs in the
                # mean and the ETA
                if status != "SKIPPED":
                    durations.append(dur)

                row = {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "batch_id": batch_id,
                    "hostname": hostname,
                    **r,
                }
                row["duration_seconds"] = f"{dur:.1f}"
                try:
                    writer.writerow({k: row.get(k, "") for k in log_fields})
                    log_file.flush()
                except Exception as log_err:            # noqa: BLE001
                    print(f"  WARN: failed to write log row: {log_err}")

                n_done = n_ok + n_skip + n_fail
                elapsed = time.time() - t_start
                mean_t = sum(durations) / len(durations) if durations else 0.0
                eta = ((n_total - n_done) / max_workers) * mean_t
                print(
                    f"[{n_done:>4}/{n_total}] {status:<7} "
                    f"{describe(r):<20} "
                    f"last={fmt_duration(dur):<10} "
                    f"mean={fmt_duration(mean_t):<10} "
                    f"elapsed={fmt_duration(elapsed):<12} "
                    f"eta={fmt_duration(eta):<12} "
                    f"fails={n_fail}"
                )

    total_elapsed = time.time() - t_start
    mean_t = sum(durations) / len(durations) if durations else 0.0
    print(
        f"\ndone: {n_ok} ok, {n_skip} skipped, {n_fail} failed, "
        f"wall-clock {fmt_duration(total_elapsed)}, "
        f"mean per run, excluding skipped {fmt_duration(mean_t)}"
    )
    if failures:
        print("\nfailures:")
        for r in failures:
            print(f"  {describe(r)}: {r['error_type']}: {r['error_msg']}")
