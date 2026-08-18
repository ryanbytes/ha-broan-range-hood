#!/usr/bin/env python3
from pathlib import Path
import math, re, sys

case = Path(sys.argv[1])
U = float(sys.argv[2]) if len(sys.argv) > 2 else 5.635451667
SCALE = 30.0
geom = [
    ('center', 296.364, 19.2111, 8.25033, 0.0),
    ('starboard', 274.673, 10.4012, 5.22519, 19.7994),
    ('port', 274.673, 10.4012, 5.22519, -19.7994),
]

def hb(x,z,L,B,T):
    xi = 2*x/L - 1
    eta = abs(z)/T
    return 0.5*B*max(0.0, 1-xi*xi)*max(0.0, 1-eta*eta)

def normal(a,b,c):
    ux,uy,uz = (b[i]-a[i] for i in range(3))
    vx,vy,vz = (c[i]-a[i] for i in range(3))
    n = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
    m = math.sqrt(sum(q*q for q in n)) or 1.0
    return tuple(q/m for q in n)

def area2(a,b,c):
    ux,uy,uz = (b[i]-a[i] for i in range(3))
    vx,vy,vz = (c[i]-a[i] for i in range(3))
    cr = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
    return math.sqrt(sum(q*q for q in cr))

def write_tri(f,a,b,c):
    n = normal(a,b,c)
    f.write(f'  facet normal {n[0]:.8e} {n[1]:.8e} {n[2]:.8e}\n    outer loop\n')
    for p in (a,b,c):
        f.write(f'      vertex {p[0]:.8e} {p[1]:.8e} {p[2]:.8e}\n')
    f.write('    endloop\n  endfacet\n')

def tri_key(t):
    # STL vertices are merged by coordinates by OpenFOAM; dedupe the six
    # collapsed stem/keel corner triangles regardless of winding.
    return tuple(sorted(tuple(round(q,10) for q in p) for p in t))

def stl(path,nx=121,nz=41):
    seen=set()
    written=0
    with open(path,'w') as f:
        f.write('solid motorBike\n')
        for _,Lf,Bf,Tf,y0f in geom:
            L,B,T,yc = Lf/SCALE, Bf/SCALE, Tf/SCALE, y0f/SCALE
            xs=[L*i/(nx-1) for i in range(nx)]
            zs=[-T+2*T*k/(nz-1) for k in range(nz)]
            for side in (-1,1):
                for i in range(nx-1):
                    for k in range(nz-1):
                        pts=[]
                        for ii,kk in ((i,k),(i+1,k),(i+1,k+1),(i,k+1)):
                            x,z=xs[ii],zs[kk]
                            y=yc+side*hb(x*SCALE,z*SCALE,Lf,Bf,Tf)/SCALE
                            pts.append((x,y,z))
                        a,b,c,d=pts
                        # Outward winding: negative-y side uses the natural
                        # x-z parameter winding; positive-y side is reversed.
                        ts=((a,b,c),(a,c,d)) if side < 0 else ((a,c,b),(a,d,c))
                        for t in ts:
                            if area2(*t) <= 1e-12:
                                continue
                            key=tri_key(t)
                            if key in seen:
                                continue
                            seen.add(key)
                            write_tri(f,*t)
                            written += 1
        f.write('endsolid motorBike\n')
    print('STL triangles', written)

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
    (-5 -3 -1.5)
    (20 -3 -1.5)
    (20 3 -1.5)
    (-5 3 -1.5)
    (-5 -3 1.5)
    (20 -3 1.5)
    (20 3 1.5)
    (-5 3 1.5)
);
blocks
(
    hex (0 1 2 3 4 5 6 7) (50 18 10) simpleGrading (1 1 1)
);
boundary
(
    front
    {
        type symmetryPlane;
        faces ((0 1 5 4));
    }
    back
    {
        type symmetryPlane;
        faces ((3 7 6 2));
    }
    inlet
    {
        type patch;
        faces ((0 4 7 3));
    }
    outlet
    {
        type patch;
        faces ((1 2 6 5));
    }
    lowerWall
    {
        type symmetryPlane;
        faces ((0 3 2 1));
    }
    upperWall
    {
        type symmetryPlane;
        faces ((4 5 6 7));
    }
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
    nearHull { type box; min (-0.5 -1.1 -0.5); max (10.5 1.1 0.5); }
    wakeBox { type box; min (7 -1.4 -0.65); max (18 1.4 0.65); }
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
    nSmoothPatch 3;
    tolerance 2;
    nSolveIter 30;
    nRelaxIter 5;
}
addLayersControls
{
    relativeSizes false;
    layers { "motorBike.*" { nSurfaceLayers 5; } }
    expansionRatio 1.25;
    firstLayerThickness 0.0005;
    minThickness 0.00015;
    nGrow 0;
    featureAngle 80;
    slipFeatureAngle 30;
    nRelaxIter 5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 50;
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

# Adapt the motorBike tutorial fields to the ship surface and make both
# vertical domain limits symmetry planes (true double-body outer domain).
for fn in ['U','p','nuTilda','nut','k']:
    p=case/'0'/fn
    if not p.exists():
        continue
    s=p.read_text().replace('motorBike_.*','motorBike.*')
    if fn=='U':
        s=s.replace('(20 0 0)',f'({U:.9f} 0 0)')
    s=re.sub(r'lowerWall\s*\{.*?\}', 'lowerWall\n    {\n        type symmetryPlane;\n    }', s, flags=re.S)
    p.write_text(s)

# Keep only the force coefficient function object so post-processing is
# deterministic and does not inherit the motorBike cut-plane/streamline setup.
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
endTime 250;
deltaT 1;
writeControl timeStep;
writeInterval 250;
purgeWrite 0;
writeFormat ascii;
writePrecision 8;
writeCompression off;
timeFormat general;
timePrecision 6;
runTimeModifiable true;
''')
print('configured',U)
