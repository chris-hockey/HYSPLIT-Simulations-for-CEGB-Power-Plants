#!/bin/bash
# split_to_months.sh

RAW_PRESSURE="/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/raw/pressures"
RAW_SINGLES="/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/raw/singles"
INT_PRESSURE="/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/intermediate/pressures"
INT_SINGLES="/home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/data/intermediate/singles"

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

# reset to original directory
cd $ORIG_DIR

echo "Splitting complete."