#!/bin/bash
# merge_geopot.sh

# create short symlink if it doesn't exist
if [ ! -L /home/chris/htest ]; then
    ln -s /home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/home/chris/htest
fi

INT_SINGLES="/home/chris/htest/data/intermediate/singles"
GEOPOTENTIAL="/home/chris/htest/data/raw/geopot/geopot.grib"
MERGED_SINGLES="/home/chris/htest/data/intermediate/singles_merged"

mkdir -p "$MERGED_SINGLES"

if [ ! -f "$GEOPOTENTIAL" ]; then
    echo "ERROR: geopotential file not found at $GEOPOTENTIAL"
    exit 1
fi

for sfc_file in "$INT_SINGLES"/era5_sfc_an_????_??.grib; do
    if [ ! -f "$sfc_file" ]; then
        echo "WARNING: no monthly surface files found in $INT_SINGLES"
        exit 1
    fi

    base=$(basename "$sfc_file" .grib)
    out_file="${MERGED_SINGLES}/${base}_z.grib"

    echo "Merging geopotential into ${base}..."

    grib_copy \
        "$sfc_file" \
        "$GEOPOTENTIAL" \
        "$out_file"

    echo "  Done: $(basename "$out_file")"
done

echo "Geopotential merge complete."