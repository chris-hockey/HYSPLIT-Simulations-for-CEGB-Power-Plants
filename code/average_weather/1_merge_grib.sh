#!/bin/bash
set -euo pipefail

# Create short symlink if it doesn't exist
if [ ! -L /home/chris/htest ]; then
    ln -s \
        /home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants \
        /home/chris/htest
fi

SINGLES_DIR="/home/chris/htest/data/intermediate/singles_merged"
PRESSURES_DIR="/home/chris/htest/data/raw/pressures"

SINGLES_OUT="/home/chris/htest/data/intermediate/all_singles.grib"
PRESSURES_OUT="/home/chris/htest/data/intermediate/pressure_925_tuv.grib"

# check that all 192 files exist (16 years * 12 months)
EXPECTED=192

singles_files=("$SINGLES_DIR"/era5_sfc_an_*.grib)
pressures_files=("$PRESSURES_DIR"/era5_pl_*.grib)

if [ "${#singles_files[@]}" -ne "$EXPECTED" ]; then
    echo "ERROR: Expected $EXPECTED surface GRIB files, found ${#singles_files[@]}." >&2
    exit 1
fi

if [ "${#pressures_files[@]}" -ne "$EXPECTED" ]; then
    echo "ERROR: Expected $EXPECTED pressure-level GRIB files, found ${#pressures_files[@]}." >&2
    exit 1
fi

echo "Found ${#singles_files[@]} surface GRIB files."
echo "Found ${#pressures_files[@]} pressure-level GRIB files."

rm -f "$SINGLES_OUT" "$PRESSURES_OUT"

echo "Merging surface GRIBs..."
cat "${singles_files[@]}" > "$SINGLES_OUT"
echo "Surface merge complete: $(du -h "$SINGLES_OUT" | cut -f1)"

# extract only t, u and v at 925 hPa while merging pressure GRIBs
echo "Extracting t, u and v at 925 hPa..."
grib_copy \
    -w shortName=t/u/v,level=925 \
    "${pressures_files[@]}" \
    "$PRESSURES_OUT"

echo "Pressure extraction complete: $(du -h "$PRESSURES_OUT" | cut -f1)"

echo "Done."