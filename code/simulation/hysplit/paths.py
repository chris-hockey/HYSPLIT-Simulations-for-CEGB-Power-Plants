"""
Global list of file paths and simulation parameters called upon

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

from pathlib import Path

# project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# HYSPLIT binaries
HYSPLIT_DIR = Path.home() / "opt/hysplit/hysplit.v5.4.2_RHEL9.7_public"
BDYFILES_DIR = HYSPLIT_DIR / "bdyfiles"
HYCS_STD = HYSPLIT_DIR / "exec/hycs_std"
CON2CDF4 = HYSPLIT_DIR / "exec/con2cdf4"

# met data
ARL_DIR = PROJECT_ROOT / "data/final/arl"

# cegb panel
PANEL_PATH = PROJECT_ROOT / "data/final/cegb_panel_with_stacks.csv"

# simulation outputs
SIM_ROOT = PROJECT_ROOT / "data/final/simulation_output"
ENSEMBLE_ROOT = SIM_ROOT / "ensemble_1981"
RUNS_DIR = SIM_ROOT / "runs"
ENSEMBLE_RUNS_DIR = ENSEMBLE_ROOT / "runs"
ANNUAL_DIR = SIM_ROOT / "kernels/annual"
MONTHLY_DIR = SIM_ROOT / "kernels/monthly"

# grid
GRID_CENTRE = (53.0, -2.0)  # lat, lon
GRID_SPACING = (0.05, 0.05)  # degrees
GRID_SPAN = (10.0, 14.0)   # degrees lat, lon
OUTPUT_HT_M = 100           # AGL metres

# simulation parameters
TAIL_HRS = 72        # hours after emission stop for particles to clear
SAMPLE_HRS = 24        # output averaging interval (daily means)
NUMPAR = 500_000   # total particles across a full FY (~57/hr release)
MAXPAR = 100_000    # cap on particles on grid at any instant

# per-run CSV logs, written inside the repo
LOG_DIR = PROJECT_ROOT / "logs"
RUN_LOG_PATH = LOG_DIR / "run_log.csv"
ENSEMBLE_LOG_PATH = LOG_DIR / "ensemble_run_log.csv"
