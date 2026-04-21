"""
Classes for representing static plant attributes and plant-year observations
from the CEGB panel.

`Plant` stores time-invariant plant characteristics such as name, location,
and stack height. It can be constructed from the CEGB panel using the
`Plant.from_panel()` class method.

`PlantYear` stores plant-year-specific information, right now just fuel input
for a given financial year. It can be constructed from the CEGB panel using the
`PlantYear.from_panel()` class method, which raises an error if the plant is
not present in the specified year.

The `PlantYear.calendar_months()` method returns the 12 calendar year-month
pairs corresponding to the financial year, running from April of `year_maj`
through March of `year_maj + 1`.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .paths import PANEL_PATH


@dataclass
class Plant:
    """
    Static attributes of a power plant.

    These attributes are assumed to be invariant across years, including plant
    name, location, and maximum stack height.
    """
    plant_id:   str
    plant_name: str
    lat:        float
    lon:        float
    stack_ht_m: float

    @classmethod
    def from_panel(
        cls,
        plant_id:   str,
        panel_path: Path = PANEL_PATH,
    ) -> Plant:
        """
        Construct a `Plant` from the CEGB panel.

        Uses the first row matching `plant_id` and reads fields assumed to be
        time-invariant.
        """
        df = pd.read_csv(panel_path)
        rows = df[df["plant_id"] == plant_id]
        if rows.empty:
            raise ValueError(
                f"plant_id '{plant_id}' not found in {panel_path}"
            )
        row = rows.iloc[0]
        return cls(
            plant_id=str(row["plant_id"]),
            plant_name=str(row["plant_name"]),
            lat=float(row["plant_lat"]),
            lon=float(row["plant_long"]),
            stack_ht_m=float(row["max_stack_height_m"]),
        )


@dataclass
class PlantYear:
    """
    A power plant observed in a given financial year.

    Stores the plant's static attributes together with year-specific fuel input.
    Also provides the calendar months corresponding to the financial year, which
    runs from April of `year_maj` through March of `year_maj + 1`.
    """
    plant:          Plant
    year_maj:       int
    fuel_input_gwh: float

    @classmethod
    def from_panel(
        cls,
        plant_id:   str,
        year_maj:   int,
        panel_path: Path = PANEL_PATH,
    ) -> PlantYear:
        """
        Construct a `PlantYear` from the CEGB panel.

        Loads the observation for `plant_id` in `year_maj`. Raises `ValueError` if
        the plant is not present in that financial year.
        """
        df = pd.read_csv(panel_path)
        rows = df[
            (df["plant_id"] == plant_id) &
            (df["year_maj"] == year_maj)
        ]
        if rows.empty:
            raise ValueError(
                f"plant_id '{plant_id}' not found for year_maj "
                f"{year_maj} in {panel_path}. Plant may not have "
                f"been operating that year."
            )
        row = rows.iloc[0]
        plant = Plant.from_panel(plant_id, panel_path)
        fuel_input_gwh = float(row["fuel_input_gwh"])
        return cls(
            plant=plant,
            year_maj=year_maj,
            fuel_input_gwh=fuel_input_gwh,
        )

    def calendar_months(self) -> list[tuple[int, int]]:
        """
        Return the 12 (calendar_year, calendar_month) pairs for this
        financial year in order: April year_maj through March year_maj+1.
        """
        months = []
        for m in range(4, 13):          # April–December of year_maj
            months.append((self.year_maj, m))
        for m in range(1, 4):           # January–March of year_maj+1
            months.append((self.year_maj + 1, m))
        return months
