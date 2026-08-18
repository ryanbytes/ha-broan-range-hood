#!/usr/bin/env bash
set -eo pipefail
set +u
. /opt/openfoam14/etc/bashrc
set -u

SPEED="${1:-5.635451667}"
ITERS="${2:-500}"
CASE="nx290w-free-${SPEED}"
rm -rf "$CASE"
cp -r "$FOAM_TUTORIALS/incompressibleVoF/DTCHull" "$CASE"
rm -rf "$CASE"/processor* "$CASE"/[1-9]* "$CASE"/postProcessing
python3 cfd/free_surface_setup.py "$CASE" "$SPEED" "$ITERS"
cd "$CASE"

surfaceCheck constant/geometry/NX290W.stl 2>&1 | tee log.surfaceCheck
blockMesh 2>&1 | tee log.blockMesh
snappyHexMesh -overwrite 2>&1 | tee log.snappyHexMesh
checkMesh -allGeometry -allTopology 2>&1 | tee log.checkMesh

decomposePar 2>&1 | tee log.decomposePar
mpirun --oversubscribe -np 4 foamRun -parallel 2>&1 | tee log.foamRun
reconstructPar -latestTime 2>&1 | tee log.reconstructPar || true

{
  echo "NX-290W FREE-SURFACE CFD"
  echo "MODEL_SPEED_MPS=$SPEED"
  echo "ITERATIONS=$ITERS"
  echo "=== SURFACE ==="
  grep -E 'Triangles|Bounding Box|Surface has|Surface is|unconnected parts|normal orientation|End' log.surfaceCheck || true
  echo "=== LAYERS ==="
  grep -Ei 'layer|extrud|faces.*layer|cells.*layer' log.snappyHexMesh | tail -80 || true
  echo "=== CHECKMESH ==="
  grep -E 'cells:|faces:|Max aspect ratio|Mesh non-orthogonality|Max skewness|concave|Failed|Mesh OK' log.checkMesh || true
  echo "=== SOLVER TAIL ==="
  tail -100 log.foamRun
  echo "=== FORCE FILES ==="
  find . -path '*postProcessing*' -type f -maxdepth 8 -print 2>/dev/null || true
  echo "=== FORCE TAIL ==="
  f=$(find . -path '*postProcessing*' -type f \( -name 'force.dat' -o -name 'forces.dat' \) | head -1 || true)
  if [ -n "$f" ]; then tail -80 "$f"; fi
} | tee nx290w_free_surface_summary.txt
