#!/usr/bin/env python3
import math
from pathlib import Path

WATERLINE = 0.244
HULLS = [
    dict(name="center", L=6.0, B=0.48, T=0.16, deck=0.10, x0=-3.0, y0=0.0),
    dict(name="port", L=5.0, B=0.20, T=0.09, deck=0.06, x0=-2.0, y0=-0.50),
    dict(name="starboard", L=5.0, B=0.20, T=0.09, deck=0.06, x0=-2.0, y0=0.50),
]
NX = 81
NTH = 36

def longitudinal_factor(x, L):
    s=max(0.0,min(1.0,x/L))
    bow=math.sin(math.pi/2*min(s/0.40,1.0))**1.45
    stern=1.0
    if s>0.70:
        q=(s-0.70)/0.30
        stern=1.0-0.28*q*q
    return max(0.015,bow*stern)

def normal(a,b,c):
    ux,uy,uz=b[0]-a[0],b[1]-a[1],b[2]-a[2]
    vx,vy,vz=c[0]-a[0],c[1]-a[1],c[2]-a[2]
    nx=uy*vz-uz*vy; ny=uz*vx-ux*vz; nz=ux*vy-uy*vx
    m=math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
    return nx/m,ny/m,nz/m

def facet(f,a,b,c):
    n=normal(a,b,c)
    f.write(f"  facet normal {n[0]:.8e} {n[1]:.8e} {n[2]:.8e}\n")
    f.write("    outer loop\n")
    for p in (a,b,c):
        f.write(f"      vertex {p[0]:.8e} {p[1]:.8e} {p[2]:.8e}\n")
    f.write("    endloop\n  endfacet\n")

def hull_vertices(h):
    xs=[h["L"]*i/(NX-1) for i in range(NX)]
    th=[2*math.pi*j/NTH for j in range(NTH)]
    H=(h["T"]+h["deck"])/2
    zc=WATERLINE+(h["deck"]-h["T"])/2
    v=[]
    for x in xs:
        fx=longitudinal_factor(x,h["L"])
        ring=[]
        for t in th:
            c=math.cos(t)
            y=(h["B"]/2)*fx*(1 if c>=0 else -1)*(abs(c)**0.72)
            z=zc+H*math.sin(t)
            ring.append((x+h["x0"],y+h["y0"],z))
        v.append(ring)
    return v,zc

out=Path(__file__).resolve().parent/"DTC-scaled.stl"
with out.open("w") as f:
    f.write("solid NX290W_1to50\n")
    for h in HULLS:
        v,zc=hull_vertices(h)
        for i in range(NX-1):
            for j in range(NTH):
                j2=(j+1)%NTH
                a,b,c,d=v[i][j],v[i][j2],v[i+1][j2],v[i+1][j]
                facet(f,a,b,c); facet(f,a,c,d)
        bow=(h["x0"],h["y0"],zc)
        stern=(h["x0"]+h["L"],h["y0"],zc)
        for j in range(NTH):
            j2=(j+1)%NTH
            facet(f,bow,v[0][j2],v[0][j])
            facet(f,stern,v[-1][j],v[-1][j2])
    f.write("endsolid NX290W_1to50\n")
print(out)
