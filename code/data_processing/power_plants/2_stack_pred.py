"""
Impute stack heights via log-log OLS: ln(H) = alpha + beta * ln(capacity)
Validates via LOO cross-validation, imputes missing, writes to final.
"""

import logging
from pathlib import Path
import time

import numpy as np
import pandas as pd
import statsmodels.api as sm

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
logging.Formatter.converter = time.localtime
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
INT_DIR = PROJECT_ROOT / "data" / "intermediate"
OUT_DIR = PROJECT_ROOT / "data" / "final"
OUT_DIR.mkdir(exist_ok=True, parents=True)

COL_STACK = "max_stack_height_m"
COL_CAPACITY = "max_cap_mw"
COL_PLANT_ID = "plant_id"

# ------------------------------------------------------------------------------
# Load and deduplicate to one row per plant

cfpp = pd.read_csv(INT_DIR / "clean_cegb.csv")
stack_raw = pd.read_csv(RAW_DIR / "plant_stack_heights.csv")

panel_ids = set(cfpp[COL_PLANT_ID].unique())

plants = (
    stack_raw[stack_raw[COL_PLANT_ID].isin(panel_ids)]
    .sort_values([COL_PLANT_ID, COL_STACK], na_position="last")
    .groupby(COL_PLANT_ID, as_index=False)
    .first()
)

n_with_stack = plants[COL_STACK].notna().sum()
n_missing = plants[COL_STACK].isna().sum()
log.info("Plants in sample: %d  |  observed: %d  |  missing: %d",
         len(plants), n_with_stack, n_missing)

assert n_with_stack >= 3, "Too few observed stack heights to estimate."
assert plants.loc[plants[COL_STACK].notna(), COL_CAPACITY].gt(0).all(), \
    "Non-positive capacity in observed sample."

# ------------------------------------------------------------------------------
# OLS: ln(H) = alpha + beta * ln(capacity)

obs = plants.dropna(subset=[COL_STACK]).copy()
obs["ln_H"] = np.log(obs[COL_STACK])
obs["ln_capacity"] = np.log(obs[COL_CAPACITY])

X = sm.add_constant(obs["ln_capacity"])
y = obs["ln_H"]

result = sm.OLS(y, X).fit()
log.info("\n%s", result.summary())

alpha_hat = result.params["const"]
beta_hat = result.params["ln_capacity"]
log.info("z = exp(alpha): %.4f  |  beta: %.4f", np.exp(alpha_hat), beta_hat)

# ------------------------------------------------------------------------------
# LOO cross-validation on observed subsample

n = len(obs)
loo_errors = np.empty(n)

for i in range(n):
    mask = np.ones(n, dtype=bool)
    mask[i] = False
    loo_fit = sm.OLS(y.iloc[mask], X.iloc[mask]).fit()
    loo_errors[i] = loo_fit.predict(X.iloc[[i]]).item() - y.iloc[i]

loo_rmse = np.sqrt(np.mean(loo_errors ** 2))
loo_mape = np.mean(np.abs(np.expm1(loo_errors))) * 100
log.info("LOO-CV  |  RMSE (log): %.4f  |  MAPE (level): %.1f%%",
         loo_rmse, loo_mape)

# ------------------------------------------------------------------------------
# Impute

missing_mask = plants[COL_STACK].isna()
plants["stack_height_imputed"] = missing_mask

plants.loc[missing_mask, COL_STACK] = (
    np.exp(alpha_hat) * plants.loc[missing_mask, COL_CAPACITY] ** beta_hat
)

assert plants[COL_STACK].notna().all()
assert plants[COL_STACK].gt(0).all()

# ------------------------------------------------------------------------------
cfpp = cfpp.merge(
    plants[[COL_PLANT_ID, COL_STACK, "stack_height_imputed"]],
    on=COL_PLANT_ID,
    how="left"
)

assert cfpp[COL_STACK].notna().all(
), "Some panel rows have no stack height after merge."

panel_path = OUT_DIR / "cegb_panel_with_stacks.csv"
cfpp.to_csv(panel_path, index=False)
log.info("Wrote panel with stack heights: %d rows, %d plants to %s",
         len(cfpp), cfpp[COL_PLANT_ID].nunique(), panel_path)
