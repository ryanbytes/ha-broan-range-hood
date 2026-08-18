#!/usr/bin/env python3
import sys, pathlib, re, math, json, statistics

case = pathlib.Path(sys.argv[1])
full_kn = float(sys.argv[2])
meta = json.loads((pathlib.Path(__file__).with_name('geometry_metadata.json')).read_text())
force_files = sorted(p for p in case.glob('postProcessing/forces/**/*') if p.is_file() and 'force' in p.name.lower())
if not force_files:
    raise SystemExit('No forces output found under postProcessing/forces')

# OpenFOAM forces.dat: time ((pressure force) (viscous force)) ((pressure moment) (viscous moment))
# Parse the force vectors explicitly so moments can never be mistaken for force.
num = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
force_re = re.compile(
    rf'^\s*({num})\s+\(\(\s*({num})\s+({num})\s+({num})\s*\)\s*'
    rf'\(\s*({num})\s+({num})\s+({num})\s*\)\)'
)
rows = []
for fp in force_files:
    for line in fp.read_text(errors='ignore').splitlines():
        m = force_re.match(line)
        if not m:
            continue
        t, px, py, pz, vx, vy, vz = map(float, m.groups())
        pressure_drag = -px
        viscous_drag = -vx
        rows.append((t, pressure_drag, viscous_drag, pressure_drag + viscous_drag))
if len(rows) < 10:
    raise SystemExit(f'Could not parse enough force records ({len(rows)})')

# Remove duplicate time records while retaining the latest occurrence.
by_time = {r[0]: r for r in rows}
rows = [by_time[t] for t in sorted(by_time)]
tail = rows[int(len(rows) * 0.8):]

def mean_col(data, i):
    return statistics.mean(r[i] for r in data)

def sd_col(data, i):
    return statistics.pstdev(r[i] for r in data)

def slope(data, i):
    xs = [r[0] for r in data]
    ys = [r[i] for r in data]
    xm, ym = statistics.mean(xs), statistics.mean(ys)
    den = sum((x-xm)**2 for x in xs)
    return 0.0 if den == 0 else sum((x-xm)*(y-ym) for x,y in zip(xs,ys)) / den

p_mean = mean_col(tail, 1)
v_mean = mean_col(tail, 2)
drag_model = mean_col(tail, 3)
drag_sd = sd_col(tail, 3)
conv = rows[-min(50, len(rows)):]
sp, sv, st = slope(conv, 1), slope(conv, 2), slope(conv, 3)

def pct100(s, base):
    return 0.0 if base == 0 else s * 100.0 / base * 100.0

lam = 50.0
rho_m, nu_m = 998.8, 1.09e-6
rho_s, nu_s = 1025.0, 1.19e-6
Lm, Ls = 6.0, 300.0
Vm = full_kn * 0.514444 / math.sqrt(lam)
Vs = full_kn * 0.514444
Sm = meta['wetted_area_model_m2']
Ss = meta['wetted_area_full_m2']
CTm = drag_model / (0.5 * rho_m * Vm**2 * Sm)
Rem = Vm * Lm / nu_m
Res = Vs * Ls / nu_s

def cf(Re):
    return 0.075 / (math.log10(Re) - 2.0)**2

CFm, CFs = cf(Rem), cf(Res)
CR = CTm - CFm

print(f'Force records: {len(rows)}; last time/iteration: {rows[-1][0]:.0f}')
print(f'Model total drag mean (last 20%): {drag_model:.3f} N; sigma {drag_sd:.3f} N')
print(f'  pressure contribution: {p_mean:.3f} N')
print(f'  viscous contribution : {v_mean:.3f} N')
print(f'Last-{len(conv)} slope, total: {st:+.5f} N/iter ({pct100(st, mean_col(conv,3)):+.2f}% per 100 iters)')
print(f'Last-{len(conv)} slope, pressure: {sp:+.5f} N/iter ({pct100(sp, mean_col(conv,1)):+.2f}% per 100 iters)')
print(f'Last-{len(conv)} slope, viscous: {sv:+.5f} N/iter ({pct100(sv, mean_col(conv,2)):+.2f}% per 100 iters)')
print(f'Model CT: {CTm:.6f}')
print(f'Model Re: {Rem:.3e}; full-scale Re: {Res:.3e}')
print(f'ITTC-1957 CF model/full: {CFm:.6f} / {CFs:.6f}')
print(f'Classical residual estimate CR=CTm-CFm: {CR:.6f}')

if CR >= 0:
    CTs = CR + CFs
    Rt = 0.5 * rho_s * Vs**2 * Ss * CTs
    print(f'Preliminary ITTC-style full-scale resistance: {Rt/1e6:.3f} MN')
    print(f'Preliminary effective power: {Rt*Vs/1e6:.1f} MW')
else:
    print('ITTC total-resistance extrapolation REJECTED: CR < 0. The no-layer coarse mesh under-resolves model-scale friction.')

# For a no-layer validation mesh only: scale the CFD pressure resistance by Froude force scaling
# and add an ITTC full-scale flat-plate friction estimate. This is a screening number, not a final extrapolation.
Rp_screen = p_mean * (rho_s / rho_m) * lam**3
Rf_screen = 0.5 * rho_s * Vs**2 * Ss * CFs
Rt_screen = Rp_screen + Rf_screen
print(f'Pressure/Froude + ITTC-friction SCREEN only: pressure {Rp_screen/1e6:.3f} MN + friction {Rf_screen/1e6:.3f} MN = {Rt_screen/1e6:.3f} MN')
print(f'Corresponding SCREEN effective power: {Rt_screen*Vs/1e6:.1f} MW')
if abs(pct100(st, mean_col(conv,3))) > 1.0:
    print('CONVERGENCE WARNING: total drag is still trending by more than 1% per 100 iterations.')
print('WARNING: validation mesh; boundary layers and mesh/time convergence are required before design use.')
