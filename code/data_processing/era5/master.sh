#!/bin/bash
set -e

cd /home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/code/data_processing/era5/

echo "Merging Geopotential"
./2_merge_geopt.sh

echo "Converting grib to arl"
./3_convert_arl.sh

echo "Done."