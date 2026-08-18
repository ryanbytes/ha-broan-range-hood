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

NPROC="${NX290W_NPROC:-4}"
ENDTIME="${NX290W_ENDTIME:-350}"

# OpenFOAM 14 foamDictionary nested paths use '/', not dotted key names.
foamDictionary -set "numberOfSubdomains=$NPROC" system/decomposeParDict
foamDictionary -set "UMean=$MODEL_MPS" 0/U
foamDictionary -set "endTime=$ENDTIME" system/controlDict
foamDictionary -set "writeInterval=50" system/controlDict
foamDictionary -set "castellatedMeshControls/insidePoint=(8 5 1)" system/snappyHexMeshDict
foamDictionary -set "castellatedMeshControls/maxGlobalCells=450000" system/snappyHexMeshDict
# Validation mesh: remove boundary-layer extrusion so the first corrected
# full-width run can finish on the free runner. Re-enable layers for medium/final grids.
foamDictionary -set "addLayers=false" system/snappyHexMeshDict

cp "$ROOT/DTC-scaled.stl" "$CASE/constant/geometry/DTC-scaled.stl"

echo "NX-290W target ${FULL_KN} kn; model speed ${MODEL_MPS} m/s; ranks ${NPROC}; endTime ${ENDTIME}"
echo "Validation pass: symmetric full-width mesh, addLayers=false"
./Allrun 2>&1 | tee "NX290W_${FULL_KN}kn.log"
python3 "$ROOT/postprocess_forces.py" "$CASE" "$FULL_KN" | tee "$CASE/NX290W_summary.txt"
