#!/bin/bash
set -eo pipefail
FULL_KN="${1:-60}"
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ -f /opt/openfoam14/etc/bashrc ]; then
    source /opt/openfoam14/etc/bashrc
elif [ -f /opt/OpenFOAM/OpenFOAM-14/etc/bashrc ]; then
    source /opt/OpenFOAM/OpenFOAM-14/etc/bashrc
elif [ -n "${WM_PROJECT_DIR:-}" ] && [ -f "$WM_PROJECT_DIR/etc/bashrc" ]; then
    source "$WM_PROJECT_DIR/etc/bashrc"
else
    echo "OpenFOAM 14 environment not found" >&2; exit 2
fi

MODEL_MPS="$(python3 - <<PY
import math
print(float("$FULL_KN")*0.514444/math.sqrt(50.0))
PY
)"
CASE="$ROOT/runs/NX290W_${FULL_KN}kn_1to50"
mkdir -p "$ROOT/runs"; rm -rf "$CASE"
cp -a "$FOAM_TUTORIALS/incompressibleVoF/DTCHull" "$CASE"
cp -a "$ROOT/overlay/." "$CASE/"
chmod +x "$CASE/Allmesh" "$CASE/Allrun"
cd "$CASE"

NPROC="${NX290W_NPROC:-2}"
foamDictionary system/decomposeParDict -entry numberOfSubdomains -set "$NPROC"
foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls.insidePoint -set '(8 5 1)'
foamDictionary system/functions -entry forces.CofR -set '(0 0 0.244)'
foamDictionary 0/U -entry UMean -set "$MODEL_MPS"
foamDictionary system/controlDict -entry endTime -set "${NX290W_ENDTIME:-600}"
foamDictionary system/controlDict -entry writeInterval -set 100
foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls.maxGlobalCells -set 650000
cp "$ROOT/DTC-scaled.stl" "$CASE/constant/geometry/DTC-scaled.stl"

echo "NX-290W target ${FULL_KN} kn; model speed ${MODEL_MPS} m/s; ranks ${NPROC}"
./Allrun 2>&1 | tee "NX290W_${FULL_KN}kn.log"
python3 "$ROOT/postprocess_forces.py" "$CASE" "$FULL_KN" | tee "$CASE/NX290W_summary.txt"
