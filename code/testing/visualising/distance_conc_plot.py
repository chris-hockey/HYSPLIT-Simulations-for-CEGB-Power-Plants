import xarray as xr
import numpy as np
import matplotlib.pyplot as plt

# --- inputs ---
nc_path = "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/final/sim_test/kernels/monthly/kernel_neyd06_198204.nc"
src_lat = 53.736437     # plant lat
src_lon = 0.995907     # plant lon
var_name = None        # e.g. "TCM"; set to None to auto-pick first data var


# --- load ---
ds = xr.open_dataset(nc_path)
# inspect once, then hardcode var_name
print(ds)
if var_name is None:
    var_name = list(ds.data_vars)[0]
C = ds[var_name].squeeze()                  # drop singleton time/level dims
# if time remains, take mean or sum:
if "time" in C.dims:
    # monthly-mean (linear, so mean == sum/N)
    C = C.mean("time")

lats = C["latitude"].values if "latitude" in C.coords else C["lat"].values
lons = C["longitude"].values if "longitude" in C.coords else C["lon"].values

# --- haversine distance from source to every grid cell (km) ---
R = 6371.0
LAT, LON = np.meshgrid(lats, lons, indexing="ij")
phi1, phi2 = np.radians(src_lat), np.radians(LAT)
dphi = np.radians(LAT - src_lat)
dlam = np.radians(LON - src_lon)
a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlam/2)**2
D = 2 * R * np.arcsin(np.sqrt(a))

# --- flatten, drop zeros (log scale) ---
c = np.asarray(C.values).ravel()
d = D.ravel()
m = c > 0
c, d = c[m], d[m]

# --- binned median as a guide line through the cloud ---
bins = np.logspace(np.log10(max(d.min(), 1)), np.log10(d.max()), 25)
idx = np.digitize(d, bins)
bin_d = np.array([d[idx == i].mean() if (idx == i).any()
                 else np.nan for i in range(1, len(bins))])
bin_c = np.array([np.median(c[idx == i]) if (idx == i).any()
                 else np.nan for i in range(1, len(bins))])

# --- plot ---
fig, ax = plt.subplots(figsize=(6, 5))
ax.scatter(d, c, s=3, alpha=0.25, label="grid cells")
ax.plot(bin_d, bin_c, "-", lw=2, label="binned median")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("Distance from source (km)")
ax.set_ylabel(f"Concentration ({ds[var_name].attrs.get('units','')})")
ax.set_title("Plume decay: concentration vs. distance from source")
ax.legend()
plt.tight_layout()
plt.show()
