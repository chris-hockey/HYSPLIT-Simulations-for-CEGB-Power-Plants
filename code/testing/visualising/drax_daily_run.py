import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path

# single day cdump
NC_PATH = Path(
    "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/final/sim_test/runs/mdemd01_1974/01/day_01/cdump_mdemd01_197501_d01.nc"
)

ds = xr.open_dataset(NC_PATH)
conc = ds["TEST"].isel(levels=0, time=0)
data = conc.values
masked = np.where(data > 0, data, np.nan)

fig, ax = plt.subplots(
    subplot_kw={"projection": ccrs.PlateCarree()},
    figsize=(8, 8)
)
ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
ax.add_feature(cfeature.BORDERS,   linewidth=0.5)

im = ax.pcolormesh(
    conc.longitude, conc.latitude,
    np.log(masked),
    cmap="YlOrRd",
    transform=ccrs.PlateCarree(),
)
ax.plot(-1.287575, 50.745368, "b^", markersize=8,
        transform=ccrs.PlateCarree(), label="Drax")
plt.colorbar(im, ax=ax, label="ln(concentration)", shrink=0.7)
ax.set_title("Castle Donnington single day kernel — 1 January 1975 (72h)")
ax.legend()
plt.tight_layout()
plt.savefig("/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/code/testing/visualising/castled_daily.png")
plt.show()
