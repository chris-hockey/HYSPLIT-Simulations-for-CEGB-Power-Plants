import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path

# -------------------------------------------------------------------
# plant inputs: path, fuel input, lon, lat, label
# replace fuel_input_gwh values with the correct plant-year values
# -------------------------------------------------------------------
plants = [
    {
        "name": "Drax",
        "path": Path("/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/final/sim_test/runs/neyd29_1974/01/day_01/cdump_neyd29_197501_d01.nc"
                     ),
        "fuel_input_gwh": 12838.7423402393,
        "lon": -0.995907,
        "lat": 53.736437,
    },
    {
        "name": "Cowes",
        "path": Path("/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/final/sim_test/runs/swsd02_1974/01/day_01/cdump_swsd02_197501_d01.nc"
                     ),
        "fuel_input_gwh": 53.4602076124568,
        "lon": -1.287575,   # fill in
        "lat": 50.745368,   # fill in
    },
    {
        "name": "Castle Donington",
        "path": Path("/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/final/sim_test/runs/mdemd01_1974/01/day_01/cdump_mdemd01_197501_d01.nc"
                     ),
        "fuel_input_gwh": 6526.88329363729,
        "lon": -1.358511,   # fill in
        "lat": 52.847769,   # fill in
    },
]


scaled_fields = []
lons = None
lats = None

for p in plants:
    ds = xr.open_dataset(p["path"])
    conc = ds["TEST"].isel(levels=0, time=0)
    scaled = conc * p["fuel_input_gwh"]
    scaled_fields.append(scaled.values)

    if lons is None:
        lons = conc.longitude.values
        lats = conc.latitude.values

    ds.close()

combined = np.sum(scaled_fields, axis=0)
masked = np.where(combined > 0, combined, np.nan)

fig, ax = plt.subplots(
    figsize=(8, 8),
    subplot_kw={"projection": ccrs.PlateCarree()}
)

ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
ax.add_feature(cfeature.BORDERS, linewidth=0.5)

im = ax.pcolormesh(
    lons,
    lats,
    np.log(masked),
    cmap="YlOrRd",
    transform=ccrs.PlateCarree(),
)

for p in plants:
    ax.plot(
        p["lon"], p["lat"], "^", markersize=7,
        transform=ccrs.PlateCarree(), label=p["name"]
    )

plt.colorbar(
    im, ax=ax, label="log(fuel-scaled concentration proxy)", shrink=0.7)
ax.set_title("Combined fuel-scaled daily concentration fields")
ax.legend()
plt.tight_layout()
plt.show()
