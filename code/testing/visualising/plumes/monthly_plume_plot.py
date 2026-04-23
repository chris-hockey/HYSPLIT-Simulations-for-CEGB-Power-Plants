import calendar
import pandas as pd
import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path

# ==============================================================================
# Inputs
PLANT_ID = "neyd06"
YEAR = 1982
MONTH = 1

BASE_DIR = Path(
    "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants"
)

PLANT_DATA_PATH = BASE_DIR / "data" / "final" / "your_plant_panel.csv"

KERNEL_PATH = (
    BASE_DIR
    / "data"
    / "final"
    / "sim_test"
    / "kernels"
    / "monthly"
    / f"kernel_{PLANT_ID}_{YEAR}{MONTH:02d}.nc"
)

OUT_PATH = (
    BASE_DIR
    / "code"
    / "testing"
    / "visualising"
    / f"{PLANT_ID}_{YEAR}{MONTH:02d}_monthly.png"
)

# ==============================================================================
# Read plant metadata
plants = pd.read_csv(PLANT_DATA_PATH)

rows = plants[plants["plant_id"] == PLANT_ID]
if rows.empty:
    raise ValueError(f"plant_id '{PLANT_ID}' not found in {PLANT_DATA_PATH}")

row = rows.iloc[0]
plant_name = str(row["plant_name"])
plant_lat = float(row["plant_lat"])
plant_lon = float(row["plant_long"])

# ==============================================================================
# Read monthly kernel
ds = xr.open_dataset(KERNEL_PATH)
kernel = ds["transport_kernel"]
data = kernel.values
masked = np.where(data > 0, data, np.nan)

# ==============================================================================
# Labels
month_name = calendar.month_abbr[MONTH]
title = f"{plant_name} monthly transport kernel — {month_name} {YEAR}"

# ==============================================================================
# Plot
fig, ax = plt.subplots(
    subplot_kw={"projection": ccrs.PlateCarree()},
    figsize=(8, 8)
)

ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
ax.add_feature(cfeature.BORDERS, linewidth=0.5)

im = ax.pcolormesh(
    kernel.longitude,
    kernel.latitude,
    np.log(masked),
    cmap="YlOrRd",
    transform=ccrs.PlateCarree(),
)

ax.plot(
    plant_lon,
    plant_lat,
    "b^",
    markersize=8,
    transform=ccrs.PlateCarree(),
    label=plant_name,
)

plt.colorbar(im, ax=ax, label="ln(transport kernel)", shrink=0.7)
ax.set_title(title)
ax.legend()

plt.tight_layout()
plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight")
plt.show()
