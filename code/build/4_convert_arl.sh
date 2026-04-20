#!/bin/bash
# convert_to_arl.sh

if [ ! -L /home/chris/htest ]; then
    ln -s /home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants/home/chris/htest
fi

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
EOF

chmod +x ~/htest/code/build/4_convert_arl.sh