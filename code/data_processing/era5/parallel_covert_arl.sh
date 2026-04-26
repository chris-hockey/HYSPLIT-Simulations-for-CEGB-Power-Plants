#!/bin/bash
# convert_to_arl.sh

set -euo pipefail
shopt -s nullglob

HYSPLIT_ROOT="/home/chris/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public"
ERA52ARL_BIN="${HYSPLIT_ROOT}/exec/era52arl"
CHK_FILE_BIN="${HYSPLIT_ROOT}/exec/chk_file"

if [ ! -e /home/chris/htest ]; then
    ln -s /home/chris/Documents/hysplit_test/HYSPLIT-Simulations-for-CEGB-Power-Plants /home/chris/htest
fi

RAW_PRESSURE="/home/chris/htest/data/raw/pressures"
MERGED_SINGLES="/home/chris/htest/data/intermediate/singles_merged"
FINAL="/home/chris/htest/data/final/arl"
REF_CFG="/home/chris/htest/configs/era52arl_4lev_reference.cfg"

# Override at the command line, e.g. `JOBS=6 ./convert_to_arl.sh`
JOBS="${JOBS:-$(nproc)}"

mkdir -p "$FINAL"

echo "SCRIPT    : $(realpath "$0")"
echo "REF_CFG   : $REF_CFG"
echo "JOBS      : $JOBS"
grep -E "numlev|plev|numsfc|sfcarl" "$REF_CFG"

export ERA52ARL_BIN CHK_FILE_BIN MERGED_SINGLES FINAL REF_CFG HYSPLIT_ROOT

process_month() {
    set -euo pipefail
    local pl_path="$1"
    local pl_file year month a_file out_file build_log chk_log work_dir

    pl_file="$(basename "$pl_path")"
    # era5_pl_YYYY_MM.grib -> chars 8..11 = year, 13..14 = month
    year="${pl_file:8:4}"
    month="${pl_file:13:2}"

    a_file="${MERGED_SINGLES}/era5_sfc_an_${year}_${month}_z.grib"
    out_file="${FINAL}/era5_${year}_${month}.arl"
    build_log="${FINAL}/era5_${year}_${month}_build.log"
    chk_log="${FINAL}/era5_${year}_${month}_chk.log"

    if [ ! -f "$a_file" ]; then
        echo "[${year}_${month}] SKIP: no merged surface file ($a_file)" >&2
        return 0
    fi

    echo "[${year}_${month}] start"

    rm -f "$out_file" "$build_log" "$chk_log"

    work_dir="$(mktemp -d /tmp/era52arl_work.XXXXXX)"
    trap 'rm -rf "$work_dir"' RETURN

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
    ) >"$build_log" 2>&1

    printf '%s\n%s\n' "$FINAL/" "era5_${year}_${month}.arl" \
        | "$CHK_FILE_BIN" >"$chk_log" 2>&1

    echo "[${year}_${month}] done -> $out_file"
}
export -f process_month

pl_files=("${RAW_PRESSURE}"/era5_pl_????_??.grib)
if [ ${#pl_files[@]} -eq 0 ]; then
    echo "WARNING: no monthly pressure files found in $RAW_PRESSURE" >&2
    exit 1
fi

printf '%s\0' "${pl_files[@]}" \
    | xargs -0 -n1 -P "$JOBS" bash -c 'process_month "$0"'

echo "Conversion complete."