#!/usr/bin/env bash
# preflight.sh — go/no-go checks before launching the production HYSPLIT run.
# Run from project root with the Python venv active.
# Exit codes: 0 = GO, 1 = NO-GO.
#
# Override the package name if your import path differs:
#     HYSPLIT_PKG=my_pkg ./preflight.sh

set -u

PKG="${HYSPLIT_PKG:-cfpp_hysplit}"
MIN_FREE_GB="${MIN_FREE_GB:-200}"
# FY 1974/75 through 1987/88 = 168 months, +1 (April 1988) for RUN_HRS spillover.
MIN_ARL="${MIN_ARL:-169}"

fail=0
say()    { printf "  %-55s %s\n" "$1" "$2"; }
check()  {
    local desc="$1"; shift
    if eval "$@" >/dev/null 2>&1; then say "$desc" "OK"
    else say "$desc" "FAIL"; fail=1; fi
}

echo "=== environment ==="
check "python venv active"           '[[ -n ${VIRTUAL_ENV:-} ]]'
check "tmux installed"               'command -v tmux'
check "git working tree clean"       'git diff --quiet && git diff --cached --quiet'
check "git HEAD is tagged"           'git describe --exact-match --tags HEAD'

echo
echo "=== paths (from ${PKG}.paths) ==="
paths_env=$(python -c "
from ${PKG}.paths import (
    HYCS_STD, CON2CDF4, ARL_DIR, PANEL_PATH,
    RUNS_DIR, MONTHLY_DIR, ANNUAL_DIR, SIM_ROOT,
)
for name in ('HYCS_STD','CON2CDF4','ARL_DIR','PANEL_PATH',
            'RUNS_DIR','MONTHLY_DIR','ANNUAL_DIR','SIM_ROOT'):
    print(f'export {name}={eval(name)}')
" 2>/dev/null) || { say "import ${PKG}.paths" "FAIL"; echo; echo "NO-GO"; exit 1; }
eval "$paths_env"

check "hycs_std executable"          '[[ -x $HYCS_STD ]]'
check "con2cdf4 executable"          '[[ -x $CON2CDF4 ]]'
check "panel readable"               '[[ -r $PANEL_PATH ]]'
check "ARL dir exists"               '[[ -d $ARL_DIR ]]'
mkdir -p "$SIM_ROOT" 2>/dev/null
check "sim root writable"            '[[ -w $SIM_ROOT ]]'

echo
echo "=== data ==="
n_arl=$(find "$ARL_DIR" -maxdepth 1 -name 'era5_*.arl' 2>/dev/null | wc -l)
check "ARL files >= $MIN_ARL (found $n_arl)"       "(( $n_arl >= $MIN_ARL ))"

n_rows=$(python -c "import pandas as pd; print(len(pd.read_csv('$PANEL_PATH')))" 2>/dev/null || echo 0)
check "panel rows > 0 (found $n_rows)"             "(( ${n_rows:-0} > 0 ))"

echo
echo "=== disk ==="
free_gb=$(df -BG "$SIM_ROOT" | awk 'NR==2{gsub("G","",$4); print $4+0}')
check "free space >= ${MIN_FREE_GB} GB ($free_gb GB)"  "(( ${free_gb:-0} >= $MIN_FREE_GB ))"

echo
echo "=== system (day-of) ==="
check "sleep.target masked"          'systemctl is-masked -q sleep.target'
check "suspend.target masked"        'systemctl is-masked -q suspend.target'
check "hibernate.target masked"      'systemctl is-masked -q hibernate.target'

echo
if (( fail == 0 )); then
    echo "GO"
    exit 0
else
    echo "NO-GO — fix failures above"
    exit 1
fi