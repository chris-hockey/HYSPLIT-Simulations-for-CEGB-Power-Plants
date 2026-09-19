"""
Plot monthly weather in the calibration year against all other years in the
study period, to assess meteorological representativeness.

Takes the cropped NetCDF fields from 2_extract_weather.py, forms
latitude-weighted spatial means over the domain (sums for precipitation),
aggregates to months, and reorganises onto April-March financial years. Six
variables are plotted, each showing `TARGET_YEAR` highlighted against the
remaining years in grey.

Output: weather_YYYY_YY_comparison.pdf in plots/ and the Overleaf technical
appendix plot directory.

Author: Christopher Hockey
chrishockey2@gmail.com
August 2026
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.axes import Axes

# ==============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data" / "final" / "merged_weather"
PLOT_DIR = PROJECT_ROOT / "plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

# Used to send outputs to the overleaf doc to write the paper
# OVERLEAF_PLOT_DIR = Path(
#     "/home/chris/Royal Holloway Dropbox/Chris Hockey/Apps/Overleaf/"
#     "Coal Power and Infant Health/Technical Appendix/Plots"
# )

TARGET_YEAR = 1981


# ==============================================================================


def monthly_spatial_mean(da: xr.DataArray) -> xr.DataArray:
    """
    Calculate latitude-weighted spatial mean over the domain of cells in a
    xr.DataArray, then calculate the monthly mean of these
    """
    weights = np.cos(np.deg2rad(da.latitude))

    area_mean = da.weighted(weights).mean(
        dim=("latitude", "longitude")
    )

    monthly = area_mean.resample(time="MS").mean(dim="time")

    return monthly


def monthly_spatial_precip(da: xr.DataArray) -> xr.DataArray:
    """
    Calculate latitude-weighted spatial mean total precipitation, then sum to
    monthly totals
    """
    weights = np.cos(np.deg2rad(da.latitude))

    area_mean = da.weighted(weights).mean(
        dim=("latitude", "longitude")
    )

    area_mean = area_mean.stack(observation=("time", "step"))
    area_mean = area_mean.reset_index("observation")
    area_mean = area_mean.swap_dims({"observation": "valid_time"})
    area_mean = area_mean.drop_vars(["time", "step"])
    area_mean = area_mean.rename({"valid_time": "time"})

    monthly = (area_mean * 1000).resample(time="MS").sum(dim="time")

    return monthly


def to_financial_year(da: xr.DataArray) -> pd.DataFrame:
    """
    Convert monthly data to April-March financial years used in the HYSPLIT
    simulations
    """
    df = da.to_dataframe(name="value").reset_index()

    df["month"] = df["time"].dt.month
    df["calendar_year"] = df["time"].dt.year

    # Jan-March belonging to the financial year beginning in the previous
    # calendar year
    df["financial_year"] = np.where(
        df["month"] >= 4,
        df["calendar_year"],
        df["calendar_year"] - 1,
    )

    df["financial_year_month"] = np.where(
        df["month"] < 4,
        df["month"] + 9,
        df["month"] - 3,
    )

    return df


def plot_variable(
    ax: Axes,
    df: pd.DataFrame,
    title: str,
    ylabel: str,
) -> None:
    """ 
    Plot monthly means of chosen year against remaining monthly years of data
    """

    # comparison years
    for fyear, group in df.groupby("financial_year"):
        group = group.sort_values("financial_year_month")

        if fyear == TARGET_YEAR:
            continue

        ax.plot(
            group["financial_year_month"],
            group["value"],
            color="0.75",
            alpha=0.7,
        )

    # Plot 1981/82 on top
    target = (
        df[df["financial_year"] == TARGET_YEAR]
        .sort_values("financial_year_month")
    )

    ax.plot(
        target["financial_year_month"],
        target["value"],
        linewidth=2.5,
        label=f"Financial year {TARGET_YEAR}/{(TARGET_YEAR + 1) % 100:02d}",
    )

    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(
        ["Apr", "May", "Jun", "Jul", "Aug", "Sep",
         "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    )

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.2)


# ==============================================================================
# load processed weather data
# ==============================================================================
instant = xr.open_dataset(
    DATA_DIR / "instant_singles.nc", decode_timedelta=False,)

precip = xr.open_dataset(DATA_DIR / "total_precip.nc", decode_timedelta=False,)

pres = xr.open_dataset(DATA_DIR / "pressure_925_tuv.nc",
                       decode_timedelta=False,)


# ==============================================================================
# construct monthly variables
# ==============================================================================

variables = {
    "2 m temperature": {
        "data": monthly_spatial_mean(instant["t2m"] - 273.15),
        "ylabel": "Temperature (°C)",
    },
    "Boundary-layer height": {
        "data": monthly_spatial_mean(instant["blh"]),
        "ylabel": "Boundary-layer height (m)",
    },
    "10 m wind speed": {
        "data": monthly_spatial_mean(
            np.hypot(
                instant["u10"],
                instant["v10"],
            )
        ),
        "ylabel": "Wind speed (m/s)",
    },
    "925 hPa temperature": {
        "data": monthly_spatial_mean(pres["t"] - 273.15),
        "ylabel": "Temperature (°C)",
    },
    "925 hPa wind speed": {
        "data": monthly_spatial_mean(
            np.hypot(
                pres["u"],
                pres["v"],
            )
        ),
        "ylabel": "Wind speed (m/s)",
    },
    "Total precipitation": {
        "data": monthly_spatial_precip(precip["tp"]),
        "ylabel": "Total precipitation (mm)",
    },
}


# ==============================================================================
# plot
# ==============================================================================

fig, axes = plt.subplots(
    3,
    2,
    figsize=(12, 10),
)

axes = axes.flatten()

for ax, (title, spec) in zip(axes, variables.items()):
    df = to_financial_year(spec["data"])

    plot_variable(
        ax=ax,
        df=df,
        title=title,
        ylabel=spec["ylabel"],
    )

handles, labels = axes[0].get_legend_handles_labels()

fig.legend(
    handles,
    labels,
    loc="lower center",
    frameon=False,
)

fig.tight_layout(rect=(0, 0.05, 1, 1))

plt.show()


# ==============================================================================

out = PLOT_DIR / \
    f"weather_{TARGET_YEAR}_{(TARGET_YEAR + 1) % 100:02d}_comparison.pdf"

fig.savefig(
    out,
    bbox_inches="tight",
)


# out_overleaf = OVERLEAF_PLOT_DIR / \
#     f"weather_{TARGET_YEAR}_{(TARGET_YEAR + 1) % 100:02d}_comparison.pdf"

# fig.savefig(
#     out_overleaf,
#     bbox_inches="tight",
# )
