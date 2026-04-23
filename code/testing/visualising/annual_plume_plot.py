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
YEAR_MAJ = 1982

BASE_DIR = Path(
    "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants"
)


PANEL_PATH = BASE_DIR / "data" / "final" / "cegb_panel_with_stacks.csv"
KERNEL_PATH = (
    BASE_DIR
    / "data"
    / "final"
    / "sim_test"
    / "kernels"
    / "annual"
    / f"kernel_{PLANT_ID}_{YEAR_MAJ}.nc"
)

# ==============================================================================
# Read plant metadata
df = pd.read_csv(PANEL_PATH)

rows = df[df["plant_id"] == PLANT_ID]
if rows.empty:
    raise ValueError(f"plant_id '{PLANT_ID}' not found in {PANEL_PATH}")

row = rows.iloc[0]

plant_name = str(row["plant_name"])
plant_lat = float(row["plant_lat"])
plant_lon = float(row["plant_long"])

# Financial year label, e.g. 1974 -> 1974/75
fy_label = f"{YEAR_MAJ}/{str(YEAR_MAJ + 1)[-2:]}"

# ==============================================================================
# Read kernel
ds = xr.open_dataset(KERNEL_PATH)
kernel = ds["transport_kernel"]
data = kernel.values

masked = np.where(data > 0, data, np.nan)

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
ax.set_title(f"{plant_name} annual transport kernel — FY {fy_label}")
ax.legend()

plt.tight_layout()
plt.show()
