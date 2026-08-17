#!/bin/bash
set -euo pipefail

# create short symlink if it doesn't exist
if [ ! -L /home/chris/htest ]; then
    ln -s /home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants /home/chris/htest
fi


SINGLES_DIR="/home/chris/htest/data/intermediate/singles_merged"
PRESSURES_DIR="/home/chris/htest/data/raw/pressures"

SINGLES_OUT="/home/chris/htest/data/intermediate/all_singles.grib"
PRESSURES_OUT="/home/chris/htest/data/intermediate/all_pressures.grib"

singles_files=("$SINGLES_DIR"/era5_sfc_an_*.grib)
pressures_files=("$PRESSURES_DIR"/era5_pl_*.grib)

# check that all 192 files exist (16 yrs * 12 months) 

if [ "${#singles_files[@]}" -ne "$EXPECTED" ]; then
    echo "ERROR: Expected $EXPECTED surface GRIB files, found ${#sfc_files[@]}." >&2
    exit 1
fi

if [ "${#pressures_files[@]}" -ne "$EXPECTED" ]; then
    echo "ERROR: Expected $EXPECTED pressure-level GRIB files, found ${#pl_files[@]}." >&2
    exit 1
fi

echo "Found ${#singles_files[@]} surface GRIB files."
echo "Found ${#pressures_files[@]} pressure-level GRIB files."

# cat
cat "${singles_files[@]}" > "$SINGLES_OUT"
cat "${pressures_files[@]}" > "$PRESSURES_OUT"

echo "Created:"
echo "  $SINGLES_OUT"
echo "  $PRESSURES_OUT"