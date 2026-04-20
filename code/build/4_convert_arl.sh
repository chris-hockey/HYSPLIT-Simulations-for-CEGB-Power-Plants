#!/bin/bash
# convert_to_arl.sh

set -euo pipefail
shopt -s nullglob

HYSPLIT_ROOT="/home/chris/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public"
ERA52ARL_BIN="${HYSPLIT_ROOT}/exec/era52arl"

if [ ! -e /home/chris/htest ]; then
    ln -s /home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants /home/chris/htest
fi

INT_PRESSURE="/home/chris/htest/data/intermediate/pressures"
MERGED_SINGLES="/home/chris/htest/data/intermediate/singles_merged"
FINAL="/home/chris/htest/data/final/arl"
BUILD_DIR="$(dirname "$(realpath "$0")")"
REF_CFG="/home/chris/htest/configs/era52arl_4lev_reference.cfg"

mkdir -p "$FINAL"

echo "SCRIPT    : $(realpath "$0")"
echo "BUILD_DIR : $BUILD_DIR"
echo "REF_CFG   : $REF_CFG"
grep -E "numlev|plev|numsfc|sfcarl" "$REF_CFG"

pl_files=("${INT_PRESSURE}"/era5_pl_????_??.grib)

if [ ${#pl_files[@]} -eq 0 ]; then
    echo "WARNING: no monthly pressure files found in $INT_PRESSURE"
    exit 1
fi

for pl_path in "${pl_files[@]}"; do
    pl_file="$(basename "$pl_path")"
    year=$(echo "$pl_file" | grep -oP '\d{4}' | head -1)
    month=$(echo "$pl_file" | grep -oP '(?<=_)\d{2}(?=\.grib)')
    a_file="${MERGED_SINGLES}/era5_sfc_an_${year}_${month}_z.grib"
    out_file="${FINAL}/era5_${year}_${month}.arl"
    build_log="${FINAL}/era5_${year}_${month}_build.log"
    chk_log="${FINAL}/era5_${year}_${month}_chk.log"

    if [ ! -f "$a_file" ]; then
        echo "WARNING: no merged surface file for ${year}_${month}, skipping"
        continue
    fi

    echo "=================================================="
    echo "Converting ${year}_${month}"
    echo "PL  : $pl_path"
    echo "AUX : $a_file"
    echo "OUT : $out_file"

    rm -f "$out_file" "$build_log" "$chk_log"

    work_dir="$(mktemp -d /tmp/era52arl_work.XXXXXX)"
    cp "$REF_CFG" "$work_dir/era52arl.cfg"

    (
        cd "$work_dir"
        rm -f ERA52ARL.CFG arldata.cfg

        "$ERA52ARL_BIN" \
            -d"$work_dir/era52arl.cfg" \
            -i"$pl_path" \
            -a"$a_file" \
            -o"$out_file" \
            -v
    ) | tee "$build_log"

    printf "%s\n%s\n" "$FINAL/" "era5_${year}_${month}.arl" \
        | "$HYSPLIT_ROOT/exec/chk_file" \
        | tee "$chk_log"

    rm -rf "$work_dir"
done

echo "Conversion complete."