import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path

KERNEL_PATH = Path(
    "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/final/sim_test/kernels/monthly/kernel_mdemd01_197501.nc"
)

ds = xr.open_dataset(KERNEL_PATH)
kernel = ds["transport_kernel"]
data = kernel.values

fig, ax = plt.subplots(
    subplot_kw={"projection": ccrs.PlateCarree()},
    figsize=(8, 8)
)
ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
ax.add_feature(cfeature.BORDERS,   linewidth=0.5)

masked = np.where(data > 0, data, np.nan)

im = ax.pcolormesh(
    kernel.longitude,
    kernel.latitude,
    np.log(masked),
    cmap="YlOrRd",
    transform=ccrs.PlateCarree(),
)
ax.plot(
    -1.358511, 52.847769,
    "b^", markersize=8,
    transform=ccrs.PlateCarree(),
    label="Drax"
)
plt.colorbar(im, ax=ax, label="ln(transport kernel)", shrink=0.7)
ax.set_title("Castle Donnington monthly transport kernel — Jan 1975")
ax.legend()
plt.tight_layout()
plt.savefig("/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/code/testing/visualising/castled_monthly.png")
plt.show()
