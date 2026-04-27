"""
Directional diagnostics for an annual transport kernel.

Produces two plots:
  (1) Polar histogram (wind rose) of kernel mass by bearing from source.
      Each radial wedge represents a bearing bin; length of wedge is the
      total kernel in that bin. Tells you which direction the plume goes.
  (2) Polar heatmap of kernel by (bearing, distance) — the 2D decomposition
      of the kernel in polar coordinates centred on the source.

The wind rose should broadly align with the plant's prevailing-wind climatology
(SW-dominant for most UK locations, varying seasonally). The polar heatmap
gives you a radial decay structure per bearing and reveals anisotropy.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.colors import LogNorm

# ==============================================================================
# Inputs
PLANT_ID = "mdemd01"
YEAR_MAJ = 1973

BASE_DIR = Path(
    "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants"
)
PANEL_PATH = BASE_DIR / "data" / "final" / "cegb_panel_with_stacks.csv"
KERNEL_PATH = (
    BASE_DIR / "data" / "final" / "simulation_output" / "kernels" / "annual"
    / f"kernel_{PLANT_ID}_{YEAR_MAJ}.nc"
)

N_BEARING_BINS = 36          # 10-degree bins for the rose
N_DISTANCE_BINS = 20          # log-spaced radial bins for the heatmap
DIST_MAX_KM = 500.0

# ==============================================================================
# Plant metadata
df = pd.read_csv(PANEL_PATH)
row = df[df["plant_id"] == PLANT_ID].iloc[0]
name = str(row["plant_name"])
plat = float(row["plant_lat"])
plon = float(row["plant_long"])
fy = f"{YEAR_MAJ}/{str(YEAR_MAJ + 1)[-2:]}"

# ==============================================================================
# Kernel + per-cell bearing and distance from source
ds = xr.open_dataset(KERNEL_PATH)
K = ds["transport_kernel"].values                 # (lat, lon)
lats = ds["latitude"].values
lons = ds["longitude"].values
LAT, LON = np.meshgrid(lats, lons, indexing="ij")

# haversine distance (km)
R = 6371.0
phi1 = np.radians(plat)
phi2 = np.radians(LAT)
dphi = np.radians(LAT - plat)
dlam = np.radians(LON - plon)
a = np.sin(dphi / 2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2)**2
D = 2 * R * np.arcsin(np.sqrt(a))

# initial bearing (forward azimuth) from source to each cell, in degrees 0-360
# (0 = north, 90 = east)
y = np.sin(dlam) * np.cos(phi2)
x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(dlam)
B = (np.degrees(np.arctan2(y, x)) + 360.0) % 360.0

# flatten and keep only in-range positive cells
flat_K = K.ravel()
flat_D = D.ravel()
flat_B = B.ravel()
m = (flat_K > 0) & (flat_D > 0) & (flat_D <= DIST_MAX_KM)
K_, D_, B_ = flat_K[m], flat_D[m], flat_B[m]

# ==============================================================================
# (1) Wind rose: total kernel per bearing bin (integrated over all distances)
bearing_edges = np.linspace(0.0, 360.0, N_BEARING_BINS + 1)
bearing_ctr = 0.5 * (bearing_edges[:-1] + bearing_edges[1:])
rose_totals, _ = np.histogram(B_, bins=bearing_edges, weights=K_)
counts, _ = np.histogram(B_, bins=bearing_edges)
rose_totals = np.divide(rose_totals, counts, out=np.zeros_like(rose_totals),
                        where=counts > 0)

# ==============================================================================
# (2) Polar heatmap: kernel summed in (bearing, distance) bins
dist_edges = np.logspace(np.log10(max(D_.min(), 1.0)), np.log10(D_.max()),
                         N_DISTANCE_BINS + 1)
dist_ctr = 0.5 * (dist_edges[:-1] + dist_edges[1:])
H, _, _ = np.histogram2d(B_, D_, bins=[bearing_edges, dist_edges],
                         weights=K_)
# (bearing, distance) -> we want (distance, bearing) for meshgrid plotting
H = H.T   # shape (n_dist, n_bearing)

# ==============================================================================
# Plot
fig = plt.figure(figsize=(14, 6))

# --- (1) Wind rose ---
ax1 = fig.add_subplot(1, 2, 1, projection="polar")
# matplotlib polar: 0 rad = right (east), angles CCW. For a meteorological rose
# with 0 deg = north at top, angles clockwise, we flip:
ax1.set_theta_zero_location("N")
ax1.set_theta_direction(-1)

# bar widths = bin size in radians
width = np.deg2rad(360.0 / N_BEARING_BINS)
ax1.bar(
    np.deg2rad(bearing_ctr), rose_totals,
    width=width, bottom=0.0, edgecolor="white", linewidth=0.3,
    align="center",
)
ax1.set_title(f"{name}  -  kernel by bearing, FY {fy}", pad=20)
ax1.set_rlabel_position(135)

# --- (2) Polar heatmap ---
ax2 = fig.add_subplot(1, 2, 2, projection="polar")
ax2.set_theta_zero_location("N")
ax2.set_theta_direction(-1)

theta_grid, r_grid = np.meshgrid(np.deg2rad(bearing_edges), dist_edges)
# mask zeros so LogNorm doesn't choke
H_masked = np.ma.masked_where(H <= 0, H)
pm = ax2.pcolormesh(
    theta_grid, r_grid, H_masked,
    norm=LogNorm(vmin=H_masked.min(), vmax=H_masked.max()),
    cmap="YlOrRd", shading="auto",
)
ax2.set_title(f"{name}  -  kernel by bearing x distance, FY {fy}", pad=20)
ax2.set_rscale("symlog", linthresh=10)
plt.colorbar(pm, ax=ax2, label="kernel sum in bin", shrink=0.7)

plt.tight_layout()
plt.show()
