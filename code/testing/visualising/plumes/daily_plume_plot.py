import pandas as pd
import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path

# ==============================================================================
# Inputs
PLANT_ID = "neyd29"
YEAR_MAJ = 1982
YEAR = 1983
MONTH = "01"
DAY = "01"

BASE_DIR = Path(
    "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants"
)

PLANT_DATA_PATH = BASE_DIR / "data" / "final" / "cegb_panel_with_stacks.csv"

NC_PATH = (
    BASE_DIR
    / "data"
    / "final"
    / "sim_test"
    / "runs"
    / f"{PLANT_ID}_{YEAR_MAJ}"
    / MONTH
    / f"day_{DAY}"
    / f"cdump_{PLANT_ID}_{YEAR}{MONTH}_d{DAY}.nc"
)

OUT_PATH = (
    BASE_DIR
    / "code"
    / "testing"
    / "visualising"
    / f"{PLANT_ID}_{YEAR_MAJ}{MONTH}{DAY}_daily.png"
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
# Read concentration data
ds = xr.open_dataset(NC_PATH)
conc = ds["TEST"].isel(levels=0, time=0)

data = conc.values
masked = np.where(data > 0, data, np.nan)

# Avoid warnings from log(0) / log(nan)
log_masked = np.log(masked)

# ==============================================================================
# Plot
fig, ax = plt.subplots(
    subplot_kw={"projection": ccrs.PlateCarree()},
    figsize=(8, 8)
)

ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
ax.add_feature(cfeature.BORDERS, linewidth=0.5)

im = ax.pcolormesh(
    conc.longitude,
    conc.latitude,
    log_masked,
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

plt.colorbar(im, ax=ax, label="ln(concentration)", shrink=0.7)
ax.set_title(
    f"{plant_name} single-day kernel — {int(DAY)} {MONTH} {YEAR_MAJ + 1} (72h)"
)
ax.legend()

plt.tight_layout()
plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight")
plt.show()
