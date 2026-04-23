"""
Quick diagnostic plots for an annual transport kernel.

Produces two figures:
  (1) Map of the annual kernel on log-scaled colour.
  (2) Concentration vs distance-from-source scatter with a binned median.

The scatter is the primary diagnostic: a properly-resolved kernel should show
a monotonic decay in the binned median, with no flat plateau near source.
"""
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.colors import LogNorm

# ==============================================================================
# Inputs
PLANT_ID = "neyd06"
YEAR_MAJ = 1982

BASE_DIR = Path(
    "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants"
)

PANEL_PATH = BASE_DIR / "data" / "final" / "cegb_panel_with_stacks.csv"
KERNEL_PATH = (
    BASE_DIR / "data" / "final" / "sim_test" / "kernels" / "annual"
    / f"kernel_{PLANT_ID}_{YEAR_MAJ}.nc"
)

# ==============================================================================
# Plant metadata
df = pd.read_csv(PANEL_PATH)
rows = df[df["plant_id"] == PLANT_ID]
if rows.empty:
    raise ValueError(f"plant_id '{PLANT_ID}' not found in {PANEL_PATH}")
row = rows.iloc[0]

plant_name = str(row["plant_name"])
plant_lat = float(row["plant_lat"])
plant_lon = float(row["plant_long"])
fy_label = f"{YEAR_MAJ}/{str(YEAR_MAJ + 1)[-2:]}"

# ==============================================================================
# Kernel
ds = xr.open_dataset(KERNEL_PATH)
kernel = ds["transport_kernel"]
data = kernel.values
masked = np.where(data > 0, data, np.nan)

# ==============================================================================
# Distance from source to every grid cell (haversine, km)
R = 6371.0
lats = kernel["latitude"].values
lons = kernel["longitude"].values
LAT, LON = np.meshgrid(lats, lons, indexing="ij")

phi1 = np.radians(plant_lat)
phi2 = np.radians(LAT)
dphi = np.radians(LAT - plant_lat)
dlam = np.radians(LON - plant_lon)
a = np.sin(dphi / 2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2)**2
D = 2 * R * np.arcsin(np.sqrt(a))  # (lat, lon) in km

# ==============================================================================
# Flatten + drop zeros for log-log plotting
c = data.ravel()
d = D.ravel()
m = c > 0
c, d = c[m], d[m]

# ==============================================================================
# Binned median as a guide line through the cloud
bins = np.logspace(np.log10(max(d.min(), 1.0)), np.log10(d.max()), 25)
idx = np.digitize(d, bins)
bin_d = np.array([
    d[idx == i].mean() if (idx == i).any() else np.nan
    for i in range(1, len(bins))
])
bin_c = np.array([
    np.median(c[idx == i]) if (idx == i).any() else np.nan
    for i in range(1, len(bins))
])

# ==============================================================================
# Fit a power-law slope to the binned median and add reference lines
ok = np.isfinite(bin_c) & (bin_c > 0) & np.isfinite(bin_d) & (bin_d > 0)
slope, intercept = np.polyfit(np.log10(bin_d[ok]), np.log10(bin_c[ok]), 1)
print(f"Fitted power-law slope: {slope:.2f}")

# ==============================================================================
# Plot
fig = plt.figure(figsize=(14, 6))

# --- (1) Map ---
ax_map = fig.add_subplot(1, 2, 1, projection=ccrs.PlateCarree())
ax_map.add_feature(cfeature.COASTLINE, linewidth=0.8)
ax_map.add_feature(cfeature.BORDERS,   linewidth=0.5)

vmin = np.nanmin(masked[masked > 0])
vmax = np.nanmax(masked)
im = ax_map.pcolormesh(
    kernel.longitude, kernel.latitude, masked,
    norm=LogNorm(vmin=vmin, vmax=vmax),
    cmap="YlOrRd",
    transform=ccrs.PlateCarree(),
    shading="auto",
)
ax_map.plot(
    plant_lon, plant_lat, "b^", markersize=8,
    transform=ccrs.PlateCarree(), label=plant_name,
)
plt.colorbar(im, ax=ax_map, label="annual transport kernel", shrink=0.7)
ax_map.set_title(f"{plant_name}  —  annual kernel, FY {fy_label}")
ax_map.legend(loc="lower left")

# --- (2) Distance-concentration scatter ---
ax_sc = fig.add_subplot(1, 2, 2)
ax_sc.scatter(d, c, s=3, alpha=0.25, label="grid cells")
ax_sc.plot(bin_d, bin_c, "-", lw=2, color="C1", label="binned median")
ax_sc.set_xscale("log")
ax_sc.set_yscale("log")
ax_sc.set_xlabel("Distance from source (km)")
ax_sc.set_ylabel("Annual kernel")
ax_sc.set_title(f"{plant_name}  —  kernel vs distance, FY {fy_label}")
# Reference slopes anchored to the first finite bin
d_ref = np.logspace(np.log10(d.min()), np.log10(d.max()), 100)
idx_anchor = np.where(~np.isnan(bin_c))[0][0]
c_anchor = bin_c[idx_anchor]
d_anchor = bin_d[idx_anchor]

for s, style in [(-1.0, "--"), (-1.5, "-."), (-2.0, ":")]:
    ax_sc.plot(d_ref, c_anchor * (d_ref / d_anchor) ** s,
               style, color="grey", alpha=0.7, label=f"slope {s}")

ax_sc.text(
    0.05, 0.05,
    f"fitted slope = {slope:.2f}",
    transform=ax_sc.transAxes,
    fontsize=10,
    verticalalignment="bottom",
)
ax_sc.legend()

plt.tight_layout()
plt.show()
