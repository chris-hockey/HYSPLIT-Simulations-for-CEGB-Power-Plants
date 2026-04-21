import os
import subprocess
import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# --- paths ---
HYSPLIT_EXEC = os.path.expanduser(
    "~/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/exec/con2cdf4"
)
CDUMP_PATH = os.path.expanduser(
    "~/htest/data/final/concentration/fedora_cdump_drax_197401"
)
NC_PATH = CDUMP_PATH + ".nc"

# --- convert cdump to NetCDF if not already done ---
if not os.path.exists(NC_PATH):
    print("Converting cdump to NetCDF...")
    result = subprocess.run(
        [HYSPLIT_EXEC, CDUMP_PATH, NC_PATH],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"con2cdf4 failed:\n{result.stderr}")
    print("Done.")
else:
    print(f"NetCDF already exists, skipping conversion.")

# --- load ---
ds = xr.open_dataset(NC_PATH)
print(ds)

# single level (100m AGL), all 31 daily time slices
conc = ds['TEST'].isel(levels=0)  # shape: (time, lat, lon)

# monthly average — mean over daily slices
monthly_avg = conc.mean(dim='time')

print(f"\nDaily slices:    {conc.shape[0]}")
print(f"Grid shape:      {conc.shape[1:]}")
print(f"Non-zero cells:  {(monthly_avg.values > 0).sum()}")
print(f"Max cell value:  {monthly_avg.values.max():.4e}")
print(
    f"Mean (nonzero):  {monthly_avg.values[monthly_avg.values > 0].mean():.4e}")

# --- plot ---
fig, ax = plt.subplots(
    subplot_kw={'projection': ccrs.PlateCarree()},
    figsize=(8, 8)
)

ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
ax.add_feature(cfeature.BORDERS, linewidth=0.5)

data_masked = np.where(monthly_avg.values > 0, monthly_avg.values, np.nan)

im = ax.pcolormesh(
    monthly_avg.longitude,
    monthly_avg.latitude,
    np.log10(data_masked),
    cmap='YlOrRd',
    transform=ccrs.PlateCarree()
)

ax.plot(-0.995907, 53.736437, 'b^', markersize=8,
        transform=ccrs.PlateCarree(), label='Drax')

plt.colorbar(im, ax=ax, label='log10(mean daily concentration)', shrink=0.7)
ax.set_title(
    'Drax transport kernel — January 1974\n(monthly average, 100m AGL)')
ax.legend()
plt.tight_layout()

out_plot = os.path.expanduser(
    "~/htest/data/final/concentration/drax_197401_monthly_avg.png"
)
plt.savefig(out_plot, dpi=150)
plt.show()
print(f"Saved to {out_plot}")
