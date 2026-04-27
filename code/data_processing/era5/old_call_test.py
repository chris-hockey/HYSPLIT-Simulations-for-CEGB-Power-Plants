# /tmp/old_call_test.py — exact old API call, just one year:
import cdsapi
import os
os.makedirs('/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/tmp/old_call_test', exist_ok=True)
c = cdsapi.Client()

c.retrieve("reanalysis-era5-pressure-levels", {
    "product_type": ["reanalysis"],
    "variable": ["geopotential", "temperature", "u_component_of_wind",
                 "v_component_of_wind", "vertical_velocity", "relative_humidity"],
    "year": ["1974"],
    "month": [f"{m:02d}" for m in range(1, 13)],
    "day": [f"{d:02d}" for d in range(1, 32)],
    "time": ["00:00", "06:00", "12:00", "18:00"],
    "pressure_level": ["700", "850", "925", "1000"],
    "data_format": "grib", "download_format": "unarchived",
    "area": [56.01297, -5.903322, 49.883132, 2.006834],
}).download('/tmp/old_call_test/era5_pl_1974.grib')

c.retrieve("reanalysis-era5-single-levels", {
    "product_type": ["reanalysis"],
    "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind",
                 "2m_temperature", "surface_pressure", "total_precipitation",
                 "surface_latent_heat_flux", "surface_sensible_heat_flux",
                 "total_cloud_cover", "boundary_layer_height"],
    "year": ["1974"],
    "month": [f"{m:02d}" for m in range(1, 13)],
    "day": [f"{d:02d}" for d in range(1, 32)],
    "time": ["00:00", "06:00", "12:00", "18:00"],
    "data_format": "grib", "download_format": "unarchived",
    "area": [56.01297, -5.903322, 49.883132, 2.006834],
}).download('/tmp/old_call_test/era5_sfc_an_1974.grib')
