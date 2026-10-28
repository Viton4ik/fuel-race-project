"""Build the monthly USD-per-litre dataset (Jan 1999 - Oct 2026) for every country in the video.

Inputs:  data/raw/*.txt  (official sources, see data/SOURCES.md)
Output:  data/prices_usd_monthly.csv  (columns: month, code, gasoline, diesel)
         data/series_notes.json        (how each country's series was built)

Run:  python3 scripts/build_data.py
"""
import json
import math
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

START_Y, START_M = 1999, 1
END_Y, END_M = 2026, 10
N = (END_Y - START_Y) * 12 + (END_M - START_M) + 1  # 334 months


def midx(y, m):
    return (y - START_Y) * 12 + (m - START_M)


def label(i):
    y, m = divmod(i, 12)
    return f"{START_Y + y}-{m + 1:02d}"


def parse_ym(s):
    s = s.replace("M", "-")
    y, m = s.split("-")[:2]
    return int(y), int(m)


# ---------------------------------------------------------------- FX (Eurostat ert_bil_eur_m)
def load_eurostat():
    hicp, fx = {}, {}
    for line in (RAW / "eurostat_hicp_fuels_and_fx.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        kind, key, rest = line.split(" ", 2)
        start, vals = rest.split(":", 1)
        y, m = parse_ym(start)
        arr = [float(v) for v in vals.split(",")]
        series = {midx(y, m) + k: v for k, v in enumerate(arr)}
        (hicp if kind == "HICP" else fx)[key] = series
    return hicp, fx


HICP, FX = load_eurostat()


def fx_series(cur_per_eur):
    """Return array: local currency units per USD, monthly (held flat after last obs)."""
    usd = FX["USD"]
    out = np.full(N, np.nan)
    last = None
    for i in range(N):
        if i in cur_per_eur and i in usd:
            last = cur_per_eur[i] / usd[i]
        out[i] = last if last is not None else np.nan
    # back-fill start if needed
    first = next(v for v in out if not np.isnan(v))
    out[np.isnan(out)] = first
    return out


USD_PER_EUR = np.array([FX["USD"].get(i, np.nan) for i in range(N)])
for i in range(N):
    if np.isnan(USD_PER_EUR[i]):
        USD_PER_EUR[i] = USD_PER_EUR[i - 1]

# ---------------------------------------------------------------- World Bank / GIZ biennial points
ISO3 = {"AUT": "AT", "BEL": "BE", "BGR": "BG", "CYP": "CY", "CZE": "CZ", "DEU": "DE", "DNK": "DK", "EST": "EE",
        "ESP": "ES", "FIN": "FI", "FRA": "FR", "GRC": "GR", "HRV": "HR", "HUN": "HU", "IRL": "IE", "ITA": "IT",
        "LTU": "LT", "LUX": "LU", "LVA": "LV", "MLT": "MT", "NLD": "NL", "POL": "PL", "PRT": "PT", "ROU": "RO",
        "SWE": "SE", "SVN": "SI", "SVK": "SK", "GBR": "UK", "NOR": "NO", "CHE": "CH", "ISL": "IS", "TUR": "TR",
        "SRB": "RS", "RUS": "RU", "CHN": "CN"}
WB = {}
for line in (RAW / "worldbank_wdi_archive_pump_prices_usd_per_l.txt").read_text().splitlines():
    if not line or line.startswith("#"):
        continue
    parts = line.split()
    code = ISO3.get(parts[0])
    if not code:
        continue
    g = parts[parts.index("G") + 1] if "G" in parts else ""
    d = parts[parts.index("D") + 1] if "D" in parts else ""
    pts = lambda s: {midx(int(y), 11): float(v) for y, v in (p.split(":") for p in s.split(",") if p) if int(y) >= 1998}
    WB[code] = {"g": pts(g), "d": pts(d)}

# ---------------------------------------------------------------- EU Weekly Oil Bulletin (EUR / 1000 l)
WOB = {}
for line in (RAW / "eu_wob_monthly_eur_per_1000l.txt").read_text().splitlines():
    key, rest = line.split(" ")
    code, fuel = key[:2], ("g" if key.endswith("euro95") else "d")
    start, vals = rest.split(":")
    y, m = int(start[:4]), int(start[4:])
    base = midx(y, m)
    ser = {}
    for k, v in enumerate(vals.split(",")):
        if v.strip():
            ser[base + k] = float(v) / 1000.0 * USD_PER_EUR[base + k]
    WOB.setdefault(code, {})[fuel] = ser

EU27 = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU",
        "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"]


def fill(points, end_hold=True):
    """PCHIP through sparse/monthly points -> full monthly array."""
    ks = sorted(points)
    xs = np.array(ks, dtype=float)
    ys = np.array([points[k] for k in ks], dtype=float)
    f = PchipInterpolator(xs, ys, extrapolate=False)
    out = f(np.arange(N, dtype=float))
    # hold ends
    first_i, last_i = int(math.ceil(xs[0])), int(math.floor(xs[-1]))
    out[:max(first_i, 0)] = ys[0]
    if end_hold:
        out[last_i + 1:] = ys[-1]
    return out


def merge(*dicts):
    d = {}
    for x in dicts:
        d.update(x)
    return d


def wb_before(code, fuel, before_idx):
    return {k: v for k, v in WB[code][fuel].items() if k < before_idx}


SERIES, NOTES = {}, {}

# ---- EU27
for c in EU27:
    for f in ("g", "d"):
        mon = WOB[c][f]
        first = min(mon)
        pts = merge(wb_before(c, f, first - 3), mon)
        SERIES.setdefault(c, {})[f] = fill(pts)
    NOTES[c] = f"EC Weekly Oil Bulletin monthly avg from {label(min(WOB[c]['g']))}; earlier: World Bank/GIZ (Nov, biennial) interpolated"

# ---- UK: WOB 2005-2020, DESNZ 2018+ (DESNZ preferred from 2021)
uk_lines = (RAW / "uk_desnz_weekly_road_fuel_monthly_pence_per_l.txt").read_text().splitlines()
uk = {l.split()[0]: [float(v) for v in l.split()[1].split(",")] for l in uk_lines if l.startswith("UK_")}
gbp = fx_series(FX["GBP"])
for f, key in (("g", "UK_G"), ("d", "UK_D")):
    desnz = {midx(2018, 1) + k: v / 100.0 / gbp[midx(2018, 1) + k] for k, v in enumerate(uk[key])}
    wob = {k: v for k, v in WOB["UK"][f].items() if k < midx(2021, 1)}
    pts = merge(wb_before("UK", f, midx(2005, 1) - 3), wob, {k: v for k, v in desnz.items() if k >= midx(2021, 1)})
    SERIES.setdefault("UK", {})[f] = fill(pts)
NOTES["UK"] = "EC Weekly Oil Bulletin 2005-2020; DESNZ weekly road fuel prices 2021-2026; earlier World Bank/GIZ"

# ---- Norway: SSB 09654 monthly NOK
nok = fx_series(FX["NOK"])
no_lines = (RAW / "norway_ssb_09654_nok_per_l.txt").read_text().splitlines()
no = {l.split()[0]: [float(v) for v in l.split()[1].split(",")] for l in no_lines if l.startswith("NO_")}
for f, key in (("g", "NO_G"), ("d", "NO_D")):
    SERIES.setdefault("NO", {})[f] = fill({k: v / nok[k] for k, v in enumerate(no[key])})
NOTES["NO"] = "Statistics Norway table 09654, monthly, NOK converted at Eurostat monthly FX"

# ---- CH, IS, TR, RS: World Bank/GIZ level to Nov 2016, then chained with Eurostat HICP petrol/diesel sub-indices
for c, cur in (("CH", "CHF"), ("IS", "ISK"), ("TR", "TRY"), ("RS", "RSD")):
    lc = fx_series(FX[cur])
    for f, coicop in (("g", "CP07222"), ("d", "CP07221")):
        idx = HICP[f"{coicop}|{c}"]
        anchor = midx(2016, 11)
        base = anchor if anchor in idx else min(idx)  # TR index starts Dec 2016
        level_lc = WB[c][f][anchor] * lc[anchor]
        chained = {k: level_lc * v / idx[base] / lc[k] for k, v in idx.items() if k >= base}
        pts = merge({k: v for k, v in WB[c][f].items() if k < base}, chained)
        if c == "CH":  # official BAZG pump prices take over from Jan 2025
            line = next(l for l in (RAW / "other_sources_ch_cn_rub.txt").read_text().splitlines()
                        if l.startswith("CH_BAZG_" + f.upper()))
            vals = [float(v) for v in line.split()[1].split(",")]
            pts = {k: v for k, v in pts.items() if k < midx(2025, 1)}
            pts.update({midx(2025, 1) + k: v / 100.0 / lc[midx(2025, 1) + k] for k, v in enumerate(vals)})
        SERIES.setdefault(c, {})[f] = fill(pts)
    NOTES[c] = ("BAZG border-zone pump prices 2025-2026; " if c == "CH" else "") + "World Bank/GIZ to Nov 2016; then Eurostat HICP petrol/diesel index (prc_hicp_minr) applied to that level, Eurostat FX"

# ---- Russia: Rosstat
ru_txt = (RAW / "russia_rosstat_fuel_prices_rub_per_l.txt").read_text().splitlines()
ru = {l.split()[0]: l.split()[1] for l in ru_txt if l and not l.startswith("#")}
rub = fx_series(FX["RUB"])
for kv in ru_txt:
    pass
rub_extra = {}
for line in (RAW / "other_sources_ch_cn_rub.txt").read_text().splitlines():
    if line.startswith("RUB_USD"):
        for p in line.split()[1].split(","):
            ym, v = p.split(":")
            y, m = parse_ym(ym)
            rub_extra[midx(y, m)] = float(v)
for k, v in rub_extra.items():
    rub[k] = v
ann95 = {int(y): float(v) for y, v in (p.split(":") for p in ru["ANNUAL_AI95"].split(","))}
ann92 = {int(y): float(v) for y, v in (p.split(":") for p in ru["ANNUAL_AI92"].split(","))}
ratio = ann95[2001] / ann92[2001]
for y in (1999, 2000):
    ann95[y] = ann92[y] * ratio
weekly = {"g": {}, "d": {}}
for yr in range(2022, 2027):
    dates = ru[f"W{yr}_DATES"].split(",")
    for f, key in (("g", f"W{yr}_AI95"), ("d", f"W{yr}_DIES")):
        vals = [float(v) for v in ru[key].split(",")]
        acc = {}
        for dt, v in zip(dates, vals):
            mth = int(dt.split(".")[1])
            acc.setdefault(midx(yr, mth), []).append(v)
        for k, vs in acc.items():
            weekly[f][k] = sum(vs) / len(vs)
g_pts = {midx(y, 12): v / rub[midx(y, 12)] for y, v in ann95.items() if y < 2022}
g_pts.update({k: v / rub[k] for k, v in weekly["g"].items()})
ru_g = fill(g_pts)
# diesel = gasoline x ratio; ratio from World Bank (to 2016) and Rosstat weekly (2022+), interpolated between
r_pts = {k: WB["RU"]["d"][k] / WB["RU"]["g"][k] for k in WB["RU"]["d"]}
r_pts.update({k: weekly["d"][k] / weekly["g"][k] for k in weekly["d"]})
ru_r = fill(r_pts)
SERIES["RU"] = {"g": ru_g, "d": ru_g * ru_r}
NOTES["RU"] = ("Rosstat average consumer prices: AI-95 end-of-year 2001-2021, weekly AI-95 & diesel 2022-2026; "
               "diesel before 2022 from World Bank/GIZ diesel/gasoline ratio; FX Eurostat, OECD/FRED, Bank of Russia")

# ---- China
cny = fx_series(FX["CNY"])
cn_txt = (RAW / "other_sources_ch_cn_rub.txt").read_text().splitlines()
adj = next(l for l in cn_txt if l.startswith("CN_ADJ")).split()[1].split(",")
ann = {int(y): float(v) for y, v in (p.split(":") for p in next(l for l in cn_txt if l.startswith("CN_G_ANNUAL")).split()[1].split(","))}
# per-tonne path anchored on Shanghai DRC 2026-03-10 level (after the +695/+670 move)
G_T_PER_L, D_T_PER_L = 7.60 / 10059, 7.28 / 8455
steps = []
for p in adj:
    d, ch = p.split(":")
    gch, dch = ch.split("/")
    steps.append((d, int(gch), int(dch)))
idx_anchor = [s[0] for s in steps].index("2026-03-10")
g_t, d_t = 10059.0, 8455.0
levels = {}
# walk backwards to get level before first step
g0, d0 = g_t, d_t
for d, gc, dc in reversed(steps[:idx_anchor + 1]):
    g0 -= gc
    d0 -= dc
g_cur, d_cur = g0, d0
daily = []
for d, gc, dc in steps:
    g_cur += gc
    d_cur += dc
    daily.append((d, g_cur, d_cur))
# monthly average by step function (value at mid-month)
import datetime as _dt
def level_at(date, start_g, start_d):
    g, d_ = start_g, start_d
    for ds, gg, dd in daily:
        if _dt.date.fromisoformat(ds) <= date:
            g, d_ = gg, dd
    return g, d_
cn_g, cn_d = {}, {}
for y in range(2024, 2027):
    for m in range(1, 13):
        i = midx(y, m)
        if i < midx(2024, 5) or i >= N:
            continue
        gt, dt = level_at(_dt.date(y, m, 15), g0, d0)
        cn_g[i] = gt * G_T_PER_L / cny[i]
        cn_d[i] = dt * D_T_PER_L / cny[i]
cn_g[midx(2024, 4)] = g0 * G_T_PER_L / cny[midx(2024, 4)]
cn_d[midx(2024, 4)] = d0 * D_T_PER_L / cny[midx(2024, 4)]
g_pts = dict(WB["CN"]["g"])
g_pts.update({midx(y, 6): v / cny[midx(y, 6)] for y, v in ann.items()})
g_pts.update(cn_g)
cn_gs = fill(g_pts)
r_pts = {k: WB["CN"]["d"][k] / WB["CN"]["g"][k] for k in WB["CN"]["d"]}
r_pts.update({k: cn_d[k] / cn_g[k] for k in cn_d})
cn_rs = fill(r_pts)
SERIES["CN"] = {"g": cn_gs, "d": cn_gs * cn_rs}
NOTES["CN"] = ("World Bank/GIZ to 2016; 92# annual levels 2017-2023; 2024-2026 NDRC price-cap adjustments chained from "
               "Shanghai DRC notice (Mar 2026); diesel via diesel/gasoline ratio")

# ---------------------------------------------------------------- reshape World-Bank-only spans after 2005
# World Bank/GIZ points are a single mid-November snapshot every two years, so straight interpolation would
# miss the 2008 spike etc. For spans after 2005 where a country has only those snapshots, we interpolate the
# country's price RELATIVE to the EU average (EC Weekly Oil Bulletin) and multiply back by the EU monthly
# average. The official snapshot values are kept exactly at their dates.
_core = [c for c in EU27 if min(WOB[c]["g"]) == midx(2005, 1)]  # countries reporting since 2005
EU_AVG = {f: np.mean([SERIES[c][f] for c in _core], axis=0) for f in ("g", "d")}
GAPS = {"CH": None, "IS": None, "TR": None, "RS": None, "HR": midx(2013, 7), "BG": midx(2008, 1), "RO": midx(2008, 1)}
E05 = midx(2005, 1)
for c, gap_end in GAPS.items():
    for f in ("g", "d"):
        s = SERIES[c][f]
        if gap_end is None:  # chained series start
            coicop = "CP07222" if f == "g" else "CP07221"
            idx = HICP[f"{coicop}|{c}"]
            gap_end = midx(2016, 11) if midx(2016, 11) in idx else min(idx)
        ratio_pts = {k: v / EU_AVG[f][k] for k, v in WB[c][f].items() if E05 - 6 <= k < gap_end}
        ratio_pts[gap_end] = s[gap_end] / EU_AVG[f][gap_end]
        ratio_pts[midx(2004, 11)] = WB[c][f][midx(2004, 11)] / EU_AVG[f][E05]
        r = fill(ratio_pts)
        for i in range(E05, gap_end):
            s[i] = r[i] * EU_AVG[f][i]
        # blend the 2004-11 -> 2005-01 seam
        SERIES[c][f] = s
    NOTES[c] += "; 2005 onward gaps between World Bank snapshots shaped by EU-average monthly path"

# ---------------------------------------------------------------- write
out = ["month,code,gasoline,diesel"]
for i in range(N):
    for c, s in SERIES.items():
        out.append(f"{label(i)},{c},{s['g'][i]:.4f},{s['d'][i]:.4f}")
(ROOT / "data" / "prices_usd_monthly.csv").write_text("\n".join(out) + "\n")
(ROOT / "data" / "series_notes.json").write_text(json.dumps(NOTES, indent=2))
print("countries", len(SERIES), "months", N)
