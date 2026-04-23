# Production run launch procedure

Single source of truth for kicking off the full HYSPLIT simulation. Work top-to-bottom; don't skip.

## T-24h (day before)

- [ ] `paths.py` updated: `SIM_ROOT` points to production location, not `sim_test`
- [ ] `kernel.py` `max_workers` matches intended core count (default `10`; set to `9` if you want 3 cores free)
- [ ] `git add -A && git commit -m "production run config"`
- [ ] `git tag production-run-$(date +%Y%m%d)`
- [ ] `pip freeze > requirements.lock.txt && git add requirements.lock.txt && git commit --amend --no-edit`
- [ ] Dry run: execute one `AnnualKernel` for a small/short-lived plant and confirm the annual NetCDF opens cleanly in xarray and has `transport_kernel` with expected shape
- [ ] Kill the dry run mid-month, restart; confirm daily idempotency skips completed `.nc` files and monthly idempotency skips completed kernels
- [ ] Back up `paths.py`, `*.py` source, `PANEL_PATH`, and **all** `ARL_DIR` contents to external drive (ARL files are expensive to regenerate)
- [ ] Close browser, Slack, email, anything chatty on the machine

## T-1h

```bash
# mask sleep/suspend/hibernate for the duration
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

# confirm they're masked
systemctl is-masked sleep.target suspend.target hibernate.target

# disable any automatic dnf updates
systemctl is-enabled dnf-automatic.timer 2>/dev/null && \
    sudo systemctl disable --now dnf-automatic.timer

# GNOME: Settings → Power → Screen Blank "Never", Auto Suspend off
```

- [ ] Close all GUI apps you don't need running
- [ ] Reboot for a clean slate
- [ ] Activate venv, `cd` to project root

## Launch

```bash
# Run pre-flight checks. Must print "GO" before proceeding.
./preflight.sh

# Thread caps — prevent numpy/OpenBLAS/MKL from spawning their own pools
# inside each HYSPLIT worker and over-subscribing the CPU.
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1

# Start the run inside tmux so closing the terminal does not kill it.
mkdir -p logs
tmux new -s hysplit

# Inside tmux (the prompt changes):
git rev-parse HEAD > run.commit    # record exact code version
nice -n 10 python -u <your_run_script>.py 2>&1 \
    | tee -a logs/run_$(date +%Y%m%d_%H%M).log

# Split pane for monitoring: Ctrl-b %
#   In the new pane: btop
# Detach: Ctrl-b d
```

## During the run (daily)

- [ ] `tmux attach -t hysplit` — confirm it's still ticking
- [ ] `find $MONTHLY_DIR -name '*.nc' | wc -l` — progress
- [ ] `find $ANNUAL_DIR -name '*.nc' | wc -l` — progress
- [ ] `df -h $SIM_ROOT` — disk OK
- [ ] `sensors` — temps stable, no throttling
- [ ] Nightly: `rsync -av --partial $SIM_ROOT/ /mnt/external/backup/`

## If it crashes

Pipeline aborts on any daily failure. To resume:

1. `tmux attach -t hysplit` — read the exception and the referenced `run.log`
2. Diagnose the failure (usually a missing ARL file, a bad CONTROL, or HYSPLIT refusing a stack height)
3. Fix the underlying issue
4. Re-launch: idempotency guards skip completed daily runs (`nc_path` exists), completed monthly kernels, and completed annual kernels

## Post-run

- [ ] Final `rsync` to external drive
- [ ] `git tag production-run-complete-$(date +%Y%m%d)`
- [ ] Archive `run.commit` and `logs/` alongside the kernels
- [ ] `sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target`
- [ ] Spot-check a handful of annual kernels: plot in Python, confirm plume pattern is plausible (concentrated near plant, elongated in prevailing wind direction, not uniformly zero, not uniformly saturated)