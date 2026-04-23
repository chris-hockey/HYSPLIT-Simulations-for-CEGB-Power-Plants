import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

ds = xr.open_dataset(
    "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/final/sim_test/kernels/monthly/kernel_neyd06_198204.nc")
C = ds[list(ds.data_vars)[0]].squeeze()
if "time" in C.dims:
    C = C.mean("time")

src_lat, src_lon = 53.7355, -0.9975  # Drax

fig, ax = plt.subplots(figsize=(8, 7))
# mask zeros for log scale
Cm = C.where(C > 0)
im = ax.pcolormesh(C["longitude"], C["latitude"], Cm,
                   norm=LogNorm(vmin=1e-15, vmax=Cm.max().item()),
                   cmap="viridis", shading="auto")
ax.scatter(src_lon, src_lat, marker="x", c="red", s=80, label="Drax")
# distance rings at 25, 50, 100, 200 km
for r_km in [25, 50, 100, 200]:
    theta = np.linspace(0, 2*np.pi, 200)
    dlat = (r_km/111.0)*np.cos(theta)
    dlon = (r_km/(111.0*np.cos(np.radians(src_lat))))*np.sin(theta)
    ax.plot(src_lon+dlon, src_lat+dlat, "w--", lw=0.6, alpha=0.6)
plt.colorbar(im, label="concentration")
ax.set_aspect("equal")
ax.set_xlabel("lon")
ax.set_ylabel("lat")
ax.legend()
plt.tight_layout()
plt.show()
