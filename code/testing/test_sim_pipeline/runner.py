"""
Production runner — executes AnnualKernel for all plant-years in the
panel within the specified year_maj range.
Skips already-completed plant-years via already_done() check.
"""
from pathlib import Path

import pandas as pd

from hysplit import PlantYear, AnnualKernel
from hysplit.paths import PANEL_PATH


# --- configuration ---
YEAR_MAJ_MIN = 1981
YEAR_MAJ_MAX = 1985


def main() -> None:
    df = pd.read_csv(PANEL_PATH)
    plant_years = (
        df[
            (df["year_maj"] >= YEAR_MAJ_MIN) &
            (df["year_maj"] <= YEAR_MAJ_MAX)
        ][["plant_id", "year_maj"]]
        .drop_duplicates()
        .sort_values(["year_maj", "plant_id"])
        .reset_index(drop=True)
    )

    n_total = len(plant_years)
    print(f"Plant-years to run: {n_total}")
    print(f"Range: {YEAR_MAJ_MIN}–{YEAR_MAJ_MAX}\n")

    completed = 0
    failed = []

    for i, row in plant_years.iterrows():
        plant_id = str(row["plant_id"])
        year_maj = int(row["year_maj"])
        tag = f"[{i+1}/{n_total}] {plant_id} {year_maj}"

        try:
            plant_year = PlantYear.from_panel(plant_id, year_maj)
            kernel = AnnualKernel(plant_year=plant_year)
            kernel.execute()
            completed += 1
            print(f"✓ {tag}")
        except Exception as e:
            failed.append((plant_id, year_maj, str(e)))
            print(f"✗ {tag}: {e}")
            continue

    print(f"\n{'='*50}")
    print(f"Completed: {completed}/{n_total}")
    print(f"Failed:    {len(failed)}")
    if failed:
        print("\nFailures:")
        for pid, yr, err in failed:
            print(f"  {pid} {yr}: {err}")


if __name__ == "__main__":
    main()
