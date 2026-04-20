# HYSPLIT Setup on Fedora 43 — Complete Instructions

**Purpose:** Install HYSPLIT, set up the ERA5-to-ARL conversion pipeline, and run concentration simulations from the command line.  
**Machine:** Fedora 43 x86_64  
**Tested binary**: ```hysplit.v5.4.2_RHEL9.7_public.tar.gz```

### 1.) Install system dependencies
Install the required development tools and libraries:
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

### 2.) Download

For Fedora 43, the **Red Hat Enterprise Linux 9 / Rocky 9**  build worked.
Download from NOAA’s Linux page, https://www.ready.noaa.gov/ready2-bin/getlinuxtrial.pl, after entering an email address:
- file: ```hysplit.v5.4.2_RHEL9.7_public.tar.gz```

Save it to:
```bash
~/Downloads/
```
### 3.) Verify the download
Check that the downloaded tarball matches the expected checksum:
```bash
sha1sum ~/Downloads/hysplit.v5.4.2_RHEL9.7_public.tar.gz
```
Expected SHA1:
```bash
de9b219723e7d648a5bd70f515fffb91ceef8cf5
```
### 4.) Extract HYSPLIT from tarball
Create the installation directory:
```bash
mkdir -p ~/opt/hysplit
```
Extract HYSPLIT there:
```bash
tar -xzf ~/Downloads/hysplit.v5.4.2_RHEL9.7_public.tar.gz -C ~/opt/hysplit
```
That should give you:
```
~/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public
```
### 5.) Create a HYSPLIT directory in your shell environment
(Aka: setting environment variables):
```bash
echo 'export HYSPLIT_DIR=$HOME/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public' >> ~/.bashrc
echo 'export PATH=$PATH:$HYSPLIT_DIR/exec' >> ~/.bashrc
source ~/.bashrc
```
Check that it is set correctly:
```bash
echo $HYSPLIT_DIR
ls $HYSPLIT_DIR/exec | head
```

### 6.) Test the installation
Check that core executables exist:
```bash
ls -l $HYSPLIT_DIR/exec/hycs_std
ls -l $HYSPLIT_DIR/exec/hyts_std
ls -l $HYSPLIT_DIR/exec/era52arl
ls -l $HYSPLIT_DIR/exec/con2cdf4
ls -l $HYSPLIT_DIR/exec/chk_file
```

#### 6.5) Launching GUI
Look at ```instructions/gui_fix.md```, as it documents an important fix to make to get the GUI working.

Once that is done, you can launch it with:
```bash
cd $HYSPLIT_DIR/working
wish ../guicode/hysplit.tcl
```

### 7.) Project structure
The working project has the following structure:
```
HYSPLIT-Simulations-for-CEGB-Power-Plants/
├── code/build/
├── data/raw/
│   ├── pressures/
│   ├── singles/
│   └── geopot/
├── data/intermediate/
│   ├── pressures/
│   ├── singles/
│   └── singles_merged/
└── data/final/
    ├── arl/
    └── concentration/
```

A symlink is created when running the conversion scripts:
```bash
ln -s ~/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants ~/htest
```
We can then use the directory ```~/htest``` to access the project

### 8.) Download ERA5 Data
The script ``code/build/1_api_calls.py`` calls ERA5 pressure-level and single-level GRIB files. These are saved to
```
data/raw/pressures/era5_pl_YYYY.grib
data/raw/singles/era5_sfc_an_YYYY.grib
data/raw/geopot/geopot.grib
```
Pressure-level request **only used 4 levels**:
- ```1000```
- ```925```
- ```850```
- ```700```
**This is important because downstream, ```era52arl``` config must match those four levels.

### 9.) Split annual ERA5 files into monthly files
Use ```code/build/2_convert_monthly.sh``` which uses ```grib_copy``` from the ```eccodes``` package we downloaded in 1.

Output files:
```
data/intermediate/pressures/era5_pl_YYYY_MM.grib
data/intermediate/singles/era5_sfc_an_YYYY_MM.grib
```

### 10.) Merge geopotential into monthly-single levels
The monthly surface files were merged with the time-invariant GRIB, ```data/raw/geopot/geopot.grib```, in ```code/build/3_merge_geopot.sh``` to create:
```
data/intermediate/singles_merged/era5_sfc_an_YYYY_MM_z.grib
```

### 11.) Keep a reference ```era52arl``` config 
**THIS IS IMPORTANT**
Do not let ```era52arl``` write directly to the Git-tracked config file that is set-up to handle converting our specific selection of variables and **levels** of ERA5 data to the arl format. 

**DO NOT TOUCH!!! :**
```
code/build/era52arl_4lev_reference.cfg
```
**Make it read-only so it cannot be over-written**
```bash
chmod 444 ~/htest/code/build/era52arl_4lev_reference.cfg
```
This reference file should match the 4 pressure levels we have in our ERA5 data:
```
numlev = 4
plev = 1000, 925, 850, 700
```

### 12.) Convert Monthly ERA5 GRIBs to ARL data
Use ```code/build/4_convert_arl.sh```
It:
- reads monthly pressure GRIBs
- reads merged monthly single-level GRIBs
- copies the reference config into a temporary working directory
- calls ```era52arl``` with ```-d``` pointing to that temporary config
- writes ```.arl``` files into ```data/final/arl```
- immediately checks each output with ```chk_file```

This avoids the problem where ```era52arl``` auto-generates or overwrites ```era52arl.cfg``` with the *incorrect* default of 37 pressure levels

**Before building ARLs** remove old ARLs and logs:
```bash
rm -f ~/htest/data/final/arl/*.arl
rm -f ~/htest/data/final/arl/*_build.log
rm -f ~/htest/data/final/arl/*_chk.log
rm -f ~/htest/data/final/arl/rebuild_all.log
```
And remove any stray runtime config files if present:
```bash
rm -f ~/htest/data/intermediate/pressures/era52arl.cfg
rm -f ~/htest/data/intermediate/pressures/ERA52ARL.CFG
rm -f ~/era52arl.cfg ~/ERA52ARL.CFG ~/arldata.cfg 2>/dev/null
```

**Then run the conversion script**
```bash
bash ~/htest/code/build/4_convert_arl.sh | tee ~/htest/data/final/arl/rebuild_all.log
```

### 13.) Verify ARL files
Check converted ARL files using:
```bash
printf "%s\n%s\n" "$HOME/htest/data/final/arl/" "era5_1974_01.arl" | "$HYSPLIT_DIR/exec/chk_file"
printf "%s\n%s\n" "$HOME/htest/data/final/arl/" "era5_1984_01.arl" | "$HYSPLIT_DIR/exec/chk_file"
```
(example using Jan 1974 and Jan 1984)

They key check is:
```
Grid size x,y,z : 32 25 5
```
where z = 5 levels, (the 4 pressures plus the surface-layer from the geopotential)

If you see ```z = 38```, then the wrong default config was used using era52arl conversion, and this will break the HYSPLIT run.

# 15.) Run HYSPLIT concentration simulations from the command line
Here, we will do a CONTROL file for 1974 and 1984.

1974:
```bash
cat > CONTROL_1974 <<'EOF'
74 01 01 00
1
53.736437 -0.995907 259
24
0
10000.0
1
/home/chris/htest/data/final/arl/
era5_1974_01.arl
1
TEST
1.0
24
74 01 01 00 00
1
53.0 -2.0
0.05 0.05
8.0 10.0
/home/chris/htest/data/final/concentration/
fedora_cdump_drax_197401
1
100
00 00 00 00 00
00 00 00 00 00
00 24 00
1
0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0
0.0 0.0 0.0
0.0
0.0
EOF
```

1984
```bash
cat > CONTROL_1984 <<'EOF'
84 01 01 00
1
53.736437 -0.995907 259
24
0
10000.0
1
/home/chris/htest/data/final/arl/
era5_1984_01.arl
1
TEST
1.0
24
84 01 01 00 00
1
53.0 -2.0
0.05 0.05
8.0 10.0
/home/chris/htest/data/final/concentration/
fedora_cdump_drax_198401
1
100
00 00 00 00 00
00 00 00 00 00
00 24 00
1
0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0
0.0 0.0 0.0
0.0
0.0
EOF
```

And double check the ARL data we are about to use, to make sure ```z = 5```:
```bash
ls -lh /home/chris/htest/data/final/arl/era5_1974_01.arl
ls -lh /home/chris/htest/data/final/arl/era5_1984_01.arl
```

nd double check the ARL data we are about to use, to make sure ```z = 5```:
```bash
ls -lh /home/chris/htest/data/final/arl/era5_1974_01.arl
ls -lh /home/chris/htest/data/final/arl/era5_1984_01.arl
```

**Run HYSPLIT**
```bash
cp CONTROL_1974 CONTROL
../exec/hycs_std > run_1974.log 2>&1
cat run_1974.log
ls -lh /home/chris/htest/data/final/concentration/fedora_cdump_drax_197401
```

For a successful run, the log should end with"
```
Complete Hysplit
```

### EXPERIMENTAL: Convert concentration file to NetCDF
After HYSPLIT produces a ```cdump``` file, convert it to NetCDF using:
```bash
cd $HYSPLIT_DIR/working
../exec/con2cdf4 ~/htest/data/final/concentration/fedora_cdump_drax_197401 \
                 ~/htest/data/final/concentration/fedora_cdump_drax_197401.nc
```
Then open in in Python using ```xarray```:
```python
import xarray as xr

ds = xr.open_dataset("/home/chris/htest/data/final/concentration/fedora_cdump_drax_197401.nc")
print(ds)
```