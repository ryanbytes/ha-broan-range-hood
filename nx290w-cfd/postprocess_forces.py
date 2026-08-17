#!/usr/bin/env python3
import sys,pathlib,re,math,json,statistics
case=pathlib.Path(sys.argv[1]); full_kn=float(sys.argv[2])
meta=json.loads((pathlib.Path(__file__).with_name('geometry_metadata.json')).read_text())
files=list(case.glob('postProcessing/forces/**/*'))
force_files=[p for p in files if p.is_file() and ('force' in p.name.lower())]
if not force_files: raise SystemExit('No forces output found under postProcessing/forces')
def nums(line):
    return [float(x) for x in re.findall(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?',line)]
rows=[]
for fp in sorted(force_files):
    for line in fp.read_text(errors='ignore').splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        a=nums(line)
        if len(a)>=10: rows.append((a[0],a[1]+a[4]+a[7]))
if len(rows)<10: raise SystemExit(f'Could not parse enough force records ({len(rows)})')
rows=sorted(set(rows)); tail=rows[int(len(rows)*0.8):]
drag_model=abs(statistics.mean(x[1] for x in tail)); drag_sd=statistics.pstdev(x[1] for x in tail)
lam=50.; rho_m=998.8; nu_m=1.09e-6; rho_s=1025.; nu_s=1.19e-6; Lm=6.; Ls=300.
Vm=full_kn*0.514444/math.sqrt(lam); Vs=full_kn*0.514444; Sm=meta['wetted_area_model_m2']; Ss=meta['wetted_area_full_m2']
CTm=drag_model/(0.5*rho_m*Vm**2*Sm); Rem=Vm*Lm/nu_m; Res=Vs*Ls/nu_s
def cf(Re): return 0.075/(math.log10(Re)-2.0)**2
CFm=cf(Rem); CFs=cf(Res); CR=CTm-CFm; CTs=CR+CFs
Rt=0.5*rho_s*Vs**2*Ss*CTs; Pe=Rt*Vs/1e6
print(f'Model drag mean (last 20%): {drag_model:.3f} N')
print(f'Model drag sigma: {drag_sd:.3f} N')
print(f'Model CT: {CTm:.6f}')
print(f'Model Re: {Rem:.3e}; full-scale Re: {Res:.3e}')
print(f'ITTC-1957 CF model/full: {CFm:.6f} / {CFs:.6f}')
print(f'Residual coefficient estimate CR=CTm-CFm: {CR:.6f}')
print(f'Preliminary full-scale resistance: {Rt/1e6:.3f} MN')
print(f'Preliminary effective power: {Pe:.1f} MW')
print('WARNING: coarse first-pass result; mesh/time convergence required before design use.')
