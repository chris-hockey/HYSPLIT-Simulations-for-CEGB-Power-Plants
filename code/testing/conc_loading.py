# autopep8: off
import sys
sys.path.insert(0, '/home/chris/hysplit/python/hysplitdata')
import hysplitdata
import numpy as np
import xarray as xr
import pandas as pd
import rioxarray
# autopep8: on

cdump = hysplitdata.read_cdump(
    '/home/chris/Documents/hysplit_test/data/final/concentration/cdump_drax_197401')

dates = [g.ending_datetime for g in cdump.grids]
conc_stack = np.stack([g.conc for g in cdump.grids], axis=0)

da = xr.DataArray(
    conc_stack,
    dims=["time", "lat", "lon"],
    coords={
        "time": pd.DatetimeIndex(dates),
        "lat": cdump.latitudes,
        "lon": cdump.longitudes
    }
)

da_monthly = da.sum(dim="time")
da_monthly = da_monthly.rio.set_spatial_dims(x_dim="lon", y_dim="lat")
da_monthly = da_monthly.rio.write_crs("EPSG:4326")

da_monthly.rio.to_raster(
    "/home/chris/Documents/hysplit_test/data/final/concentration/drax_197401_monthly.tif"
)
