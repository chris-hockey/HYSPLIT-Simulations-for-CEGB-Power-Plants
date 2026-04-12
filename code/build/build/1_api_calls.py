import os
import cdsapi


PRESSURE_DIR = "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/raw/pressures"
SINGLES_DIR = "/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plantsdata/raw/singles"

os.makedirs(PRESSURE_DIR, exist_ok=True)
os.makedirs(SINGLES_DIR, exist_ok=True)
PRESSURE_DATASET = "reanalysis-era5-pressure-levels"
SINGLES_DATASET = "reanalysis-era5-single-levels"
years = [str(y) for y in range(1983, 1988)]

client = cdsapi.Client()

for year in years:

    # ------------------------------------------------------------------
    # FILE 1: pressure level 3D fields
    # ------------------------------------------------------------------
    client.retrieve(PRESSURE_DATASET, {
        "product_type": ["reanalysis"],
        "variable": [
            "geopotential",
            "temperature",
            "u_component_of_wind",
            "v_component_of_wind",
            "vertical_velocity",
            "relative_humidity"
        ],
        "year": [year],
        "month": ["01", "02", "03", "04", "05", "06",
                  "07", "08", "09", "10", "11", "12"],
        "day":   [f"{d:02d}" for d in range(1, 32)],
        "time":  ["00:00", "06:00", "12:00", "18:00"],
        "pressure_level": ["700", "850", "925", "1000"],
        "data_format": "grib",
        "download_format": "unarchived",
        "area": [56.01297, -5.903322, 49.883132, 2.006834]
    }).download(os.path.join(PRESSURE_DIR, f"era5_pl_{year}.grib"))
    print(f"Pressure levels done: {year}")

    # ------------------------------------------------------------------
    # FILE 2: analysis surface fields (instantaneous)
    # ------------------------------------------------------------------
    client.retrieve(SINGLES_DATASET, {
        "product_type": ["reanalysis"],
        "variable": [
            "10m_u_component_of_wind",
            "10m_v_component_of_wind",
            "2m_temperature",
            "surface_pressure",
            "total_precipitation",
            "surface_latent_heat_flux",
            "surface_sensible_heat_flux",
            "total_cloud_cover",
            "boundary_layer_height"
        ],
        "year": [year],
        "month": ["01", "02", "03", "04", "05", "06",
                  "07", "08", "09", "10", "11", "12"],
        "day":   [f"{d:02d}" for d in range(1, 32)],
        "time":  ["00:00", "06:00", "12:00", "18:00"],
        "data_format": "grib",
        "download_format": "unarchived",
        "area": [56.01297, -5.903322, 49.883132, 2.006834]
    }).download(os.path.join(SINGLES_DIR, f"era5_sfc_an_{year}.grib"))
    print(f"Surface analysis done: {year}")

print("All done.")
