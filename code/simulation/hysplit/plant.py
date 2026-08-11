"""
Plant-year observation from the CEGB panel.

`PlantYear` stores all attributes for a power plant in a given financial
year: time-invariant fields (id, name, location, stack height) plus the
year-specific fuel input. Constructed from the CEGB panel via
`PlantYear.from_panel()`, which reads the CSV once.

`calendar_months()` returns the 12 (calendar_year, calendar_month) pairs
for the financial year, April `year_maj` through March `year_maj + 1`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .paths import PANEL_PATH

# ==============================================================================


@dataclass
class PlantYear:
    """
    A power plant observed in a given financial year.

    Time-invariant fields (plant_id, plant_name, lat, lon, stack_ht_m) and
    the year-specific fuel input are read together from a single panel row.
    """
    plant_id: str
    plant_name: str
    lat: float
    lon: float
    stack_ht_m: float
    year_maj: int
    fuel_input_gwh: float

    @classmethod
    def from_panel(
        cls,
        plant_id:   str,
        year_maj:   int,
        panel_path: Path = PANEL_PATH,
    ) -> PlantYear:
        """
        Construct a `PlantYear` from the CEGB panel with a single CSV read.

        Raises `ValueError` if the plant is not in the panel at all, or if
        it is in the panel but absent in `year_maj`.
        """
        df = pd.read_csv(panel_path)
        plant_rows = df[df["plant_id"] == plant_id]
        if plant_rows.empty:
            raise ValueError(
                f"plant_id '{plant_id}' not found in {panel_path}"
            )
        year_rows = plant_rows[plant_rows["year_maj"] == year_maj]
        if year_rows.empty:
            raise ValueError(
                f"plant_id '{plant_id}' has no data for year_maj "
                f"{year_maj} in {panel_path}. Plant may not have "
                f"been operating that year."
            )
        row = year_rows.iloc[0]
        return cls(
            plant_id=str(row["plant_id"]),
            plant_name=str(row["plant_name"]),
            lat=float(row["plant_lat"]),
            lon=float(row["plant_long"]),
            stack_ht_m=float(row["max_stack_height_m"]),
            year_maj=int(year_maj),
            fuel_input_gwh=float(row["fuel_input_gwh"]),
        )

    def calendar_months(self) -> list[tuple[int, int]]:
        """
        12 (calendar_year, calendar_month) pairs for this financial year:
        April `year_maj` through March `year_maj + 1`.
        """
        months: list[tuple[int, int]] = []
        for m in range(4, 13):          # April–December of year_maj
            months.append((self.year_maj, m))
        for m in range(1, 4):           # January–March of year_maj+1
            months.append((self.year_maj + 1, m))
        return months
