"""
Assess plume-rise ensemble runs against observed pollution concentrations at
monitoring stations.

For each fuel type and candidate plume-rise parameter k, estimate a two-way
fixed-effects regression of observed monthly pollution on HYSPLIT-derived 
exposure, using the station-month panel written by `ensemble_treatment.py`
(`data/final/ensemble_stations.csv`). Candidate values of k are ranked by within
R2.

Regression coefficients and within correlations are retained as diagnostics:
the coefficient sign checks whether simulated exposure is associated with
observed pollution in the expected direction, while within R2 remains the
parameter-selection criterion.

Outputs a 3x2 panel of within R2 profiles (fuel type by pollutant), saved as
`ensemble_within_r2.pdf` to `plots/` and to the Overleaf technical appendix plot
directory, and prints the full diagnostics table to stdout.

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyfixest as pf

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# PyFixest drops singleton fixed effects by default: suppress the repeated
# warning generated when the same singleton groups are removed across the
# ensemble regressions
warnings.filterwarnings(
    "ignore",
    message=r".*singleton fixed effect.*",
    category=UserWarning,
)


# ==============================================================================
# paths and settings
# ==============================================================================

POLLUTION_DATA = (
    PROJECT_ROOT / "data" / "final" / "ensemble_stations.csv"
)
PLOT_DIR = PROJECT_ROOT / "plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

# Used to send outputs to the overleaf doc to write the paper
# OVERLEAF_PLOT_DIR = Path(
#     "/home/chris/Royal Holloway Dropbox/Chris Hockey/Apps/Overleaf/"
#     "Coal Power and Infant Health/Technical Appendix/Plots"
# )

FUELS = ("coal", "oil", "gt")
MEMBERS = [f"k{i}" for i in range(1, 8)]

OUTCOMES = {
    "monthly_mean_so2_ugm3": "Monthly mean SO2 (µg/m³)",
    "monthly_mean_bs_ugm3": "Monthly mean black smoke (µg/m³)",
}

FUEL_LABELS = {
    "coal": "Coal",
    "oil": "Oil",
    "gt": "Gas turbine",
}

# minimum share of days in the month with a reading
COV_MIN = 0.8
COV_COLS = {
    "monthly_mean_so2_ugm3": "monthly_cov_so2",
    "monthly_mean_bs_ugm3": "monthly_cov_bs",
}

# ==============================================================================
# estimate fixed-effects calibration regressions
# ==============================================================================

monthly = pd.read_csv(POLLUTION_DATA)

e_cols = [
    c
    for c in monthly.columns
    if c.startswith("e_")
]

# HYSPLIT exposure values are numerically very small, so rescale them to improve
# numerical conditioning. Multiplying a regressor by a constant changes the
# coefficient's units but does not change its within R2 or correlation
monthly[e_cols] *= 1e8

rows = []

for ycol in OUTCOMES:
    # coverage differs by pollutant, so the sample is formed per outcome
    est = monthly.loc[monthly[COV_COLS[ycol]] >= COV_MIN]
    print(
        f"{ycol}: {len(est):,} of {len(monthly):,} station-months at "
        f"coverage >= {COV_MIN:.0%}"
    )
    for fuel in FUELS:
        for member in MEMBERS:
            xcol = f"e_{fuel}_{member}"

            # Estimate:
            #
            #   pollution_st = alpha_s + gamma_t
            #                  + beta_k exposure_st^k + error_st
            #
            # where alpha_s are monitoring-station fixed effects and gamma_t
            # are month fixed effects
            fit = pf.feols(
                f"{ycol} ~ {xcol} | station_id + ym",
                data=est,
            )

            beta = fit.coef().loc[xcol]
            within_r2 = fit._r2_within

            # With one exposure regressor after absorbing the fixed effects,
            # signed sqrt(within R2) equals the correlation between pollution
            # and exposure after both have been residualised on the fixed
            # effects.
            #
            # Retained only as a diagnostic: within R2 is the criterion
            # used to select k and is reported in the technical appendix
            within_corr = (
                np.sign(beta)
                * np.sqrt(max(within_r2, 0))
            )

            rows.append(
                {
                    "spec": ycol,
                    "fuel": fuel,
                    "member": member,
                    "beta": beta,
                    "within_r2": within_r2,
                    "within_corr": within_corr,
                    "nobs": fit._N,
                }
            )

res = pd.DataFrame(rows)


# ==============================================================================
# plot within R2 across plume-rise parameters
# ==============================================================================

fig, axes = plt.subplots(
    3,
    2,
    figsize=(12, 10),
    sharex=True,
)

x = range(1, len(MEMBERS) + 1)

for i, fuel in enumerate(FUELS):
    for j, (ycol, ylab) in enumerate(OUTCOMES.items()):
        ax = axes[i, j]

        sub = res.loc[
            (res["fuel"] == fuel)
            & (res["spec"] == ycol)
        ]

        wr2 = (
            sub
            .set_index("member")
            .loc[MEMBERS, "within_r2"]
        )

        # plot within R2 for each candidate value of k
        ax.plot(
            x,
            wr2,
            color=f"C{i}",
            marker="o",
            markersize=3,
        )

        # highlight the candidate with the largest within R2
        peak = wr2.idxmax()
        peak_x = MEMBERS.index(peak) + 1

        ax.plot(
            peak_x,
            wr2[peak],
            color=f"C{i}",
            marker="o",
            markersize=7,
            markerfacecolor="white",
        )

        ax.set_xticks(
            range(1, len(MEMBERS) + 1),
            MEMBERS,
        )

        ax.set_ylabel(r"Within $R^2$")
        ax.grid(alpha=0.2)

        if i == 0:
            ax.set_title(ylab)

        if j == len(OUTCOMES) - 1:
            ax.text(
                1.03,
                0.5,
                FUEL_LABELS[fuel],
                transform=ax.transAxes,
                rotation=270,
                va="center",
            )

        # report the number of observations actually retained by PyFixest
        # after missing values and singleton fixed effects are removed
        nobs = sub["nobs"].iloc[0]

        ax.text(
            0.5,
            0.03,
            f"N = {nobs:,}",
            transform=ax.transAxes,
            ha="center",
            fontsize=8,
        )

fig.supxlabel(
    "Ensemble member (k1 = no plume rise, k7 = strongest)"
)

fig.tight_layout()

plt.show()


# ==============================================================================
# save figure
# ==============================================================================
fig.savefig(
    PLOT_DIR / "ensemble_within_r2.pdf",
    bbox_inches="tight",
)

# fig.savefig(
#     OVERLEAF_PLOT_DIR / "ensemble_within_r2.pdf",
#     bbox_inches="tight",
# )

# ==============================================================================
# diagnostic output
# ==============================================================================

# print the full regression diagnostics for reproducibility. beta is retained
# to verify that simulated exposure is positively associated with
# observed pollution
diagnostics = res[
    [
        "spec",
        "fuel",
        "member",
        "beta",
        "within_corr",
        "within_r2",
        "nobs",
    ]
].copy()

print(
    diagnostics.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)
