"""
Global list of file paths called upon
"""

from pathlib import Path

# project root
PROJECT_ROOT = Path(
    "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants")

# HYSPLIT binaries
HYSPLIT_DIR = Path.home() / "opt/hysplit/hysplit.v5.4.2_RHEL9.7_public"
HYCS_STD = HYSPLIT_DIR / "exec/hycs_std"
CON2CDF4 = HYSPLIT_DIR / "exec/con2cdf4"

# met data
ARL_DIR = PROJECT_ROOT / "data/final/arl"

# cegb panel
PANEL_PATH = PROJECT_ROOT / "data/final/cegb_panel_with_stacks.csv"

# simulation outputs
SIM_ROOT = PROJECT_ROOT / "data/final/sim_test"
RUNS_DIR = SIM_ROOT / "runs"
MONTHLY_DIR = SIM_ROOT / "kernels/monthly"
ANNUAL_DIR = SIM_ROOT / "kernels/annual"

# grid
GRID_CENTRE = (53.0, -2.0)  # lat, lon
GRID_SPACING = (0.05, 0.05)  # degrees
GRID_SPAN = (10.0, 14.0)   # degrees lat, lon
OUTPUT_HT_M = 100           # AGL metres

#  simulation parameters
RUN_HRS = 72  # track tracer particle for this long
EMIT_HRS = 24  # emit tracer particle from plant for this long
