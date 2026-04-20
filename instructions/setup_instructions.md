# HYSPLIT Setup on Fedora 43 — Complete Instructions

**Purpose:** Install HYSPLIT, compile the ERA5 converter, and set up the
ERA5-to-ARL conversion pipeline from scratch.  
**Machine:** Fedora 43 x86_64  
**HYSPLIT version:** 5.4.2

---

## Why two downloads are needed

HYSPLIT is split across two packages from NOAA:

1. **The "All Linux" package** — contains `hycs_std` (the model itself)
   and most utilities, compiled as static binaries that work on any
   Linux. However, the ERA5 converter (`era52arl`) in this package is
   broken on Fedora 43 because it has a path to the ECMWF library
   hardcoded from the machine it was built on.

2. **The RHEL9 package** — we use this only to extract one file:
   `libhysplit.a`, a compiled library that `era52arl` needs when
   building from source. We do not use any other binaries from it.

The solution is: use the "All Linux" binaries for everything except
`era52arl`, and compile `era52arl` from source (which is included in
the package) using the one library file extracted from the RHEL9 package.

---

## Step 1 — Install system dependencies

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

---

## Step 2 — Download both HYSPLIT packages

Go to:
```
https://www.ready.noaa.gov/ready2-bin/getlinuxtrial.pl
```

Enter your institutional email. Download both files to `~/Downloads`:

| File | SHA1 checksum |
|---|---|
| `hysplit.v5.4.2_x86_64_public.tar.gz` | `1e2de556b5794749c950770218751ab863d9f2ce` |
| `hysplit.v5.4.2_RHEL9.7_public.tar.gz` | `de9b219723e7d648a5bd70f515fffb91ceef8cf5` |

Verify both before extracting:

```bash
sha1sum ~/Downloads/hysplit.v5.4.2_x86_64_public.tar.gz
sha1sum ~/Downloads/hysplit.v5.4.2_RHEL9.7_public.tar.gz
```

Both must match exactly.

---

## Step 3 — Extract and install

```bash
# Extract the All Linux package
tar -xzf ~/Downloads/hysplit.v5.4.2_x86_64_public.tar.gz -C ~/Downloads

# Move to permanent location
mv ~/Downloads/hysplit.v5.4.2_x86_64_public ~/HYSPLIT

# Extract only the library directory from the RHEL9 package
tar -xzf ~/Downloads/hysplit.v5.4.2_RHEL9.7_public.tar.gz \
    -C ~/Downloads \
    --wildcards \
    'hysplit.v5.4.2_RHEL9.7_public/library/*'

# Copy the two library files we need into the HYSPLIT installation
cp ~/Downloads/hysplit.v5.4.2_RHEL9.7_public/library/libhysplit.a \
   ~/HYSPLIT/library/
cp ~/Downloads/hysplit.v5.4.2_RHEL9.7_public/library/libgfortranfcsubs.a \
   ~/HYSPLIT/library/

# Clean up downloads
rm -rf ~/Downloads/hysplit.v5.4.2_x86_64_public
rm -rf ~/Downloads/hysplit.v5.4.2_RHEL9.7_public
rm -f  ~/Downloads/hysplit.v5.4.2_x86_64_public.tar.gz
rm -f  ~/Downloads/hysplit.v5.4.2_RHEL9.7_public.tar.gz
```

---

## Step 4 — Configure the compiler settings

HYSPLIT uses a file called `Makefile.inc` to find the libraries on your
machine. Start from the provided template and apply two changes to match
Fedora's library locations.

```bash
# Copy the template
cp ~/HYSPLIT/Makefile.inc.gfortran ~/HYSPLIT/Makefile.inc

# Fix 1: set the ECMWF eccodes library path (Fedora puts it in /usr/lib64)
sed -i \
  's|#ECCODESINC= -I/opt/eccodes/include|ECCODESINC= -I/usr/lib64/gfortran/modules|' \
  ~/HYSPLIT/Makefile.inc

sed -i \
  's|#ECCODESLIBS= -L/opt/eccodes/lib -leccodes_f90 -leccodes|ECCODESLIBS= -L/usr/lib64 -leccodes_f90 -leccodes|' \
  ~/HYSPLIT/Makefile.inc

# Fix 2: set ECCODES_TOPDIR so the Makefile finds the library files
sed -i \
  's|#ECCODES_TOPDIR= /opt/eccodes|ECCODES_TOPDIR= /usr|' \
  ~/HYSPLIT/Makefile.inc

# Verify all three lines are correct
grep -E "^ECCODESINC|^ECCODESLIBS|^ECCODES_TOPDIR" ~/HYSPLIT/Makefile.inc
```

Expected output:
```
ECCODES_TOPDIR= /usr
ECCODESINC= -I/usr/lib64/gfortran/modules
ECCODESLIBS= -L/usr/lib64 -leccodes_f90 -leccodes
```

---

## Step 5 — Fix the era52arl Makefile

The era52arl Makefile checks for library files before compiling. The
path it constructs (`/usr/lib/libeccodes_f90.so`) is wrong on Fedora —
the files are in `/usr/lib64/`. Override the paths directly:

```bash
sed -i \
  's|$(ECCODES_TOPDIR)/lib/libeccodes_f90.so|/usr/lib64/libeccodes_f90.so|g' \
  ~/HYSPLIT/data2arl/era52arl/Makefile

sed -i \
  's|$(ECCODES_TOPDIR)/lib/libeccodes.so|/usr/lib64/libeccodes.so|g' \
  ~/HYSPLIT/data2arl/era52arl/Makefile

# Verify
grep "libeccodes" ~/HYSPLIT/data2arl/era52arl/Makefile
```

Expected output:
```
        /usr/lib64/libeccodes_f90.so \
        /usr/lib64/libeccodes.so
```

---

## Step 6 — Compile era52arl

```bash
cd ~/HYSPLIT/data2arl/era52arl
make 2>&1 | tail -5
```

The output will contain several warnings about unused variables — these
are harmless. The final line should be a `gfortran` linker command with
no errors. Then verify:

```bash
ls -lh ~/HYSPLIT/exec/era52arl
```

Should show a file dated today, around 190K in size.

---

## Step 7 — Add HYSPLIT to PATH and set eccodes definitions path

```bash
echo 'export PATH=$PATH:$HOME/HYSPLIT/exec' >> ~/.bashrc
echo 'export ECCODES_DEFINITION_PATH=/usr/share/eccodes/definitions' >> ~/.bashrc
source ~/.bashrc
```

The `ECCODES_DEFINITION_PATH` line tells the compiled era52arl where to
find the ECMWF variable definition files on this machine. Without it,
era52arl crashes immediately.

Verify both executables work:

```bash
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

---

## Step 8 — Set up the project repo config files

Two config files must live in `code/build/` in the project repo. They
are copied to the working directory at runtime by `4_convert_arl.sh`.

### era52arl.cfg

Tells era52arl which variables to read from the ERA5 GRIB files and
what to call them in the ARL output.

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

### arldata.cfg

Tells era52arl the structure of the ARL output grid — its geographic
domain, resolution, and which variables appear at each level.

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

This grid covers England: SW corner 50.0°N 5.75°W, NE corner 56.25°N
2.25°E, at 0.25° resolution.

---

## Step 9 — Run a single-month test conversion

Before running the full pipeline, test on one month:

```bash
cd ~/htest/data/intermediate/pressures

cp ~/htest/code/build/era52arl.cfg ./ERA52ARL.CFG
cp ~/htest/code/build/arldata.cfg  ./arldata.cfg

era52arl \
    -iera5_pl_1974_01.grib \
    -a../singles_merged/era5_sfc_an_1974_01_z.grib \
    -o../../final/arl/era5_1974_01.arl \
    -v 2>&1 | head -20
```

A successful run prints the grid coordinates, number of time periods
found (should be ~124 for a monthly file at 6-hourly resolution), and
then processes each time period in sequence. When finished:

```bash
ls -lh ~/htest/data/final/arl/era5_1974_01.arl
```

---

## Step 10 — Run the full pipeline

Once the test passes, run all years:

```bash
cd ~/htest/code/build
bash master.sh 2>&1 | tee ~/htest/pipeline.log
```

Expected output: 180 ARL files (15 years × 12 months) in
`~/htest/data/final/arl/`.

```bash
ls ~/htest/data/final/arl/ | wc -l   # should return 180
```

---

## Summary of changes made to HYSPLIT files

| File | Change | Reason |
|---|---|---|
| `~/HYSPLIT/Makefile.inc` | Copied from `Makefile.inc.gfortran` | Template must be copied before use |
| `~/HYSPLIT/Makefile.inc` | Set `ECCODESINC` to `/usr/lib64/gfortran/modules` | Fedora installs Fortran modules here, not `/usr/include` |
| `~/HYSPLIT/Makefile.inc` | Set `ECCODESLIBS` to `-L/usr/lib64` | Fedora puts libraries in `/usr/lib64`, not `/usr/lib` |
| `~/HYSPLIT/Makefile.inc` | Set `ECCODES_TOPDIR` to `/usr` | Required by the era52arl Makefile dependency check |
| `~/HYSPLIT/data2arl/era52arl/Makefile` | Replaced `$(ECCODES_TOPDIR)/lib/libeccodes*.so` with `/usr/lib64/libeccodes*.so` | Fedora puts these in `/usr/lib64`, not `/usr/lib` |
| `~/.bashrc` | Added `HYSPLIT/exec` to PATH | So executables can be called from anywhere |
| `~/.bashrc` | Set `ECCODES_DEFINITION_PATH` | The compiled era52arl needs to find ECMWF definition files at runtime |