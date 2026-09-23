# HYSPLIT Simulations for CEGB Power Plants, 1973–1988

Code and documentation for the HYSPLIT dispersion simulations used to model
emissions from fossil-fuelled Central Electricity Generating Board (CEGB) power
stations in England and Wales between April 1973 and March 1988. The sample
contains 186 plants and 1,718 plant-years. The simulations
were run on Fedora Linux 44. Parts of this repository were written with Claude (Anthropic) under my direction and subsequently checked by me.

> [!NOTE]
> **Known gap: surface geopotential.** Stage 2 needs a static ERA5 terrain
> field, `data/raw/geopot/geopot.grib`: the surface geopotential from the
> `reanalysis-era5-single-levels` dataset. For the original run it was
> downloaded manually, not by `1_api_calls.py`, so no code in this repository
> currently produces it. `1_api_calls.py` will be updated to download it once.
> Until then, request the `geopotential` variable from
> `reanalysis-era5-single-levels` for a single time step, over the same area as
> the monthly files (`AREA` in `1_api_calls.py`), in GRIB format. The field
> does not change over time, so any date will do.

## Contents

- [What the code does](#what-the-code-does)
- [About this repository](#about-this-repository)
- [Pipeline overview](#pipeline-overview)
- [Installing HYSPLIT](#installing-hysplit)
- [Setting up](#setting-up): [on your own machine](#option-a-on-your-own-machine) or [in Docker](#option-b-docker-container)
- [Input data](#input-data)
- [Running the pipeline](#running-the-pipeline)
- [Runtime](#runtime)
- [Repository structure](#repository-structure)
- [Citing](#citing)

## What the code does

The role of HYSPLIT in the research design is described in the main paper, with
further details on the exposure methodology and calibration in Appendix B.

A simulation is run separately for each plant and financial year (April-March).
Each run releases tracer particles continuously at a constant unit rate from
00Z on 1 April to 00Z on 1 April of the following year. Concentrations are
recorded as daily means at 100 m above ground on a $0.05^\circ \times 0.05^\circ$ grid centred on $53^\circ$ N, $2^\circ$ W. Release height is adjusted for plume rise using HYSPLIT's Briggs scheme driven by the plant's sensible heat. 

HYSPLIT writes concentrations to a binary `cdump` file, which is converted to
NetCDF using HYSPLIT's `con2cdf4` utility. Daily mean concentrations are then
averaged over the financial year to produce an **annual transport kernel**: the
mean concentration in each output grid cell resulting from a unit emission rate
at that plant. The plant's annual fuel input is stored as an attribute of the
kernel but is not applied during the HYSPLIT simulation.

In the analysis in the paper, each annual transport kernel is scaled by the
corresponding plant's fuel input in that financial year. The scaled kernels are
then summed across plants within each fuel type to construct annual exposure
measures for coal-, oil-, and gas-turbine-fired generation. This is analogous to
HYSPLIT's transfer coefficient matrix (TCM) approach: atmospheric transport from
each source is simulated once at a constant unit emission rate and variation in
plant activity is then applied afterwards to the resulting concentration field via annual fuel input as a proxy for emissions intensity.

Two simulation inputs are estimated rather than directly observed and are
covered in more detail in the paper's Appendix B and are functions of either
maximum power plant capacity or annual-actual plant capacity, both of which
we have detailed information on. Missing stack heights are
imputed using a log-log regression of stack height on maximum plant capacity.
Sensible heat, which determines plume rise, is selected by calibration: all
plants operating in FY1981/82 are simulated at seven candidate heat values and
the value that best matches observed sulphur dioxide and black smoke
concentrations is selected. Sensible heat is a function of a plant's annual capacity and differs by fuel type.

Meteorology is taken from ERA5 reanalysis. The required fields are converted to
HYSPLIT's ARL format using HYSPLIT's `era52arl` tool. The meteorological data and
conversion procedure are described below.

## About this repository

The repository records the code and computing environment used for the
simulations. It is research code rather than maintained software, and the input
data are not currently distributed with it. 

**Please note: running this exact code is computationally expensive and took a**
**long time on my machine: 53.4 hours to download 11.6 GB of meteorological data**
**from the ERA5 API, 2.2 days for the ensemble runs, and 5.2 days for the full**
**simulation (see [Runtime](#runtime)). Thoroughly read this and all supporting**
**documentation before committing to the run.**

It may also be useful as a worked example for researchers who want to use
HYSPLIT for repeated point-source dispersion simulations but are unsure how to
structure the workflow. It shows one way of setting up HYSPLIT runs from Python,
running them in batches, and processing the resulting concentration output.

The simulation code is a small Python package, `hysplit`, in
`code/simulation/hysplit/`, built around three classes:

- `PlantYear` is one point source in one financial year: its location, stack
  height and fuel input.
- `HYSPLITRun` takes a `PlantYear` and its sensible heat, writes the `CONTROL`,
  `SETUP.CFG`, `ASCDATA.CFG` and `EMITIMES` files, runs HYSPLIT and converts
  the output to NetCDF.
- `AnnualKernel` averages that daily output into an annual transport kernel.

The batch runners, `ensemble_run.py` and `sim_run.py`, repeat this across
plant-years in parallel, logging each run and skipping any already complete.

The same code can be used for other point sources, given a source-year panel with
the columns below. The first five rows are the fields of a `PlantYear` whilst sensible heat is passed alongside it:

| Attribute | Panel column | Meaning | Used for |
| --- | --- | --- | --- |
| `plant_id`, `plant_name` | `plant_id`, `plant_name` | Unique plant identifier and plant name | Naming runs and outputs |
| `lat`, `lon` | `plant_lat`, `plant_long` | Latitude and longitude of the power station in decimal degrees | Source location |
| `stack_ht_m` | `max_stack_height_m` | Height of the tallest stack at the plant, in metres | HYSPLIT release height |
| `year_maj` | `year_maj` | First calendar year of the April-March financial year; e.g. `1981` denotes FY1981/82 | Simulation start date, run length, and selection of meteorological files |
| `fuel_input_gwh` | `fuel_input_gwh` | Total fuel input to the plant during the financial year, in GWh | Stored as an attribute of the annual kernel for later scaling; not used by HYSPLIT itself |
| sensible heat | `heat_w` | Sensible heat released with the plume, in watts | Briggs plume rise; written to `EMITIMES` |

---

## Pipeline overview

The pipeline has four stages:

| Stage | What it does | Code (in `code/`) | Main output |
| --- | --- | --- | --- |
| 1. Power plant data | Cleans the CEGB panel, computes fuel input and the sensible-heat values for plume rise, and imputes missing stack heights | `data_processing/power_plants/`<br>- `1_pp_cleaning.py`<br>- `2_stack_pred.py` | `data/final/cegb_panel_with_stacks.csv` |
| 2. Meteorology | Downloads ERA5 from the Copernicus Climate Data Store and converts it to HYSPLIT's ARL format | `data_processing/era5/`<br>- `1_api_calls.py`<br>- `2_merge_geopt.sh`<br>- `3_convert_arl.sh`<br>- `configs/era52arl_8lev_reference.cfg` | `data/final/arl/era5_YYYY_MM.arl` |
| 3. Plume-rise calibration | Runs a 7-member plume-rise ensemble for FY1981/82, selects the member per fuel type that best fits observed SO₂ and black smoke, and checks that FY1981/82 weather was representative of the study period | Ensemble: `simulation/ensemble_run.py`<br><br>Uses `simulation/hysplit/` package<br><br> Analysis: `data_processing/ensemble_runs/` <br>- `1_ensemble_treatment.py`<br>- `2_ensemble_assessment.py`<br><br>Weather check: `average_weather/`<br>- `1_merge_grib.sh`<br>- `2_extract_weather.py`<br>- `3_plot_weather.py` | Ensemble: `data/final/simulation_output/ensemble_1981/` (`runs/`, `kernels/`)<br>Analysis: `data/final/ensemble_stations.csv`, `plots/ensemble_within_r2.pdf`, and the selected members<br>Weather check: `data/final/merged_weather/`, `plots/weather_1981_82_comparison.pdf` |
| 4. Production simulations | Runs every plant-year with its selected plume rise and averages each run to an annual kernel | `simulation/`<br>- `sim_run.py`<br><br>Uses `simulation/hysplit/` package | `data/final/simulation_output/runs/` (one folder per plant-year)<br>`data/final/simulation_output/kernels/annual/` |

`simulation/backfil_kernels.py` is a one-off recovery script that also
validates the finished kernels (see `docs/authors_notes.md`).

---

## Installing HYSPLIT

HYSPLIT is needed whichever way the code is run (i.e. replication inside of the 
container, or as someone wanting to use this framework with HYSPLIT). NOAA 
distributes it only to registered users, so it is not included here. The 
simulations used **HYSPLIT v5.4.2 (May 2025)**, the Red Hat Enterprise Linux 9 
build.

1. **Download** `hysplit.v5.4.2_RHEL9.7_public.tar.gz` from
   [NOAA ARL](https://www.ready.noaa.gov/HYSPLIT.php) after registering.
2. **Check the download** against NOAA's published checksum. This prints `OK`
   for the same distribution (each Linux build has its own checksum):

   ```bash
   echo "de9b219723e7d648a5bd70f515fffb91ceef8cf5  hysplit.v5.4.2_RHEL9.7_public.tar.gz" | sha1sum -c
   ```

3. **Extract it** anywhere:

   ```bash
   tar -xzf hysplit.v5.4.2_RHEL9.7_public.tar.gz -C /path/of/your/choice
   ```

   The original installation was at
   `~/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public`.

The pipeline uses four HYSPLIT programs: `hycs_std` (the dispersion model),
`con2cdf4` (converts its output to NetCDF), and `era52arl` and `chk_file`
(convert ERA5 to HYSPLIT's format and check the result). It also uses the
land-use and roughness files in `bdyfiles/`.

The RHEL 9 build runs as it is on Fedora 44. On other Linux distributions,
NOAA's build for that system, or its statically linked `x86_64` build, should
run the same model, although the checksum above will not match.

---

## Setting up

The code can be run in two ways:

- **[Option A](#option-a-on-your-own-machine): directly on your own machine.**
  This is the usual route.
- **[Option B](#option-b-docker-container): in the Docker container.** This is
  a copy of the machine the simulations ran on, so no paths need changing. I also have a save of the specific docker image used at the time.

### Option A: on your own machine

**1. Python environment.** `cfpp_sim.yml` lists every package at the version
used:

```bash
conda env create -f cfpp_sim.yml
conda activate cfpp_sim
```

**2. System libraries.** The HYSPLIT programs rely on a few system libraries:
the Fortran runtime, NetCDF, HDF and eccodes. On Fedora, RHEL or Rocky:

```bash
sudo dnf install libgfortran libquadmath netcdf-fortran eccodes eccodes-data
```

If nothing is missing, this prints nothing:

```bash
cd /path/to/hysplit.v5.4.2_RHEL9.7_public/exec
ldd hycs_std con2cdf4 era52arl chk_file | grep "not found"
```

On the original machine, `ECCODES_DEFINITION_PATH` was also set to
`/usr/share/eccodes/definitions`.

**3. File paths.** The Python scripts find the repository by themselves. The
remaining machine-specific paths are two settings in
`code/simulation/hysplit/paths.py` and three shell scripts:

| Where | Setting | Points to |
| --- | --- | --- |
| `paths.py` | `HYSPLIT_DIR` | the HYSPLIT folder |
| `paths.py` | `DROPBOX_DIR` | a folder for the run logs (any folder) |
| `3_convert_arl.sh` | `HYSPLIT_ROOT` | the HYSPLIT folder |
| `2_merge_geopt.sh`, `3_convert_arl.sh`, `1_merge_grib.sh` | the `htest` link | the repository (see below) |

This lists every line concerned:

```bash
grep -rnIE "/home/chris|Path.home\(\)" code/ | grep -vE ":[0-9]+:\s*#"
```

A few points about these settings:

- If `HYSPLIT_DIR` is wrong, the runs stop straight away with an error. The
  check is there because HYSPLIT itself would not stop: without `bdyfiles/`
  it quietly uses default land-use and roughness values, and the results are
  wrong with no warning.
- The shell scripts reach the repository through a short link,
  `/home/chris/htest`, because HYSPLIT's conversion tools cannot handle long
  file paths. The repository's full paths are 92–136 characters; through the
  link the longest is 77. A replacement link needs a similarly short path.
- Some lines in `2_stack_pred.py`, `2_ensemble_assessment.py` and
  `3_plot_weather.py` are commented out. They copied figures and tables into
  the paper's Overleaf folder, and are kept only as a record.

### Option B: Docker container

The `Dockerfile` builds a copy of the machine the simulations were run on:
Fedora 44, the same system libraries, the `cfpp_sim` environment and HYSPLIT,
with the original user name and folder layout. The code therefore runs inside
it without any changes to paths.

**Building.** The build does not download HYSPLIT; it copies it in from wherever
it was extracted. From the repository root, with the HYSPLIT path filled in:

```bash
docker build \
  --build-arg UID=$(id -u) \
  --build-context hysplit=/path/to/hysplit.v5.4.2_RHEL9.7_public \
  -t cfpp-sim:paper .
```

The `UID` setting makes the files the container creates belong to your own
user. An error mentioning `pull access denied for hysplit` means the
`--build-context` line is missing. The build stops with a message if any
library HYSPLIT needs is missing. Because the image contains HYSPLIT, it should
not be shared publicly.

**Running.** Run this from the repository root:

```bash
docker run --rm -it \
  -v "$PWD":/home/chris/Documents/cfpp_hysplit/HYSPLIT-Simulations-for-CEGB-Power-Plants \
  -v ~/.cdsapirc:/home/chris/.cdsapirc:ro \
  cfpp-sim:paper
```

The command opens a shell inside the container, in the repository, with
`cfpp_sim` already active. Scripts are then run as in
[Running the pipeline](#running-the-pipeline). The `-v` flag bind-mounts the
repository into the container instead of copying it, so every output written
inside the repository (kernels, plots, tables) lands on the host disk and
persists. The `--rm` flag deletes the container itself on exit, so anything
written outside the repository does not persist.

The `~/.cdsapirc` mount makes the CDS API key readable inside the container (see
[ERA5 access](#era5-access)), since it lives outside of the repo directory. 
You will need to make sure this file path is set to where you have placed your
`.cdsapirc`. Stage 2 reads the token to download ERA5, so this
mount is included on every run.

In the original runs, the run logs were the only output written outside the 
repository. The batch runners write them to `DROPBOX_DIR` in `code/simulation/hysplit/paths.py`, which currently points to a Dropbox folder. Keeping the logs then needs a third mount, and the whole command looks like this instead:

```bash
docker run --rm -it \
  -v "$PWD":/home/chris/Documents/cfpp_hysplit/HYSPLIT-Simulations-for-CEGB-Power-Plants \
  -v ~/.cdsapirc:/home/chris/.cdsapirc:ro \
  -v ~/cfpp_logs:"/home/chris/Royal Holloway Dropbox/Chris Hockey/PhD/cfpp2/hysplit/hysplit_simulations/error_log" \
  cfpp-sim:paper
```
Create the host log folder once with `mkdir -p ~/cfpp_logs`.

Setting `DROPBOX_DIR` in `code/simulation/hysplit/paths.py` to a path inside the repository removes the need for the third mount because they are written inside of
the repo.

**Checking.** This prints `container OK` if everything the pipeline needs is in
the image: the libraries for all four HYSPLIT programs, the command-line tools
the shell scripts use, HYSPLIT's `bdyfiles/`, and the Python packages.

```bash
docker run --rm cfpp-sim:paper bash -c '
  set -e
  cd ~/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/exec
  ldd hycs_std con2cdf4 era52arl chk_file | grep "not found" && exit 1
  for t in grib_copy grib_get grib_set grib_count rm ln grep basename tee \
           realpath mktemp mkdir du cut cat wc head dirname cp; do
    command -v "$t" >/dev/null || { echo "missing: $t"; exit 1; }
  done
  ls ../bdyfiles "$ECCODES_DEFINITION_PATH" >/dev/null
  python -c "import numpy, pandas, xarray, matplotlib, statsmodels, cdsapi, pyfixest, netCDF4, cfgrib"
  echo "container OK"'
```

The `environment/` folder lists the exact version of everything in the image.

---

## Input data

### Files not included

`data/` is not part of the repository. The pipeline creates everything in it
except these inputs:

| File | Contents | Source |
| --- | --- | --- |
| `data/raw/cegb_panel.csv` | CEGB plant-year panel: location, capacity, fuel, output, thermal efficiency | Authors' own, will be on GitHub at some point, also distributed with the main paper's replication package |
| `data/raw/plant_stack_heights.csv` | Observed stack heights | Authors' own - will be distributed here |
| `data/raw/smokeso2_monthly.csv` | Monthly SO₂ and black smoke at monitoring stations, for calibration | Black Smoke and Sulphur Dioxide Network from the [UK Air Website](https://uk-air.defra.gov.uk/), also distributed from the main replication package |
| `data/raw/geopot/geopot.grib` | ERA5 surface geopotential (time-invariant), needed by `era52arl` for terrain height | ERA5, downloaded manually; see the note at the top |

### ERA5 access

Stage 2 downloads ERA5 from the Copernicus Climate Data Store (CDS), which needs
a free account:

1. Register at the [Copernicus Climate Data Store](https://cds.climate.copernicus.eu).
2. Accept the ERA5 licence in the web interface. Without this, downloads fail
   with a `403` error, which looks like a password problem but is not.
3. Save the API details in `~/.cdsapirc`:

   ```
   url: https://cds.climate.copernicus.eu/api
   key: <your-personal-access-token>
   ```

This file holds a personal token, so it stays outside the repository. The CDS
has changed its API details before; its
[documentation](https://cds.climate.copernicus.eu/how-to-api) has the current
form. The container uses the same file when it is added as in Option B. 
You will need to know the location of `.cdsapirc`, as it is needed when
creating the docker container (see [Option B: Docker Container](#option-b-docker-container)).

**Never share your personal access token.**

---

## Running the pipeline

Scripts are run from the repository root with `cfpp_sim` active (in the
container it already is), in the order below. Each stage uses the outputs of
the one before.

### Stage 1: power plant data

```bash
python code/data_processing/power_plants/1_pp_cleaning.py
python code/data_processing/power_plants/2_stack_pred.py
```

- `1_pp_cleaning.py` cleans the raw CEGB panel. It gives dual-fired plants a
  single fuel (oil in the 1984/85 miners' strike year, coal otherwise), derives
  each plant-year's fuel input from electricity supplied and thermal
  efficiency, and computes the seven candidate sensible-heat values used in
  stage 3, along with the selected one. It keeps fossil-fuel plant-years from
  FY1973/74 onwards with positive fuel input, and writes
  `data/intermediate/clean_cegb.csv`.
- `2_stack_pred.py` fills in missing stack heights using a log-log regression
  of stack height on maximum capacity, fitted on the plants with observed
  heights and checked by leave-one-out cross-validation. Imputed heights are
  flagged. It writes the panel used by the simulations,
  `data/final/cegb_panel_with_stacks.csv`, and the regression table to
  `tables/`.

### Stage 2: meteorology

```bash
python code/data_processing/era5/1_api_calls.py
bash   code/data_processing/era5/2_merge_geopt.sh
bash   code/data_processing/era5/3_convert_arl.sh
```

- `1_api_calls.py` downloads ERA5 from the Copernicus Climate Data Store: one
  file per month for 1973–1988, 6-hourly, over a box covering Britain. There
  are two files per month: one of fields on eight pressure levels between 700
  and 1000 hPa and one of surface fields. Files already downloaded are skipped,
  so it can be restarted after an interruption. This is ran in parallel purely to send as many API requests as possible to speed up the process.
- `2_merge_geopt.sh` adds terrain height (the static surface geopotential; see
  the note at the top) to every monthly surface file, one copy per time step,
  because `era52arl` expects it alongside the other surface fields.
- `3_convert_arl.sh` converts each month to HYSPLIT's ARL format with
  `era52arl`, using the variable and level settings in
  `configs/era52arl_8lev_reference.cfg`, and checks each converted file with
  `chk_file`. The results in `data/final/arl/` are the meteorology the
  simulations read.

**Downloading takes about two days.** In the original run, the 384 monthly
files (11.6 GiB) took 53 hours to arrive. The CDS queues each request and
prepares the data before sending it, so the time depends on how busy the CDS
is, not on connection speed.

ERA5 for this period is a final product, so the same request returns the same
data. ERA5 before 1979 comes from ECMWF's back extension, produced separately
from the post-1979 reanalysis and with different input observations. It covers
the first six financial years of the sample; the 1984/85 strike period is well
within the post-1979 data.

### Stage 3: plume-rise calibration

```bash
python code/simulation/ensemble_run.py
python code/data_processing/ensemble_runs/1_ensemble_treatment.py
python code/data_processing/ensemble_runs/2_ensemble_assessment.py
```

- `ensemble_run.py` runs HYSPLIT for every plant operating in FY1981/82 at each
  of the seven candidate heat values (105 plants × 7 = 735 simulations) and
  saves an annual kernel for each, in `data/final/simulation_output/ensemble_1981/`.
- `1_ensemble_treatment.py` computes each monitoring station's monthly exposure
  under each candidate: the concentration in the grid cell containing the
  station, scaled by each plant's fuel input and summed across plants,
  separately for each fuel type. It matches these to the observed monthly SO₂
  and black smoke readings and writes `data/final/ensemble_stations.csv`.
- `2_ensemble_assessment.py` regresses observed pollution on each candidate's
  exposure, with station and year-month fixed effects, for each fuel type and
  pollutant. It ranks the candidates by within R-squared, and plots the result to
  `plots/ensemble_within_r2.pdf`.

The candidate sensible heat for member *k* is `k_fuel × capacity (MW) × 10⁶`
watts:

| Member | k1 | k2 | k3 | k4 | k5 | k6 | k7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Coal | 0 | 0.03 | 0.06 | 0.09 | 0.12 | 0.15 | 0.18 |
| Oil | 0 | 0.039 | 0.078 | 0.117 | 0.156 | 0.195 | 0.234 |
| Gas turbine | 0 | 0.5 | 1 | 1.5 | 2 | 2.5 | 3 |

`k1` means no plume rise. The selected members are coal k2, oil k2 and gas
turbine k6. They are set in `SELECTED_MEMBER` in `1_pp_cleaning.py`, which
writes the chosen heat to the panel's `heat_w` column. The ensemble itself uses
all seven candidate columns, so the stages run once, in order; stage 1 only
needs re-running if a different selection is made.

#### Weather check

```bash
bash   code/average_weather/1_merge_grib.sh
python code/average_weather/2_extract_weather.py
python code/average_weather/3_plot_weather.py
```

These check that the calibration year's weather was typical of the sample
period, using the files from stage 2.

- `1_merge_grib.sh` joins the monthly surface files into one file for
  1973–1988, and extracts temperature and wind at 925 hPa from the
  pressure-level files into another.
- `2_extract_weather.py` crops these to England and saves them as NetCDF, in
  three files: surface fields, precipitation, and 925 hPa temperature and wind.
  925 hPa (roughly 750–800 m) is kept because it is about where plume rise
  places the plume.
- `3_plot_weather.py` averages each field over the area (weighting by
  latitude, and summing precipitation), groups the results by month and
  financial year, and plots FY1981/82 against every other year:
  `plots/weather_1981_82_comparison.pdf`.

### Stage 4: production simulations

```bash
python code/simulation/sim_run.py
```

- `sim_run.py` runs HYSPLIT for all 1,718 plant-years with their selected
  heat, ten at a time, and saves one annual kernel per plant-year in
  `data/final/simulation_output/kernels/annual/`. Finished kernels are skipped,
  so an interrupted batch can be restarted, and setting `N_JOBS` limits a test
  to the first few jobs.
- `backfil_kernels.py` was a one-off: it built kernels from simulations that
  had finished but not been saved (see the `docs/authors_notes.md`).

The simulation code itself is the `hysplit` package described in
[About this repository](#about-this-repository): `plant.py`, `run.py` and
`kernel.py` define its three classes, and `paths.py` holds every file path and
simulation setting, such as the grid, the sampling interval and the number of
particles.

---

## Runtime

The simulations were run on one desktop machine: an AMD Ryzen 5 5600X (6 cores,
12 threads) with 32 GB of memory, running Fedora Linux 44. HYSPLIT uses one core
per simulation, so simulations were run ten at a time. A single simulation took
about 43 minutes, and the full set of 2,453 (1,718 production and 735
calibration) took about 7.4 days. More detail is `docs/authors_notes.md`.

---

## Repository structure

```
.
├── cfpp_sim.yml                  conda environment, exact versions
├── Dockerfile                    snapshot of the original machine
├── .dockerignore                 limits what Docker reads from the repository
├── environment/                  exact versions of everything in the Docker image
├── configs/
│   └── era52arl_8lev_reference.cfg   ERA5 → ARL variable and level mapping
├── docs/
│   └── authors_notes.md          record of the original: run, runtime, ER5 & fixes
└── code/
    ├── data_processing/
    │   ├── power_plants/         stage 1: CEGB panel, heat values, stack heights
    │   ├── era5/                 stage 2: download, add terrain, convert to ARL
    │   └── ensemble_runs/        stage 3: station exposure and member selection
    ├── simulation/
    │   ├── hysplit/              package: paths and parameters, PlantYear,
    │   │                         HYSPLITRun, AnnualKernel
    │   ├── ensemble_run.py       stage 3: FY1981/82 plume-rise ensemble
    │   ├── sim_run.py            stage 4: production simulations
    │   └── backfil_kernels.py    one-off recovery of 112 kernels, plus validation
    └── average_weather/          stage 3: weather check
```

Created by the pipeline and not version-controlled:

```
data/
├── raw/            cegb_panel.csv, plant_stack_heights.csv, smokeso2_monthly.csv,
│                   pressures/, singles/, geopot/
├── intermediate/   clean_cegb.csv, singles_merged/, merged GRIB for the weather check
└── final/
    ├── cegb_panel_with_stacks.csv    the simulation input
    ├── arl/                          monthly ARL meteorology
    ├── ensemble_stations.csv         station-month calibration panel
    ├── merged_weather/               weather-check NetCDF
    └── simulation_output/
        ├── runs/                     one directory per plant-year
        ├── kernels/annual/           production kernels
        └── ensemble_1981/            calibration runs and kernels
plots/, tables/                       figures and tables
```

---

## Citing

For the methodology, please cite the paper:

> [TODO: Authors] ([year]). *[Title]*. [Working paper / journal]. [Link]

If you use or adapt the code, please also cite this repository: see
`CITATION.cff`, or GitHub's "Cite this repository" button.

HYSPLIT and ERA5 should be cited in their own right:

- Stein, A. F., Draxler, R. R., Rolph, G. D., Stunder, B. J. B., Cohen, M. D.
  and Ngan, F. (2015). NOAA's HYSPLIT atmospheric transport and dispersion
  modeling system. *Bulletin of the American Meteorological Society*, 96(12),
  2059–2077. https://doi.org/10.1175/BAMS-D-14-00110.1
- Hersbach, H. et al. (2020). The ERA5 global reanalysis. *Quarterly Journal of
  the Royal Meteorological Society*, 146(730), 1999–2049.
  https://doi.org/10.1002/qj.3803

Contains modified Copernicus Climate Change Service information, 2026.

[TODO: licence.]
