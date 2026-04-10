#!/bin/bash
set -e

cd /home/chris/Documents/hysplit_test/code/build/build

echo "Converting Annual Data to Monthly Data"
./2_convert_monthly.sh

echo "Merging Geopotential"
./3_merge_geopt.sh

echo "Converting grib to arl"
./4_convert_arl.sh

echo "Done."