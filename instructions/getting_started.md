# HYSPLIT Setup on Fedora 43
**Project:** HYSPLIT Simulations for CEGB Power Plants  
**Date:** April 2026  
**Status:** hycs_std working. era52arl blocked — see Section 4.

---

## Overview (by Claude)

This document records everything done to install HYSPLIT and set up the
ERA5-to-ARL conversion pipeline on a fresh Fedora 43 machine. It covers
what was done, why each decision was made, and the exact terminal commands
used. It is intended to be fully reproducible from scratch.

---

## 1. Installing HYSPLIT

### 1.1 Why the "All Linux" static binary?

NOAA distributes HYSPLIT in four variants:

| Variant | Target |
|---|---|
| Ubuntu 20.04 | Debian-based, GCC 9 |
| RHEL 8 / CentOS 8 | RPM-based, GCC 8 |
| RHEL 9 / Rocky 9 | RPM-based, GCC 11 |
| All Linux (experimental) | Statically linked, any x86_64 |

Fedora 43 ships GCC 15 and glibc 2.41 — significantly newer than any of
the three OS-specific targets. The OS-specific binaries are *dynamically
linked*, meaning they rely on the exact library versions present on their
build machine. On Fedora 43 these version mismatches cause crashes.

The "All Linux" variant uses *static linking* — it bundles all library
dependencies inside the binary itself and does not depend on anything
installed on the host. This is the correct choice for any Linux
distribution not explicitly listed by NOAA.

**Note:** The "All Linux" variant excludes MPI executables
(`hycm_std`, `hytm_std`, etc.). These are not needed for this project,
which runs sequential single-plant simulations.

### 1.2 Source code

HYSPLIT source code is not in the public distribution. It is restricted
to registered institutional users. The public tarball ships pre-built
binaries only, with Makefiles present but no `.f` source files in
`library/hysplit/` or `source/`. Do not attempt `make all` on the public
tarball — it will fail at the library build step with:

```
make[1]: *** No rule to make target 'const.o', needed by '../libhysplit.a'. Stop.
```

### 1.3 Download

Go to:
```
https://www.ready.noaa.gov/ready2-bin/getlinuxtrial.pl
```

Enter your institutional email address. Download:
```
hysplit.v5.4.2_x86_64_public.tar.gz
```

SHA1 checksum (verify before extracting):
```
1e2de556b5794749c950770218751ab863d9f2ce
```

### 1.4 Installation commands

```bash
# Verify checksum — must match exactly before proceeding
sha1sum ~/Downloads/hysplit.v5.4.2_x86_64_public.tar.gz

# Extract
tar -xzf ~/Downloads/hysplit.v5.4.2_x86_64_public.tar.gz -C ~/Downloads

# Move to permanent location
mv ~/Downloads/hysplit.v5.4.2_x86_64_public ~/HYSPLIT

# Add executables to PATH permanently
echo 'export PATH=$PATH:$HOME/HYSPLIT/exec' >> ~/.bashrc
source ~/.bashrc

# Verify
which hycs_std
which era52arl
hycs_std 2>&1 | head -2
era52arl 2>&1 | head -2
```

Expected output:
```
/home/chris/HYSPLIT/exec/hycs_std
/home/chris/HYSPLIT/exec/era52arl
 HYSPLIT - Initialization
 HYSPLIT version: hysplit.v5.4.2
 Usage: era52arl [-options]
 One pressure level file and at least one surface file must be input.
```

### 1.5 Directory structure

```
~/HYSPLIT/
├── exec/          # all executables including hycs_std and era52arl
├── data2arl/
│   └── era52arl/  # era52arl Fortran source and Makefile
├── library/       # empty in public distribution (no source)
├── working/       # default working directory for HYSPLIT runs
└── Makefile.inc.gfortran  # compiler config template
```

---

## 2. System Dependencies

The following packages are required. Install with:

```bash
sudo dnf install -y \
    gcc \
    gcc-gfortran \
    gcc-c++ \
    make \
    netcdf-devel \
    netcdf-fortran-devel \
    eccodes-devel \
    hdf5-devel \
    zlib-devel
```

These are needed for:
- `gcc-gfortran` — Fortran compiler (required if compiling any HYSPLIT tools from source)
- `netcdf-fortran-devel` — NetCDF4 Fortran bindings (for `con2cdf4`, `arw2arl`)
- `eccodes-devel` — ECMWF eccodes library (for `era52arl` and API converters)
- `hdf5-devel` — HDF5, required by NetCDF4

Verify eccodes is installed correctly:
```bash
rpm -ql eccodes-devel | grep "\.mod$"
find /usr -name "libeccodes_f90.so"
```

Expected:
```
/usr/lib64/gfortran/modules/eccodes.mod
/usr/lib64/gfortran/modules/grib_api.mod
/usr/lib64/libeccodes_f90.so
```

---

## 3. ERA5-to-ARL Conversion Pipeline

### 3.1 Overview

The pipeline converts ERA5 GRIB files to HYSPLIT's binary ARL format.
It runs in three steps:

```
Step 2: Split annual GRIBs → monthly GRIBs
Step 3: Merge static geopotential into each monthly surface file
Step 4: Convert monthly GRIB pairs → monthly ARL files
```

Steps 2 and 3 use `grib_copy` (from `eccodes-devel`).  
Step 4 uses `era52arl`.

### 3.2 Project directory structure

```
~/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/
├── code/
│   └── build/
│       ├── 1_api_calls.py        # ERA5 download via CDS API
│       ├── 2_convert_monthly.sh  # split annual → monthly GRIBs
│       ├── 3_merge_geopt.sh      # merge static geopotential
│       ├── 4_convert_arl.sh      # convert GRIB → ARL
│       ├── master.sh             # runs steps 2-4 in sequence
│       ├── era52arl.cfg          # era52arl input variable config
│       └── arldata.cfg           # era52arl output grid config
├── data/
│   ├── raw/
│   │   ├── pressures/            # annual pressure-level GRIBs
│   │   ├── singles/              # annual surface GRIBs
│   │   └── geopot/               # static geopotential GRIB
│   ├── intermediate/
│   │   ├── pressures/            # monthly pressure-level GRIBs
│   │   ├── singles/              # monthly surface GRIBs
│   │   └── singles_merged/       # monthly surface + geopotential
│   └── final/
│       └── arl/                  # monthly ARL files (output)
└── .gitignore
```

A symlink is created for convenience:
```bash
ln -s ~/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants ~/htest
```

All scripts use `~/htest/` paths.

### 3.3 Configuration files

There are two config files that `era52arl` reads from the **working
directory** at runtime. Both live in `code/build/` and are copied to
the working directory by `4_convert_arl.sh` before each run.

#### era52arl.cfg

Tells `era52arl` which variables to read from the GRIB files and how
to map them to HYSPLIT's internal variable names.

```
&SETUP
 numatm = 6,
 atmgrb = 'z','t','u','v','w','r',
 atmcat =  129, 130, 131, 132, 135, 157,
 atmnum =  129, 130, 131, 132, 135, 157,
 atmcnv =  0.102, 1.0, 1.0, 1.0, 0.01, 1.0,
 atmarl = 'HGTS','TEMP','UWND','VWND','WWND','RELH',
 numsfc = 9,
 sfcgrb = '2t','10v','10u','tcc','sp','blh','sshf','slhf','tp',
 sfccat =  167, 166, 165, 164, 134, 159, 146, 147, 228,
 sfcnum =  167, 166, 165, 164, 134, 159, 146, 147, 228,
 sfccnv =  1.0, 1.0, 1.0, 1.0, 0.01, 1.0, 1.0, 1.0, 1.0,
 sfcarl = 'T02M','V10M','U10M','TCLD','PRSS','PBLH','SHFL','LHFL','TPP3',
 numlev = 4,
 plev = 1000, 925, 850, 700,
/
```

Variable mapping (pressure levels):

| GRIB short name | ECMWF param ID | HYSPLIT name | Conversion |
|---|---|---|---|
| z | 129 | HGTS | × 0.102 (m²/s² → m) |
| t | 130 | TEMP | × 1.0 |
| u | 131 | UWND | × 1.0 |
| v | 132 | VWND | × 1.0 |
| w | 135 | WWND | × 0.01 |
| r | 157 | RELH | × 1.0 |

Variable mapping (surface):

| GRIB short name | ECMWF param ID | HYSPLIT name | Notes |
|---|---|---|---|
| 2t | 167 | T02M | 2m temperature |
| 10v | 166 | V10M | 10m V wind |
| 10u | 165 | U10M | 10m U wind |
| tcc | 164 | TCLD | Total cloud cover |
| sp | 134 | PRSS | Surface pressure (× 0.01: Pa → hPa) |
| blh | 159 | PBLH | Boundary layer height |
| sshf | 146 | SHFL | Sensible heat flux |
| slhf | 147 | LHFL | Latent heat flux |
| tp | 228 | TPP3 | Total precipitation |

#### arldata.cfg

Tells `era52arl` the structure of the ARL output grid — its geographic
domain, resolution, and which variables to write at each level.

```
Model Type:         ERA5
Grid Numb:            99
Vert Coord:            2
Pole Lat:                56.00
Pole Lon:                 2.00
Ref Lat:                  0.25
Ref Lon:                  0.25
Grid Size:                0.00
Orientation:              0.00
Cone Angle:               0.00
Sync X Pt:                1.00
Sync Y Pt:                1.00
Sync Lat:                50.00
Sync Lon:               354.25
Reserved:                 0.00
Numb X pt:            32
Numb Y pt:            25
Numb Levels:           5
Level    1:         .00000  9 T02M V10M U10M TCLD PRSS PBLH SHFL LHFL TPP3
Level    2:         1000.0  7 HGTS TEMP UWND VWND WWND RELH DIFW
Level    3:         925.00  7 HGTS TEMP UWND VWND WWND RELH DIFW
Level    4:         850.00  7 HGTS TEMP UWND VWND WWND RELH DIFW
Level    5:         700.00  7 HGTS TEMP UWND VWND WWND RELH DIFW
```

Grid domain:
- SW corner: 50.0°N, 354.25°E (= 5.75°W)
- NE corner: 56.25°N, 2.25°E
- Resolution: 0.25° × 0.25°
- Points: 32 (lon) × 25 (lat)

This domain covers England. Designed for England-only analysis;
coastal cells are not normalised within the cdump so no boundary
correction is needed.

### 3.4 Shell scripts

#### 2_convert_monthly.sh

Splits annual GRIB files into monthly files using `grib_copy`:

```bash
#!/bin/bash
RAW_PRESSURE="/home/chris/htest/data/raw/pressures"
RAW_SINGLES="/home/chris/htest/data/raw/singles"
INT_PRESSURE="/home/chris/htest/data/intermediate/pressures"
INT_SINGLES="/home/chris/htest/data/intermediate/singles"

mkdir -p $INT_PRESSURE $INT_SINGLES

for pl_file in ${RAW_PRESSURE}/era5_pl_*.grib; do
    year=$(basename $pl_file | grep -oP '\d{4}')
    sfc_file="${RAW_SINGLES}/era5_sfc_an_${year}.grib"

    if [ ! -f "$sfc_file" ]; then
        echo "WARNING: no surface file for $year, skipping"
        continue
    fi

    echo "Splitting $year..."

    for month in $(seq -w 1 12); do
        grib_copy -w month=$month \
            $pl_file \
            ${INT_PRESSURE}/era5_pl_${year}_${month}.grib

        grib_copy -w month=$month \
            $sfc_file \
            ${INT_SINGLES}/era5_sfc_an_${year}_${month}.grib

        echo "  Done: ${year}_${month}"
    done
done

echo "Splitting complete."
```

#### 3_merge_geopt.sh

Appends the static geopotential (terrain height) GRIB record to each
monthly surface file. `era52arl` requires terrain height to be present
in the surface file:

```bash
#!/bin/bash
INT_SINGLES="/home/chris/htest/data/intermediate/singles"
GEOPOTENTIAL="/home/chris/htest/data/raw/geopot/geopot.grib"
MERGED_SINGLES="/home/chris/htest/data/intermediate/singles_merged"

mkdir -p "$MERGED_SINGLES"

for sfc_file in "$INT_SINGLES"/era5_sfc_an_????_??.grib; do
    base=$(basename "$sfc_file" .grib)
    out_file="${MERGED_SINGLES}/${base}_z.grib"

    echo "Merging geopotential into ${base}..."
    grib_copy "$sfc_file" "$GEOPOTENTIAL" "$out_file"
    echo "  Done: $(basename "$out_file")"
done

echo "Geopotential merge complete."
```

#### 4_convert_arl.sh

Converts each monthly GRIB pair to ARL format. Copies both config
files to the working directory before calling `era52arl`, because
`era52arl` looks for `ERA52ARL.CFG` and `arldata.cfg` in the current
working directory:

```bash
#!/bin/bash
INT_PRESSURE="/home/chris/htest/data/intermediate/pressures"
MERGED_SINGLES="/home/chris/htest/data/intermediate/singles_merged"
FINAL="/home/chris/htest/data/final/arl"
BUILD_DIR="$(dirname "$(realpath "$0")")"

mkdir -p "$FINAL"
ORIG_DIR=$(pwd)
cd "$INT_PRESSURE" || exit 1

# both configs must be in the working directory when era52arl runs
cp "${BUILD_DIR}/era52arl.cfg" ./ERA52ARL.CFG
cp "${BUILD_DIR}/arldata.cfg"  ./arldata.cfg

for pl_file in era5_pl_????_??.grib; do
    if [ ! -f "$pl_file" ]; then
        echo "WARNING: no monthly pressure files found in $INT_PRESSURE"
        exit 1
    fi

    year=$(echo "$pl_file" | grep -oP '\d{4}' | head -1)
    month=$(echo "$pl_file" | grep -oP '(?<=_)\d{2}(?=\.grib)')
    a_file="${MERGED_SINGLES}/era5_sfc_an_${year}_${month}_z.grib"

    if [ ! -f "$a_file" ]; then
        echo "WARNING: no merged surface file for ${year}_${month}, skipping"
        continue
    fi

    echo "Converting ${year}_${month}..."

    era52arl \
        -i"$pl_file" \
        -a"$a_file" \
        -o"${FINAL}/era5_${year}_${month}.arl" \
        -v

    echo "  Done: ${year}_${month}"
done

cd "$ORIG_DIR" || exit 1
echo "Conversion complete."
```

#### master.sh

Runs the full pipeline in sequence:

```bash
#!/bin/bash
set -e

cd /home/chris/htest/code/build

echo "Converting Annual Data to Monthly Data"
bash 2_convert_monthly.sh

echo "Merging Geopotential"
bash 3_merge_geopt.sh

echo "Converting GRIB to ARL"
bash 4_convert_arl.sh

echo "Done."
```

---

## 4. Known Blocking Issue: era52arl

**Status: Unresolved.**

### What works
- `hycs_std` (the concentration model) — fully working.
- Steps 2 and 3 of the pipeline (GRIB splitting and geopotential merge) — fully working. 180 intermediate files confirmed present.

### What is blocked
- `era52arl` — the GRIB-to-ARL converter crashes on Fedora 43.

### Root cause

The "All Linux" static binary has the ECMWF eccodes definitions path
hardcoded to the build machine's path:

```
/hysplit1/sonnyz/local/rhel7_gfort4.8.5/share/eccodes/definitions
```

This path does not exist on any other machine. Setting
`ECCODES_DEFINITION_PATH` to the correct Fedora path
(`/usr/share/eccodes/definitions`) gets past the first crash but
triggers a segfault due to an eccodes version mismatch: the binary
was compiled against eccodes **2.17.0** but Fedora 43 ships
eccodes **2.46.0**. The definition file format changed between
these versions.

### What was tried
1. Setting `ECCODES_DEFINITION_PATH` — gets past boot.def error but segfaults on version mismatch.
2. Compiling era52arl from source (`~/HYSPLIT/data2arl/era52arl/`) — blocked because `libhysplit.a` is not in the public distribution.

### Resolution options (not yet attempted)
1. **Download RHEL9 tarball and extract only `libhysplit.a`** — the RHEL9 pre-built tarball contains this library. Extract it and use it to compile era52arl from source against the system eccodes 2.46.0.
2. **Register for HYSPLIT source access** — full source registration at `https://www.ready.noaa.gov/HYSPLIT_register.php` gives access to `libhysplit.a` source, enabling a complete native build.

---

## 5. Environment Summary

```bash
# Fedora version
cat /etc/fedora-release
# Fedora release 43 (Workstation Edition)

# GCC version
gfortran --version | head -1
# GNU Fortran (GCC) 15.2.1 20260123 (Red Hat 15.2.1-7)

# HYSPLIT version
hycs_std 2>&1 | grep version
# HYSPLIT version: hysplit.v5.4.2

# eccodes version
rpm -q eccodes
# eccodes-2.46.0-1.fc43.x86_64

# PATH entry
echo $PATH | tr ':' '\n' | grep HYSPLIT
# /home/chris/HYSPLIT/exec

# ECCODES_DEFINITION_PATH
echo $ECCODES_DEFINITION_PATH
# /usr/share/eccodes/definitions
```