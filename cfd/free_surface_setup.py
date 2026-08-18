#!/usr/bin/env python3
from pathlib import Path
import math, sys, re

case = Path(sys.argv[1])
U = float(sys.argv[2])
iterations = int(sys.argv[3]) if len(sys.argv) > 3 else 500
SCALE = 30.0
# Full-scale principal geometry: L, B, draft, transverse centerline.
hulls = [
    (296.364, 19.2111, 8.25033, 0.0),
    (274.673, 10.4012, 5.22519, 19.7994),
    (274.673, 10.4012, 5.22519, -19.7994),
]

def normal(a,b,c):
    ux,uy,uz=(b[i]-a[i] for i in range(3)); vx,vy,vz=(c[i]-a[i] for i in range(3))
    n=(uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
    m=math.sqrt(sum(q*q for q in n))
    return n,m

def write_tri(f,a,b,c,target):
    n,m=normal(a,b,c)
    if m < 1e-12: return
    if sum(n[i]*target[i] for i in range(3)) < 0:
        b,c=c,b; n,m=normal(a,b,c)
    n=tuple(q/m for q in n)
    f.write(f'  facet normal {n[0]:.9e} {n[1]:.9e} {n[2]:.9e}\n    outer loop\n')
    for p in (a,b,c): f.write(f'      vertex {p[0]:.9e} {p[1]:.9e} {p[2]:.9e}\n')
    f.write('    endloop\n  endfacet\n')

def generate_hulls(path, nx=121, nt=96):
    with open(path,'w') as f:
        f.write('solid hull\n')
        for Lf,Bf,Tf,ycf in hulls:
            L,B,T,yc = Lf/SCALE, Bf/SCALE, Tf/SCALE, ycf/SCALE
            rings=[]
            for i in range(1,nx-1):
                x=L*i/(nx-1)
                xi=2*x/L-1
                sx=max(0.0,1-xi*xi)
                ring=[]
                for j in range(nt):
                    th=2*math.pi*j/nt
                    ring.append((x, yc+0.5*B*sx*math.cos(th), T*math.sin(th)))
                rings.append(ring)
            for ri in range(len(rings)-1):
                r0,r1=rings[ri],rings[ri+1]
                for j in range(nt):
                    k=(j+1)%nt
                    a,b,c,d=r0[j],r1[j],r1[k],r0[k]
                    cy=(a[1]+b[1]+c[1]+d[1])/4-yc
                    cz=(a[2]+b[2]+c[2]+d[2])/4
                    target=(0,cy,cz)
                    write_tri(f,a,b,c,target); write_tri(f,a,c,d,target)
            bow=(0.0,yc,0.0); stern=(L,yc,0.0)
            first,last=rings[0],rings[-1]
            for j in range(nt):
                k=(j+1)%nt
                write_tri(f,bow,first[k],first[j],(-1,0,0))
                write_tri(f,stern,last[j],last[k],(1,0,0))
        f.write('endsolid hull\n')

geom=case/'constant'/'geometry'; geom.mkdir(parents=True,exist_ok=True)
for p in geom.iterdir():
    if p.is_file(): p.unlink()
generate_hulls(geom/'NX290W.stl')

# Multi-block background mesh with concentrated vertical resolution around z=0 free surface.
x0,x1=-4.0,18.0; y0,y1=-2.8,2.8
zs=[-1.2,-0.4,-0.08,0.08,0.4,1.2]
zcells=[10,12,16,12,10]
verts=[]
for z in zs:
    verts += [(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)]
blocks=[]
for i,nz in enumerate(zcells):
    a=4*i; b=4*(i+1)
    blocks.append(f'    hex ({a} {a+1} {a+2} {a+3} {b} {b+1} {b+2} {b+3}) (65 28 {nz}) simpleGrading (1 1 1)')
inlet=[]; outlet=[]; side_neg=[]; side_pos=[]
for i in range(len(zcells)):
    a=4*i; b=4*(i+1)
    inlet.append(f'            ({a} {b} {b+3} {a+3})')
    outlet.append(f'            ({a+1} {a+2} {b+2} {b+1})')
    side_neg.append(f'            ({a} {a+1} {b+1} {b})')
    side_pos.append(f'            ({a+3} {b+3} {b+2} {a+2})')
top=4*(len(zs)-1)
block = '''FoamFile\n{\n    format ascii;\n    class dictionary;\n    location "system";\n    object blockMeshDict;\n}\nconvertToMeters 1;\nvertices\n(\n''' + '\n'.join(f'    ({x} {y} {z})' for x,y,z in verts) + '''\n);\nblocks\n(\n''' + '\n'.join(blocks) + '''\n);\nedges ();\nboundary\n(\n    inlet\n    {\n        type patch;\n        faces\n        (\n''' + '\n'.join(inlet) + '''\n        );\n    }\n    outlet\n    {\n        type patch;\n        faces\n        (\n''' + '\n'.join(outlet) + '''\n        );\n    }\n    sideNeg\n    {\n        type symmetryPlane;\n        faces\n        (\n''' + '\n'.join(side_neg) + '''\n        );\n    }\n    sidePos\n    {\n        type symmetryPlane;\n        faces\n        (\n''' + '\n'.join(side_pos) + '''\n        );\n    }\n    bottom\n    {\n        type symmetryPlane;\n        faces ((0 3 2 1));\n    }\n    atmosphere\n    {\n        type patch;\n        faces ((%d %d %d %d));\n    }\n);\nmergePatchPairs ();\n''' % (top,top+1,top+2,top+3)
(case/'system'/'blockMeshDict').write_text(block)

snappy='''FoamFile { format ascii; class dictionary; location "system"; object snappyHexMeshDict; }
castellatedMesh true;
snap true;
addLayers true;
geometry
{
    hull { type triSurface; file "NX290W.stl"; patchInfo { type wall; } }
    nearHull { type box; min (-0.5 -1.25 -0.45); max (10.5 1.25 0.45); }
    freeSurface { type box; min (-1.5 -1.8 -0.12); max (16.0 1.8 0.12); }
    wake { type box; min (7.0 -1.5 -0.35); max (17.0 1.5 0.35); }
}
castellatedMeshControls
{
    maxLocalCells 700000;
    maxGlobalCells 900000;
    minRefinementCells 0;
    nCellsBetweenLevels 2;
    features ();
    refinementSurfaces { hull { level (2 2); } }
    resolveFeatureAngle 45;
    refinementRegions
    {
        nearHull { mode inside; level 1; }
        freeSurface { mode inside; level 1; }
        wake { mode inside; level 1; }
    }
    insidePoint (-3.0 2.0 0.7);
    allowFreeStandingZoneFaces false;
}
snapControls
{
    nSmoothPatch 5;
    tolerance 1.5;
    nSolveIter 80;
    nRelaxIter 8;
    nFeatureSnapIter 0;
}
addLayersControls
{
    relativeSizes true;
    layers { hull { nSurfaceLayers 3; } }
    expansionRatio 1.35;
    finalLayerThickness 0.55;
    minThickness 0.12;
    nGrow 0;
    featureAngle 100;
    slipFeatureAngle 30;
    nRelaxIter 8;
    nSmoothSurfaceNormals 3;
    nSmoothNormals 5;
    nSmoothThickness 15;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 80;
    nRelaxedIter 30;
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
    relaxed { maxNonOrtho 75; maxBoundarySkewness 30; maxInternalSkewness 6; maxConcave 85; }
}
writeFlags (scalarLevels layerSets layerFields);
mergeTolerance 1e-6;
'''
(case/'system'/'snappyHexMeshDict').write_text(snappy)

(case/'0'/'U').write_text(f'''FoamFile {{ format ascii; class volVectorField; location "0"; object U; }}
UMean {U:.9f};
dimensions [velocity];
internalField uniform ($UMean 0 0);
boundaryField
{{
    #includeEtc "caseDicts/setConstraintTypes"
    inlet {{ type fixedValue; value $internalField; }}
    outlet {{ type outletPhaseMeanVelocity; alpha alpha.water; UnMean $UMean; value $internalField; }}
    atmosphere {{ type pressureInletOutletVelocity; tangentialVelocity $internalField; }}
    hull {{ type noSlip; }}
}}
''')
(case/'0'/'alpha.water').write_text('''FoamFile { format ascii; class volScalarField; location "0"; object alpha.water; }
dimensions [];
internalField
{
    type zonal;
    defaultValue 0;
    zones { water { type box; box (-999 -999 -999) (999 999 0); value 1; } }
}
boundaryField
{
    #includeEtc "caseDicts/setConstraintTypes"
    inlet
    {
        type functionalFixedValue;
        value
        {
            $internalField;
            zones { water { zone { type patch; patch inlet; } } }
        }
    }
    outlet { type variableHeightFlowRate; lowerBound 0; upperBound 1; }
    atmosphere { type inletOutlet; inletValue uniform 0; }
    hull { type zeroGradient; }
}
''')
(case/'constant'/'hRef').write_text('''FoamFile { format ascii; class uniformDimensionedScalarField; location "constant"; object hRef; }
dimensions [length];
value 0;
''')
# Seawater properties; air left from the OpenFOAM tutorial.
(case/'constant'/'physicalProperties.water').write_text('''FoamFile { format ascii; class dictionary; location "constant"; object physicalProperties.water; }
viscosityModel constant;
nu 1.0e-06;
rho 1025;
''')
(case/'system'/'decomposeParDict').write_text('''FoamFile { format ascii; class dictionary; location "system"; object decomposeParDict; }
numberOfSubdomains 4;
method scotch;
''')
(case/'system'/'functions').write_text('''FoamFile { format ascii; class dictionary; location "system"; object functions; }
forces
{
    type forces;
    libs ("libforces.so");
    patches (hull);
    log on;
    writeControl timeStep;
    writeInterval 1;
    CofR (4.9 0 0);
}
''')
(case/'system'/'controlDict').write_text(f'''FoamFile {{ format ascii; class dictionary; location "system"; object controlDict; }}
solver incompressibleVoF;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {iterations};
deltaT 1;
writeControl timeStep;
writeInterval {iterations};
purgeWrite 0;
writeFormat ascii;
writePrecision 8;
writeCompression off;
timeFormat general;
timePrecision 6;
runTimeModifiable yes;
''')
# Keep official local-Euler/PIMPLE scheme, but cap local Courant number more conservatively.
fvs=case/'system'/'fvSolution'
s=fvs.read_text().replace('maxCo               10;', 'maxCo               4;').replace('maxAlphaCo          1;', 'maxAlphaCo          0.5;')
fvs.write_text(s)
print(f'configured NX-290W free-surface case: U={U:.9f} m/s, iterations={iterations}')
