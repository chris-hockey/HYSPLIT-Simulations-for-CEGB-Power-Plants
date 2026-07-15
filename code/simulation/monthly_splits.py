# one plant-year, auto-picked from what actually ran, then look at it
from hysplit import PlantYear, HYSPLITRun
from hysplit.monthly_kernel import build_monthly_kernel
from hysplit.paths import RUNS_DIR
import xarray as xr

# pick the first run folder that has a daily cdump (override by hand if you like)
run_dir = next(
    d for d in sorted(RUNS_DIR.iterdir())
    if d.is_dir() and (d / f"cdump_{d.name}.nc").exists()
)
plant_id, year_maj = run_dir.name.rsplit("_", 1)
py = PlantYear.from_panel(plant_id, int(year_maj))
print(f"testing {py.plant_id} ({py.plant_name}) FY{py.year_maj}")

# check the time convention on the daily source before trusting the split
t0 = xr.open_dataset(HYSPLITRun(plant_year=py).nc_path).time.values[0]
print("first daily stamp:", t0, "-> end-stamped, offset OK"
      if str(t0)[8:10] == "02" else "-> START-stamped, FLIP _MID_OFFSET sign")

p = build_monthly_kernel(py, overwrite=True)

ds = xr.open_dataset(p)
# dims: month(12), latitude, longitude
print(ds)
# 1974xx..1975xx, day-counts ~28-31
print(ds.month.values, ds.n_records.values)
