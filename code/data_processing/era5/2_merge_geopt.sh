#!/bin/bash
#
# Merge the static ERA5 geopotential field into each monthly surface file,
# timestamped to match.
#
# era52arl requires terrain height on the same time axis as the surface
# fields, but the geopotential is downloaded once as a static field. For each
# monthly file in data/raw/singles, this clones the static field to every
# 6-hourly timestamp (taken from 2m temperature) and concatenates it onto the
# surface records.
#
# Output: data/intermediate/singles_merged/era5_sfc_an_YYYY_MM_z.grib, the
# auxiliary input to 3_convert_arl.sh.
#
# Author: Christopher Hockey
# chrishockey2@gmail.com
# August 2026

set -euo pipefail
shopt -s nullglob

# create short symlink if it doesn't exist
if [ ! -L /home/chris/htest ]; then
    ln -s /home/chris/Documents/cfpp_hysplit/HYSPLIT-Simulations-for-CEGB-Power-Plants /home/chris/htest
fi

RAW_SINGLES="/home/chris/htest/data/raw/singles"
GEOPOTENTIAL="/home/chris/htest/data/raw/geopot/geopot.grib"
MERGED_SINGLES="/home/chris/htest/data/intermediate/singles_merged"

mkdir -p "$MERGED_SINGLES"

if [ ! -f "$GEOPOTENTIAL" ]; then
    echo "ERROR: geopotential file not found at $GEOPOTENTIAL"
    exit 1
fi

for sfc_file in "$RAW_SINGLES"/era5_sfc_an_????_??.grib; do
    if [ ! -f "$sfc_file" ]; then
        echo "WARNING: no monthly surface files found in $RAW_SINGLES"
        exit 1
    fi

    base=$(basename "$sfc_file" .grib)
    out_file="${MERGED_SINGLES}/${base}_z.grib"

    echo "Building timestamped geopotential merge for ${base}..."

    tmpdir=$(mktemp -d /tmp/geopot_merge.XXXXXX)
    z_all="${tmpdir}/z_all.grib"

    # Get one timestamp per 6-hourly period using 2m temperature as the clock.
    grib_get -w shortName=2t -p dataDate,dataTime "$sfc_file" |
    while read -r date time; do
        [ -z "${date:-}" ] && continue

        z_one="${tmpdir}/z_${date}_${time}.grib"

        # Clone the static geopotential field to this timestamp.
        grib_set \
            -s dataDate="${date}",dataTime="${time}" \
            "$GEOPOTENTIAL" \
            "$z_one"

        cat "$z_one" >> "$z_all"
    done

    n_time=$(grib_get -w shortName=2t -p dataDate,dataTime "$sfc_file" | wc -l)
    n_z=$(grib_count "$z_all")

    if [ "$n_time" -ne "$n_z" ]; then
        echo "ERROR: expected $n_time timestamped z records, got $n_z"
        rm -rf "$tmpdir"
        exit 1
    fi

    rm -f "$out_file"

    # Merge original monthly surface fields plus timestamped geopotential.
    grib_copy "$sfc_file" "$z_all" "$out_file"

    echo "  Done: $(basename "$out_file") with $n_z timestamped z records"

    rm -rf "$tmpdir"
done

echo "Geopotential timestamp merge complete."