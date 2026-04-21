import time

from hysplit import PlantYear, AnnualKernel

start = time.time()

PLANT_ID = "mdemd01"
YEAR_MAJ = 1974

plant_year = PlantYear.from_panel(
    plant_id=PLANT_ID,
    year_maj=YEAR_MAJ,
)

print(
    f"Plant:        {plant_year.plant.plant_name}\n"
    f"Lat:          {plant_year.plant.lat}\n"
    f"Lon:          {plant_year.plant.lon}\n"
    f"Stack:        {plant_year.plant.stack_ht_m}m\n"
    f"Year maj:     {plant_year.year_maj}\n"
    f"Fuel input:   {plant_year.fuel_input_gwh} GWh\n"
    f"Cal. months:  {plant_year.calendar_months()}\n"
)

kernel = AnnualKernel(plant_year=plant_year)
result = kernel.execute()

if result:
    print(f"\nDone. Annual kernel at: {result}")

elapsed = time.time() - start
print(f"Total time: {elapsed/60:.1f} minutes")
