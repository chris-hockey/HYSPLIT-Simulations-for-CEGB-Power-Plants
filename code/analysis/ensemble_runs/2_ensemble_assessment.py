"""
Assess plume-rise ensemble runs against observed pollution concentrations at
monitoring stations.

For each fuel type and candidate plume-rise parameter k, estimate a two-way
fixed-effects regression of observed monthly pollution on HYSPLIT-derived 
exposure, using the station-month panel written by `ensemble_treatment.py`
(`data/final/ensemble_stations.csv`). Candidate values of k are ranked by within
R2.

Station-months enter the sample when at least `COV_MIN` of the month's days
carry a reading, applied to the pollutant being explained. A monthly mean built
from three days is mostly noise, and it would otherwise weigh on the ranking as
heavily as a mean built from thirty.

Regression coefficients and within correlations are retained as diagnostics:
the coefficient sign checks whether simulated exposure is associated with
observed pollution in the expected direction, while within R2 remains the
parameter-selection criterion.

Outputs a 3x2 panel of within R2 profiles (fuel type by pollutant), saved as
`ensemble_within_r2.pdf` to `outputs/` and prints the full diagnostics table to 
stdout.

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
OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MEMBERS = [f"k{i}" for i in range(1, 8)]

FUELS = ("coal", "oil", "gt")

OUTCOMES = {
    "monthly_mean_so2_ugm3": "Monthly mean SO2 (µg/m³)",
    "monthly_mean_bs_ugm3": "Monthly mean black smoke (µg/m³)",
}

# Minimum share of the month's days with a reading, matching the coverage rule
# used in the main analysis. Set to 0 to estimate on every station-month
COV_MIN = 0.75

COV_COLS = {
    "monthly_mean_so2_ugm3": "monthly_cov_so2",
    "monthly_mean_bs_ugm3": "monthly_cov_bs",
}

FUEL_LABELS = {
    "coal": "Coal",
    "oil": "Oil",
    "gt": "Gas turbine",
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
# selection criterion
# ==============================================================================

def criterion(fuel: str) -> pd.Series:
    """
    Total within R2 across the two pollutants, by ensemble member.

    Each pollutant enters once, so the member that explains the most variation
    across both monitors is selected. Adding the two is a ranking device rather
    than a quantity with an interpretation of its own.
    """
    return (
        res.loc[res["fuel"] == fuel]
        .pivot(index="member", columns="spec", values="within_r2")
        .loc[MEMBERS]
        .sum(axis=1)
    )


# the margin over the runner-up says whether a selection is sharp or a tie
selection = pd.DataFrame(
    [
        {
            "fuel": fuel,
            "selected": criterion(fuel).idxmax(),
            "total_within_r2": criterion(fuel).max(),
            "margin_over_runner_up": (
                criterion(fuel).max()
                / criterion(fuel).drop(index=criterion(fuel).idxmax()).max()
                - 1
            ),
        }
        for fuel in FUELS
    ]
)


# ==============================================================================
# plot within R2 across plume-rise parameters
# ==============================================================================

fig, axes = plt.subplots(
    3,
    3,
    figsize=(16, 10),
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

    # third column: the quantity the selection rule reads
    ax = axes[i, 2]
    tot = criterion(fuel)

    ax.plot(x, tot, color=f"C{i}", marker="o", markersize=3)

    peak = tot.idxmax()
    ax.plot(
        MEMBERS.index(peak) + 1,
        tot[peak],
        color=f"C{i}",
        marker="o",
        markersize=7,
        markerfacecolor="white",
    )

    ax.set_xticks(range(1, len(MEMBERS) + 1), MEMBERS)
    ax.set_ylabel(r"Sum of within $R^2$")
    ax.grid(alpha=0.2)

    if i == 0:
        ax.set_title("Selection criterion")

    # how far the selected member stands above the next best
    margin = selection.loc[selection["fuel"] == fuel, "margin_over_runner_up"]
    ax.text(
        0.5,
        0.03,
        f"{peak}, ahead by {float(margin.iloc[0]):.1%}",
        transform=ax.transAxes,
        ha="center",
        fontsize=8,
    )

    ax.text(
        1.03,
        0.5,
        FUEL_LABELS[fuel],
        transform=ax.transAxes,
        rotation=270,
        va="center",
    )

fig.supxlabel(
    "Ensemble member (k1 = no plume rise, k7 = strongest)\n"
    f"Station-months with at least {COV_MIN:.0%} of days measured"
)

fig.tight_layout()

plt.show()


# ==============================================================================
# save figure
# ==============================================================================
fig.savefig(
    OUTPUT_DIR / "ensemble_within_r2.pdf",
    bbox_inches="tight",
)

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

print()
print(
    selection.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)
