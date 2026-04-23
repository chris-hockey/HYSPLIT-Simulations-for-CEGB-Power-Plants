from hysplit import PlantYear, MonthlyKernel

PLANT_ID = "sest05"
YEAR_MAJ = 1974
CAL_YEAR = 1975
CAL_MONTH = 1

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
)

kernel = MonthlyKernel(
    plant=plant_year.plant,
    year_maj=YEAR_MAJ,
    year=CAL_YEAR,
    month=CAL_MONTH,
)
result = kernel.execute(overwrite=True)

if result:
    print(f"\nDone. Monthly kernel at: {result}")

# rm /home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/final/sim_test/kernels/monthly/kernel_neyd29_197501.nc
# rm -rf /home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/final/sim_test/runs/neyd29_1974/01
