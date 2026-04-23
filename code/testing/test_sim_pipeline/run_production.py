# run_production.py
from pathlib import Path
import pandas as pd
from hysplit import PlantYear, AnnualKernel

PANEL = Path(
    "/home/chris/Documents/hysplit_test/"
    "HYSPLIT-Simulations-for-CEGB-Power-Plants/"
    "data/final/cegb_panel_with_stacks.csv"
)

df = pd.read_csv(PANEL)
plant_years = df[["plant_id", "year_maj"]].drop_duplicates()

for _, row in plant_years.iterrows():
    plant_id = row["plant_id"]
    year_maj = int(row["year_maj"])

    try:
        plant_year = PlantYear.from_panel(plant_id, year_maj)
        kernel = AnnualKernel(plant_year=plant_year)
        result = kernel.execute()
        print(f"✓ {plant_id} {year_maj}")
    except Exception as e:
        print(f"✗ {plant_id} {year_maj}: {e}")
        continue
