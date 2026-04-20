# HYSPLIT Setup on Fedora 43 — What We Did and Why

**Machine:** Fedora 43 x86_64, AMD Ryzen 5 5600X, 16GB RAM  
**HYSPLIT version:** 5.4.2  
**Date:** April 2026

---

## 1. System dependencies

Installed the following packages via `dnf`:

```bash
sudo dnf install -y \
    gcc gcc-gfortran gcc-c++ make \
    netcdf-devel netcdf-fortran-devel \
    eccodes-devel hdf5-devel zlib-devel
```

These were already present on the machine except for confirmation.
`eccodes-devel` is required to compile `era52arl` from source.
`netcdf-fortran-devel` is required for other HYSPLIT converters.

---

## 2. Downloading HYSPLIT

**Why two downloads:**  
NOAA's public HYSPLIT distribution does not include source code —
only pre-compiled binaries. The "All Linux" package ships `hycs_std`
and most utilities as static binaries that work on any x86_64 Linux.
However, its `era52arl` binary is broken on Fedora 43 because it has
an eccodes library path hardcoded from the build machine
(`/hysplit1/sonnyz/...`) that does not exist anywhere else, and was
compiled against eccodes 2.17.0 while Fedora 43 ships 2.46.0.

The solution is to compile `era52arl` from source. The source is
included in the package (`~/HYSPLIT/data2arl/era52arl/era52arl.f`)
but requires `libhysplit.a` to link against, which is not in the
public distribution. The RHEL9 package includes pre-compiled
`libhysplit.a`. We extract only that file from the RHEL9 package
and use it to compile `era52arl` from source against the system
eccodes 2.46.0.

**Download location:**
```
https://www.ready.noaa.gov/ready2-bin/getlinuxtrial.pl
```

**Files downloaded to `~/Downloads/`:**

| File | SHA1 |
|---|---|
| `hysplit.v5.4.2_x86_64_public.tar.gz` | `1e2de556b5794749c950770218751ab863d9f2ce` |
| `hysplit.v5.4.2_RHEL9.7_public.tar.gz` | `de9b219723e7d648a5bd70f515fffb91ceef8cf5` |

Both checksums were verified with `sha1sum` before extracting.

---

## 3. Extracting and installing

**"All Linux" package — full extraction:**

```bash
tar -xzf ~/Downloads/hysplit.v5.4.2_x86_64_public.tar.gz -C ~/Downloads
mv ~/Downloads/hysplit.v5.4.2_x86_64_public ~/HYSPLIT
```

**RHEL9 package — library files only:**

```bash
tar -xzf ~/Downloads/hysplit.v5.4.2_RHEL9.7_public.tar.gz \
    -C ~/Downloads \
    --wildcards \
    'hysplit.v5.4.2_RHEL9.7_public/library/*'

cp ~/Downloads/hysplit.v5.4.2_RHEL9.7_public/library/libhysplit.a \
   ~/HYSPLIT/library/
cp ~/Downloads/hysplit.v5.4.2_RHEL9.7_public/library/libgfortranfcsubs.a \
   ~/HYSPLIT/library/
```

Only `libhysplit.a` and `libgfortranfcsubs.a` were taken from the
RHEL9 package. Nothing else from it was used.

**Cleanup:**

```bash
rm -rf ~/Downloads/hysplit.v5.4.2_RHEL9.7_public
rm -f  ~/Downloads/hysplit.v5.4.2_RHEL9.7_public.tar.gz
rm -f  ~/Downloads/hysplit.v5.4.2_x86_64_public.tar.gz
```

---

## 4. Configuring the compiler settings (Makefile.inc)

`Makefile.inc` tells the compiler where to find libraries on this
machine. The template (`Makefile.inc.gfortran`) has the eccodes paths
commented out, pointing to `/opt/eccodes` (a custom install location).
On Fedora, eccodes is installed by `dnf` into standard system paths.
Three changes were made:

```bash
cp ~/HYSPLIT/Makefile.inc.gfortran ~/HYSPLIT/Makefile.inc
```

**Change 1 — eccodes Fortran module location:**
```bash
sed -i \
  's|#ECCODESINC= -I/opt/eccodes/include|ECCODESINC= -I/usr/lib64/gfortran/modules|' \
  ~/HYSPLIT/Makefile.inc
```
Fedora installs eccodes Fortran modules at `/usr/lib64/gfortran/modules`,
not `/opt/eccodes/include`.

**Change 2 — eccodes shared library location:**
```bash
sed -i \
  's|#ECCODESLIBS= -L/opt/eccodes/lib -leccodes_f90 -leccodes|ECCODESLIBS= -L/usr/lib64 -leccodes_f90 -leccodes|' \
  ~/HYSPLIT/Makefile.inc
```
Fedora puts shared libraries in `/usr/lib64`, not `/opt/eccodes/lib`.

**Change 3 — ECCODES_TOPDIR:**
```bash
sed -i \
  's|#ECCODES_TOPDIR= /opt/eccodes|ECCODES_TOPDIR= /usr|' \
  ~/HYSPLIT/Makefile.inc
```
The era52arl Makefile uses `ECCODES_TOPDIR` to construct a dependency
check path. Setting it to `/usr` means it looks for the libraries at
`/usr/lib/libeccodes*.so` — which is still wrong on Fedora (they are
in `/usr/lib64`), so the era52arl Makefile also needed fixing.

---

## 5. Fixing the era52arl Makefile

The era52arl Makefile constructs the library dependency path as
`$(ECCODES_TOPDIR)/lib/libeccodes_f90.so`. With `ECCODES_TOPDIR=/usr`
this becomes `/usr/lib/libeccodes_f90.so`, but the actual location on
Fedora is `/usr/lib64/libeccodes_f90.so`. The paths were overridden
directly in the Makefile:

```bash
sed -i \
  's|$(ECCODES_TOPDIR)/lib/libeccodes_f90.so|/usr/lib64/libeccodes_f90.so|g' \
  ~/HYSPLIT/data2arl/era52arl/Makefile

sed -i \
  's|$(ECCODES_TOPDIR)/lib/libeccodes.so|/usr/lib64/libeccodes.so|g' \
  ~/HYSPLIT/data2arl/era52arl/Makefile
```

---

## 6. Compiling era52arl

```bash
cd ~/HYSPLIT/data2arl/era52arl
make 2>&1 | tee make.log
```

Compiled successfully with warnings (unused variables — harmless).
Output binary written to `~/HYSPLIT/exec/era52arl`, 190K, dynamically
linked against system eccodes 2.46.0.

---

## 7. PATH and environment variables

```bash
echo 'export PATH=$PATH:$HOME/HYSPLIT/exec' >> ~/.bashrc
echo 'export ECCODES_DEFINITION_PATH=/usr/share/eccodes/definitions' >> ~/.bashrc
source ~/.bashrc
```

`ECCODES_DEFINITION_PATH` is required because the compiled `era52arl`
needs to find ECMWF variable definition files at runtime. Without it,
era52arl crashes immediately with a `boot.def not found` error.

---

## 8. Verification

```bash
which hycs_std    # → /home/chris/HYSPLIT/exec/hycs_std
which era52arl    # → /home/chris/HYSPLIT/exec/era52arl
hycs_std 2>&1 | head -2   # → HYSPLIT version: hysplit.v5.4.2
era52arl 2>&1 | head -2   # → Usage: era52arl [-options]
```

---

## 9. Test ARL conversion

One month converted manually to verify era52arl works end-to-end:

```bash
cd ~/htest/data/intermediate/pressures
cp ~/htest/code/build/era52arl.cfg ./ERA52ARL.CFG
cp ~/htest/code/build/arldata.cfg  ./arldata.cfg

era52arl \
    -iera5_pl_1974_01.grib \
    -a../singles_merged/era5_sfc_an_1974_01_z.grib \
    -o../../final/arl/era5_1974_01.arl \
    -v
```

Output verified with `chk_file`: correct grid (32×25, 0.25°, SW corner
50°N/5.75°W), 4 pressure levels, all required variables present, 6-hourly
timesteps, ERA5 model type confirmed.

---

## Summary of all files changed

| File | What changed | Why |
|---|---|---|
| `~/HYSPLIT/Makefile.inc` | Created from `Makefile.inc.gfortran`; set `ECCODESINC`, `ECCODESLIBS`, `ECCODES_TOPDIR` | Fedora library paths differ from template defaults |
| `~/HYSPLIT/data2arl/era52arl/Makefile` | Hardcoded eccodes `.so` paths to `/usr/lib64/` | `$(ECCODES_TOPDIR)/lib/` resolves incorrectly on Fedora |
| `~/.bashrc` | Added `HYSPLIT/exec` to `PATH`; set `ECCODES_DEFINITION_PATH` | Executables callable from anywhere; era52arl runtime dependency |