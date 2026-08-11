"""
Clean power plant data to the sample of plants used in HYSPLIT simulations.
"""

import logging
import time
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.Formatter.converter = time.localtime
log = logging.getLogger(__name__)


# ==============================================================================
# paths and constants
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUT_DIR = PROJECT_ROOT / "data" / "intermediate"
OUT_DIR.mkdir(exist_ok=True, parents=True)

PLANT_TYPES = ["coal", "oil", "gt"]

# Fuel-category coefficients for HEAT ensemble runs.
K_COAL = (0, 0.03, 0.06, 0.09, 0.12, 0.15, 0.18)
K_OIL = (0, 0.039, 0.078, 0.117, 0.156, 0.195, 0.234)
K_GT = (0, 0.5, 1, 1.5, 2, 2.5, 3)

assert len(K_COAL) == len(K_OIL) == len(K_GT), (
    "Fuel grids must be co-indexed (of equal length)."
)

K_BY_FUEL = {
    "coal": K_COAL,
    "oil": K_OIL,
    "gt": K_GT,
}


# ==============================================================================
cfpp = pd.read_csv(RAW_DIR / "cegb_panel.csv")
cfpp["fuel_cat"] = cfpp["fuel_cat"].astype(str)


# ==============================================================================
# resolve fuel categories

# treat dual-fired plants as oil in the strike year (1984/85) and coal in all
# other years.
mask_strike = cfpp["fuel_cat"].eq("df") & cfpp["year_maj"].eq(1984)
n_strike = mask_strike.sum()

if n_strike:
    cfpp.loc[mask_strike, "fuel_cat"] = "oil"
    log.info("Reclassified df->oil (strike 1984/85): %d rows", n_strike)

mask_coal = cfpp["fuel_cat"].eq("df")
n_coal = mask_coal.sum()

if n_coal:
    cfpp.loc[mask_coal, "fuel_cat"] = "coal"
    log.info("Reclassified df->coal (non-strike): %d rows", n_coal)


# ==============================================================================
# construct plant-year variables

# zero output where efficiency is missing and clamp negative output to zero.
missing_efficiency = (
    cfpp["electricity_supplied_gwh"].notna()
    & cfpp["thermal_efficiency_pct"].isna()
)
cfpp.loc[missing_efficiency, "electricity_supplied_gwh"] = 0

cfpp["electricity_supplied_gwh"] = cfpp["electricity_supplied_gwh"].clip(
    lower=0
)

cfpp = cfpp.rename(
    columns={
        "long": "plant_long",
        "lat": "plant_lat",
        "electricity_supplied_gwh": "gwh_output",
    }
)

cfpp["thermal_efficiency_prop"] = cfpp["thermal_efficiency_pct"] / 100

cfpp["fuel_input_gwh"] = (
    cfpp["gwh_output"] / cfpp["thermal_efficiency_prop"]
).where(
    cfpp["thermal_efficiency_prop"] > 0,
    0.0,
)


# ==============================================================================
# construct HEAT ensemble variables

# sensible heat (W) per plant-year:
# HEAT_k = k_fuel × capacity_MW × 1e6.
for m in range(len(K_COAL)):
    coeff = cfpp["fuel_cat"].map(
        {fuel: grid[m] for fuel, grid in K_BY_FUEL.items()}
    )
    cfpp[f"heat_w_k{m + 1}"] = (
        coeff * cfpp["dec_gross_cap_mw_gen"] * 1e6
    )


# ==============================================================================
# restrict sample to year_maj 1973 onwards and only coal (and df), oil, gt

cfpp_trimmed = (
    cfpp[
        (cfpp["year_maj"] >= 1973)
        & cfpp["fuel_cat"].isin(PLANT_TYPES)
        & (cfpp["fuel_input_gwh"].fillna(0) > 0)
    ]
    .drop_duplicates(subset=["plant_id", "year_maj"])
    .copy()
)

log.info(
    "Plants across sample (year_maj >= 1973, fossil fuel only): %d",
    cfpp_trimmed["plant_id"].nunique(),
)


# ==============================================================================
out_path = OUT_DIR / "clean_cegb.csv"
cfpp_trimmed.to_csv(out_path, index=False)
