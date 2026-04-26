"""
Cleans power plant data to sample of power plants to simulate with
"""

import logging
from pathlib import Path
import time

import pandas as pd

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
logging.Formatter.converter = time.localtime
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUT_DIR = PROJECT_ROOT / "data" / "intermediate"
OUT_DIR.mkdir(exist_ok=True, parents=True)

PLANT_TYPES = ["coal", "df", "oil", "gt"]
STRIKE_YEARS = {1984}

# ------------------------------------------------------------------------------

cfpp = pd.read_csv(RAW_DIR / "cegb_panel.csv")
cfpp["fuel_cat"] = cfpp["fuel_cat"].astype(str)

# Reclassify dual-fired plants as oil in strike years
mask_strike = cfpp["fuel_cat"].eq("df") & cfpp["year_maj"].isin(STRIKE_YEARS)
n_reclass = mask_strike.sum()
if n_reclass:
    cfpp.loc[mask_strike, "fuel_cat"] = "oil"
    log.info("Reclassified df->oil in strike years: %d rows", n_reclass)

# Zero out output where efficiency is missing, clamp negatives
cfpp.loc[cfpp["electricity_supplied_gwh"].notna(
) & cfpp["thermal_efficiency_pct"].isna(), "electricity_supplied_gwh"] = 0
cfpp["electricity_supplied_gwh"] = cfpp["electricity_supplied_gwh"].clip(
    lower=0)

cfpp = cfpp.rename(columns={"long": "plant_long", "lat": "plant_lat",
                            "electricity_supplied_gwh": "gwh_output"})

cfpp["thermal_efficiency_prop"] = cfpp["thermal_efficiency_pct"] / 100
cfpp["fuel_input_gwh"] = (cfpp["gwh_output"] / cfpp["thermal_efficiency_prop"]
                          ).where(cfpp["thermal_efficiency_prop"] > 0, 0.0)

cfpp_trimmed = (
    cfpp[
        (cfpp["year_maj"] >= 1973)
        & (cfpp["fuel_cat"].isin(PLANT_TYPES))
        & (cfpp["fuel_input_gwh"].fillna(0) > 0)
    ]
    .drop_duplicates(subset=["plant_id", "year_maj"])
    .copy()
)
cfpp_trimmed = cfpp_trimmed[cfpp_trimmed["fuel_cat"].isin(PLANT_TYPES)]
log.info("Plants across sample (year_maj >= 1973, fossil fuel only): %d",
         cfpp_trimmed["plant_id"].nunique())

out_vs_path = OUT_DIR / "clean_cegb.csv"
cfpp_trimmed.to_csv(out_vs_path, index=False)
