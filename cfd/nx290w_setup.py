#!/usr/bin/env python3
from pathlib import Path
import math, sys
case=Path(sys.argv[1]); U=float(sys.argv[2]) if len(sys.argv)>2 else 5.635451667; SCALE=30.0
geom=[('center',296.364,19.2111,8.25033,0.0),('starboard',274.673,10.4012,5.22519,19.7994),('port',274.673,10.4012,5.22519,-19.7994)]
def hb(x,z,L,B,T):
 xi=2*x/L-1; eta=abs(z)/T; return .5*B*max(0,1-xi*xi)*max(0,1-eta*eta)
def norm(a,b,c):
 ux,uy,uz=(b[i]-a[i] for i in range(3)); vx,vy,vz=(c[i]-a[i] for i in range(3)); n=(uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx); m=math.sqrt(sum(q*q for q in n)) or 1; return tuple(q/m for q in n)
def tri(f,a,b,c):
 n=norm(a,b,c); f.write(f'  facet normal {n[0]:.8e} {n[1]:.8e} {n[2]:.8e}\n    outer loop\n'); [f.write(f'      vertex {p[0]:.8e} {p[1]:.8e} {p[2]:.8e}\n') for p in (a,b,c)]; f.write('    endloop\n  endfacet\n')
def stl(path,nx=121,nz=41):
 with open(path,'w') as f:
  f.write('solid motorBike\n')
  for _,Lf,Bf,Tf,y0f in geom:
   L,B,T,yc=Lf/SCALE,Bf/SCALE,Tf/SCALE,y0f/SCALE; xs=[L*i/(nx-1) for i in range(nx)]; zs=[-T+2*T*k/(nz-1) for k in range(nz)]
   for side in (-1,1):
    for i in range(nx-1):
     for k in range(nz-1):
      pts=[]
      for ii,kk in ((i,k),(i+1,k),(i+1,k+1),(i,k+1)):
       x,z=xs[ii],zs[kk]; pts.append((x,yc+side*hb(x*SCALE,z*SCALE,Lf,Bf,Tf)/SCALE,z))
      a,b,c,d=pts; ts=((a,c,b),(a,d,c)) if side<0 else ((a,b,c),(a,c,d))
      for t in ts:
       A,Bp,C=t; cr=((Bp[1]-A[1])*(C[2]-A[2])-(Bp[2]-A[2])*(C[1]-A[1]),(Bp[2]-A[2])*(C[0]-A[0])-(Bp[0]-A[0])*(C[2]-A[2]),(Bp[0]-A[0])*(C[1]-A[1])-(Bp[1]-A[1])*(C[0]-A[0]));
       if math.sqrt(sum(q*q for q in cr))>1e-12: tri(f,*t)
  f.write('endsolid motorBike\n')
gd=case/'constant'/'geometry'; gd.mkdir(parents=True,exist_ok=True)
for p in gd.iterdir():
 if p.is_file(): p.unlink()
stl(gd/'motorBike.stl')
(case/'constant'/'physicalProperties').write_text('FoamFile { format ascii; class dictionary; location "constant"; object physicalProperties; }\nviscosityModel constant;\nnu 1.0e-06;\n')
(case/'system'/'blockMeshDict').write_text('''FoamFile { format ascii; class dictionary; object blockMeshDict; }
convertToMeters 1;
vertices ((-5 -3 -1.5)(20 -3 -1.5)(20 3 -1.5)(-5 3 -1.5)(-5 -3 1.5)(20 -3 1.5)(20 3 1.5)(-5 3 1.5));
blocks (hex (0 1 2 3 4 5 6 7) (50 18 10) simpleGrading (1 1 1));
edges ();
boundary (inlet{type patch;faces((0 4 7 3));} outlet{type patch;faces((1 2 6 5));} lowerWall{type patch;faces((0 3 2 1));} upperWall{type symmetryPlane;faces((4 5 6 7));} front{type symmetryPlane;faces((0 1 5 4));} back{type symmetryPlane;faces((3 7 6 2));});
mergePatchPairs ();
''')
(case/'system'/'snappyHexMeshDict').write_text('''FoamFile { format ascii; class dictionary; object snappyHexMeshDict; }
castellatedMesh true; snap true; addLayers true;
geometry { motorBike { type triSurface; file "motorBike.stl"; } nearHull { type box; min (-0.5 -1.1 -0.5); max (10.5 1.1 0.5); } wakeBox { type box; min (7 -1.4 -0.65); max (18 1.4 0.65); } }
castellatedMeshControls { maxLocalCells 1000000; maxGlobalCells 1800000; minRefinementCells 0; nCellsBetweenLevels 2; features (); refinementSurfaces { motorBike { level (2 3); patchInfo { type wall; } } } resolveFeatureAngle 45; refinementRegions { nearHull { mode inside; level 2; } wakeBox { mode inside; level 2; } } insidePoint (-3.25 2.15 0.85); allowFreeStandingZoneFaces false; }
snapControls { nSmoothPatch 3; tolerance 2; nSolveIter 30; nRelaxIter 5; }
addLayersControls { relativeSizes false; layers { "motorBike.*" { nSurfaceLayers 5; } } expansionRatio 1.25; firstLayerThickness 0.0005; minThickness 0.00015; nGrow 0; featureAngle 80; slipFeatureAngle 30; nRelaxIter 5; nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10; maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.3; minMedianAxisAngle 90; nBufferCellsNoExtrude 0; nLayerIter 50; }
meshQualityControls { maxNonOrtho 70; maxBoundarySkewness 20; maxInternalSkewness 4; maxConcave 80; minVol 1e-13; minTetQuality 1e-15; minArea -1; minTwist 0.02; minDeterminant 0.001; minFaceWeight 0.02; minVolRatio 0.01; minTriangleTwist -1; nSmoothScale 4; errorReduction 0.75; }
writeFlags (scalarLevels layerSets layerFields); mergeTolerance 1e-6;
''')
for fn in ['U','p','nuTilda','nut','k']:
 p=case/'0'/fn
 if p.exists():
  s=p.read_text().replace('motorBike_.*','motorBike.*')
  if fn=='U': s=s.replace('(20 0 0)',f'({U:.9f} 0 0)')
  p.write_text(s)
(case/'system'/'controlDict').write_text(f'''FoamFile {{ format ascii; class dictionary; location "system"; object controlDict; }}
solver incompressibleFluid; startFrom startTime; startTime 0; stopAt endTime; endTime 250; deltaT 1; writeControl timeStep; writeInterval 250; purgeWrite 0; writeFormat ascii; writePrecision 8; writeCompression off; timeFormat general; timePrecision 6; runTimeModifiable true;
functions {{ forceCoeffs {{ type forceCoeffs; libs ("libforces.so"); writeControl timeStep; writeInterval 1; log true; patches ("motorBike.*"); rho rhoInf; rhoInf 1025; liftDir (0 0 1); dragDir (1 0 0); CofR (4.9 0 0); pitchAxis (0 1 0); magUInf {U:.9f}; lRef 1; Aref 1; }} }}
''')
print('configured',U)
