#!/usr/bin/env python3
from pathlib import Path
import math, re, sys

case = Path(sys.argv[1])
U = float(sys.argv[2]) if len(sys.argv) > 2 else 5.635451667
SCALE = 30.0
# Full-scale design dimensions. The exponent is calibrated so the triangulated
# 1:30 double-body displaces exactly the prior 34,146.25 m^3 submerged target.
P_EXP = 0.8422191115379334
geom = [
    ('center', 296.364, 19.2111, 8.25033, 0.0),
    ('starboard', 274.673, 10.4012, 5.22519, 19.7994),
    ('port', 274.673, 10.4012, 5.22519, -19.7994),
]

def normal(a,b,c):
    ux,uy,uz = (b[i]-a[i] for i in range(3))
    vx,vy,vz = (c[i]-a[i] for i in range(3))
    n=(uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
    m=math.sqrt(sum(q*q for q in n)) or 1.0
    return tuple(q/m for q in n)

def write_tri(f,a,b,c):
    n=normal(a,b,c)
    f.write(f'  facet normal {n[0]:.8e} {n[1]:.8e} {n[2]:.8e}\n    outer loop\n')
    for p in (a,b,c):
        f.write(f'      vertex {p[0]:.8e} {p[1]:.8e} {p[2]:.8e}\n')
    f.write('    endloop\n  endfacet\n')

def stl(path,nx=121,nt=80):
    # Smooth, closed, volume-matched double-body. Elliptical perimeter rings
    # taper continuously to single bow/stern points; no seam or singular corner
    # triangles. Each component is a separate watertight genus-0 surface.
    ntri=0
    with open(path,'w') as f:
        f.write('solid motorBike\n')
        for _,Lf,Bf,Tf,y0f in geom:
            L,B,T,yc=Lf/SCALE,Bf/SCALE,Tf/SCALE,y0f/SCALE
            verts=[(0.0,yc,0.0)]
            rings=[]
            for i in range(1,nx-1):
                x=L*i/(nx-1)
                xi=2*x/L-1
                ff=max(0.0,1-xi*xi)**P_EXP
                ring=[]
                for j in range(nt):
                    th=2*math.pi*j/nt
                    ring.append(len(verts))
                    verts.append((x, yc+0.5*B*ff*math.cos(th), T*ff*math.sin(th)))
                rings.append(ring)
            stern=len(verts)
            verts.append((L,yc,0.0))
            r0=rings[0]
            for j in range(nt):
                jp=(j+1)%nt
                write_tri(f,verts[0],verts[r0[jp]],verts[r0[j]]); ntri+=1
            for ri in range(len(rings)-1):
                ra,rb=rings[ri],rings[ri+1]
                for j in range(nt):
                    jp=(j+1)%nt
                    a,b,c,d=ra[j],rb[j],rb[jp],ra[jp]
                    write_tri(f,verts[a],verts[c],verts[b]); ntri+=1
                    write_tri(f,verts[a],verts[d],verts[c]); ntri+=1
            rl=rings[-1]
            for j in range(nt):
                jp=(j+1)%nt
                write_tri(f,verts[stern],verts[rl[j]],verts[rl[jp]]); ntri+=1
        f.write('endsolid motorBike\n')
    print('STL triangles',ntri)

gd=case/'constant'/'geometry'
gd.mkdir(parents=True,exist_ok=True)
for p in gd.iterdir():
    if p.is_file(): p.unlink()
stl(gd/'motorBike.stl')

(case/'constant'/'physicalProperties').write_text('''FoamFile
{
    format ascii;
    class dictionary;
    location "constant";
    object physicalProperties;
}
viscosityModel constant;
nu 1.0e-06;
''')

(case/'system'/'blockMeshDict').write_text('''FoamFile
{
    format ascii;
    class dictionary;
    location "system";
    object blockMeshDict;
}
vertices
(
    (-5 -3 -1.5) (20 -3 -1.5) (20 3 -1.5) (-5 3 -1.5)
    (-5 -3  1.5) (20 -3  1.5) (20 3  1.5) (-5 3  1.5)
);
blocks
(
    hex (0 1 2 3 4 5 6 7) (50 18 10) simpleGrading (1 1 1)
);
boundary
(
    front { type symmetryPlane; faces ((0 1 5 4)); }
    back { type symmetryPlane; faces ((3 7 6 2)); }
    inlet { type patch; faces ((0 4 7 3)); }
    outlet { type patch; faces ((1 2 6 5)); }
    lowerWall { type symmetryPlane; faces ((0 3 2 1)); }
    upperWall { type symmetryPlane; faces ((4 5 6 7)); }
);
''')

(case/'system'/'snappyHexMeshDict').write_text('''FoamFile
{
    format ascii;
    class dictionary;
    location "system";
    object snappyHexMeshDict;
}
castellatedMesh true;
snap true;
addLayers true;
geometry
{
    motorBike { type triSurface; file "motorBike.stl"; }
    nearHull { type box; min (-0.5 -1.1 -0.55); max (10.5 1.1 0.55); }
    wakeBox { type box; min (7 -1.4 -0.7); max (18 1.4 0.7); }
}
castellatedMeshControls
{
    maxLocalCells 1000000;
    maxGlobalCells 1800000;
    minRefinementCells 0;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 2;
    features ();
    refinementSurfaces
    {
        motorBike
        {
            level (2 3);
            patchInfo { type wall; }
        }
    }
    resolveFeatureAngle 45;
    refinementRegions
    {
        nearHull { mode inside; level 2; }
        wakeBox { mode inside; level 2; }
    }
    insidePoint (-3.25 2.15 0.85);
    allowFreeStandingZoneFaces false;
}
snapControls
{
    nSmoothPatch 5;
    tolerance 2;
    nSolveIter 50;
    nRelaxIter 8;
}
addLayersControls
{
    relativeSizes false;
    layers { "motorBike.*" { nSurfaceLayers 5; } }
    expansionRatio 1.22;
    firstLayerThickness 0.00035;
    minThickness 0.00010;
    nGrow 0;
    featureAngle 100;
    slipFeatureAngle 30;
    nRelaxIter 8;
    nSmoothSurfaceNormals 2;
    nSmoothNormals 5;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 60;
}
meshQualityControls
{
    maxNonOrtho 70;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave 80;
    minVol 1e-13;
    minTetQuality 1e-15;
    minArea -1;
    minTwist 0.02;
    minDeterminant 0.001;
    minFaceWeight 0.02;
    minVolRatio 0.01;
    minTriangleTwist -1;
    nSmoothScale 4;
    errorReduction 0.75;
}
writeFlags (scalarLevels layerSets layerFields);
mergeTolerance 1e-6;
''')

# Adapt motorBike tutorial fields to the ship and water. SA freestream nuTilda
# is initialized at 3*nu rather than the motorBike tutorial's 0.05 m^2/s.
for fn in ['U','p','nuTilda','nut','k']:
    p=case/'0'/fn
    if not p.exists(): continue
    s=p.read_text().replace('motorBike_.*','motorBike.*')
    if fn=='U': s=s.replace('(20 0 0)',f'({U:.9f} 0 0)')
    if fn=='nuTilda': s=s.replace('uniform 0.05','uniform 3e-06')
    s=re.sub(r'lowerWall\s*\{.*?\}', 'lowerWall\n    {\n        type symmetryPlane;\n    }', s, flags=re.S)
    p.write_text(s)

(case/'system'/'functions').write_text('''FoamFile
{
    format ascii;
    class dictionary;
    location "system";
    object functions;
}
#includeFunc forceCoeffs
''')
(case/'system'/'forceCoeffs').write_text(f'''type forceCoeffs;
libs ("libforces.so");
writeControl timeStep;
writeInterval 1;
log yes;
patches ("motorBike.*");
rho rhoInf;
rhoInf 1025;
liftDir (0 0 1);
dragDir (1 0 0);
CofR (4.9 0 0);
pitchAxis (0 1 0);
magUInf {U:.9f};
lRef 1;
Aref 1;
''')

# Robust first-order RANS pass. Once converged, a later verification pass can
# switch U back to linearUpwind on the same geometry.
(case/'system'/'fvSchemes').write_text('''FoamFile
{
    format ascii;
    class dictionary;
    location "system";
    object fvSchemes;
}
ddtSchemes { default steadyState; }
gradSchemes
{
    default Gauss linear;
    grad(U) cellLimited Gauss linear 1;
    grad(nuTilda) cellLimited Gauss linear 1;
}
divSchemes
{
    default none;
    div(phi,U) bounded Gauss upwind;
    div(phi,nuTilda) bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear limited 0.5; }
interpolationSchemes { default linear; }
snGradSchemes { default limited 0.5; }
wallDist { method meshWave; }
''')

(case/'system'/'fvSolution').write_text('''FoamFile
{
    format ascii;
    class dictionary;
    location "system";
    object fvSolution;
}
solvers
{
    p
    {
        solver GAMG;
        tolerance 1e-08;
        relTol 0.05;
        smoother GaussSeidel;
    }
    pFinal
    {
        $p;
        tolerance 1e-08;
        relTol 0;
    }
    Phi { $p; }
    "(U|nuTilda)"
    {
        solver smoothSolver;
        smoother GaussSeidel;
        tolerance 1e-09;
        relTol 0.05;
    }
}
SIMPLE
{
    nNonOrthogonalCorrectors 1;
    residualControl
    {
        p 1e-5;
        U 1e-5;
        nuTilda 1e-5;
    }
}
potentialFlow { nNonOrthogonalCorrectors 10; }
relaxationFactors
{
    fields { p 0.2; }
    equations { U 0.25; nuTilda 0.3; }
}
cache { grad(U); }
''')

(case/'system'/'controlDict').write_text('''FoamFile
{
    format ascii;
    class dictionary;
    location "system";
    object controlDict;
}
solver incompressibleFluid;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime 600;
deltaT 1;
writeControl timeStep;
writeInterval 600;
purgeWrite 0;
writeFormat ascii;
writePrecision 8;
writeCompression off;
timeFormat general;
timePrecision 6;
runTimeModifiable true;
''')
print('configured',U)
