#!/usr/bin/env bash
set -eo pipefail
. /opt/openfoam14/etc/bashrc
set -u
rm -rf nx290w
cp -r "$FOAM_TUTORIALS/incompressibleFluid/motorBike/motorBike" nx290w
python3 cfd/nx290w_setup.py nx290w 5.635451667
cd nx290w
surfaceCheck constant/geometry/motorBike.stl | tee log.surfaceCheck
blockMesh | tee log.blockMesh
snappyHexMesh -overwrite | tee log.snappyHexMesh
checkMesh -allGeometry -allTopology | tee log.checkMesh
potentialFoam -initialiseUBCs | tee log.potentialFoam
foamRun | tee log.foamRun
{
 echo '=== CHECKMESH ==='
 grep -E 'cells:|Max aspect ratio|Mesh non-orthogonality|Max skewness|Failed|Mesh OK' log.checkMesh || true
 echo '=== SOLVER TAIL ==='
 tail -80 log.foamRun
 echo '=== FORCE FILES ==='
 find postProcessing -type f -maxdepth 5 -print 2>/dev/null || true
 echo '=== FORCE TAIL ==='
 f=$(find postProcessing -type f \( -name 'coefficient.dat' -o -name 'forceCoeffs.dat' \) | head -1 || true)
 if [ -n "$f" ]; then tail -40 "$f"; fi
} | tee nx290w_summary.txt
