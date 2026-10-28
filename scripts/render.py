"""Render the 9:16 bar-chart-race video (1080x1920, 60 fps) with skia and pipe frames to ffmpeg.

Run:   python3 scripts/render.py                -> build/race_silent.mp4
       python3 scripts/render.py --preview 600  -> renders a few still frames into build/frames/
"""
import argparse
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import skia
from scipy.interpolate import PchipInterpolator

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
BUILD.mkdir(exist_ok=True)

W, H, FPS = 1080, 1920, 60

# ------------------------------------------------------------------ timeline (seconds)
T_INTRO = 2.0          # title in, bars grow
T_RACE = 67.0          # Jan 1999 -> Oct 2026 (~2.4 s per year)
T_HOLD = 1.6           # final standings
T_OUTRO = 4.4          # sources card
TOTAL = T_INTRO + T_RACE + T_HOLD + T_OUTRO

TOP_N = 7
PINNED = ["RS", "RU", "CN"]

NAMES = {"AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
         "DK": "Denmark", "EE": "Estonia", "ES": "Spain", "FI": "Finland", "FR": "France", "GR": "Greece",
         "HR": "Croatia", "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LT": "Lithuania", "LU": "Luxembourg",
         "LV": "Latvia", "MT": "Malta", "NL": "Netherlands", "PL": "Poland", "PT": "Portugal", "RO": "Romania",
         "SE": "Sweden", "SI": "Slovenia", "SK": "Slovakia", "UK": "United Kingdom", "NO": "Norway",
         "CH": "Switzerland", "IS": "Iceland", "TR": "Türkiye", "RS": "Serbia", "RU": "Russia", "CN": "China"}

EVENTS = [  # (start month label, text)
    ("2008-04", "2008 · Oil hits a record $147 a barrel"),
    ("2008-11", "Global financial crisis: oil crashes"),
    ("2014-10", "2014 · Shale boom: oil price collapse"),
    ("2020-03", "2020 · COVID-19 lockdowns"),
    ("2022-03", "2022 · Russia invades Ukraine: energy crisis"),
    ("2026-03", "2026 · War in Iran: new oil shock"),
]
EVENT_DUR = 2.8  # seconds on screen

SOURCES = [
    "European Commission · Weekly Oil Bulletin (EU-27, UK to 2020)",
    "UK DESNZ · Weekly road fuel prices (2021–2026)",
    "Statistics Norway · table 09654",
    "Eurostat · HICP fuel indices & exchange rates",
    "Swiss BAZG · border-zone pump prices (2025–26)",
    "Rosstat · average consumer prices · Bank of Russia FX",
    "China NDRC price caps · Shanghai DRC notice",
    "World Bank WDI / GIZ · pump prices 1998–2016",
]

# ------------------------------------------------------------------ colours
C_BG_TOP = skia.Color(24, 27, 34)
C_BG_BOT = skia.Color(10, 11, 15)
C_TEXT = skia.Color(240, 242, 246)
C_MUTED = skia.Color(150, 157, 170)
C_FAINT = skia.Color(255, 255, 255, 18)
C_GAS = (skia.Color(255, 196, 66), skia.Color(255, 128, 32))     # amber
C_DSL = (skia.Color(64, 232, 212), skia.Color(20, 168, 196))     # teal
C_BAR_HI = skia.Color(246, 247, 250)
C_BAR_LO = skia.Color(196, 201, 210)
C_BAR_EDGE = skia.Color(128, 134, 146)

# ------------------------------------------------------------------ fonts
FD = "/usr/share/fonts/opentype/inter/"
TF = {w: skia.Typeface.MakeFromFile(FD + f) for w, f in
      {"bold": "Inter-Bold.otf", "black": "Inter-Black.otf", "semi": "Inter-SemiBold.otf",
       "med": "Inter-Medium.otf", "reg": "Inter-Regular.otf", "disp": "InterDisplay-Bold.otf"}.items()}


def font(weight, size):
    f = skia.Font(TF[weight], size)
    f.setEdging(skia.Font.Edging.kSubpixelAntiAlias)
    f.setSubpixel(True)
    return f


# ------------------------------------------------------------------ layout
SAFE_L = 56
FLAG_W, FLAG_H = 66, 50
NAME_X = SAFE_L + FLAG_W + 16
BAR_X0 = 346
BAR_MAX_W = 520
ROW_H = 104
BAR_H = 30
BAR_GAP = 9
ROWS_TOP = 486
PIN_SEP_Y = ROWS_TOP + TOP_N * ROW_H + 10
PIN_TOP = PIN_SEP_Y + 34

# ------------------------------------------------------------------ data
df = pd.read_csv(ROOT / "data" / "prices_usd_monthly.csv")
months = sorted(df.month.unique())
NM = len(months)
codes = sorted(df.code.unique())
G = {c: df[df.code == c].sort_values("month").gasoline.to_numpy() for c in codes}
D = {c: df[df.code == c].sort_values("month").diesel.to_numpy() for c in codes}


def smooth(a, w=2):
    """Centred moving average whose window shrinks at both ends, so the first and the last month
    (Jan 1999, Oct 2026) show the exact official values."""
    n = len(a)
    out = np.empty(n)
    for i in range(n):
        k = min(w, i, n - 1 - i)
        out[i] = a[i - k:i + k + 1].mean()
    return out


INTERP_G = {c: PchipInterpolator(np.arange(NM), smooth(G[c], 3)) for c in codes}
INTERP_D = {c: PchipInterpolator(np.arange(NM), smooth(D[c], 3)) for c in codes}
# 7-month centred average for display and ranking: calmer swaps, order always consistent with labels
INTERP_RANK = INTERP_G  # rank on exactly what is displayed, so the order always matches the numbers
RACE = [c for c in codes if c not in PINNED]

FLAGS = {}
for c in codes:
    FLAGS[c] = skia.Image.open(str(ROOT / "assets" / "flags" / f"{c}.png"))


def month_at(t):
    """Fractional month index for global time t."""
    if t <= T_INTRO:
        return 0.0
    if t >= T_INTRO + T_RACE:
        return NM - 1.0
    u = (t - T_INTRO) / T_RACE
    return u * (NM - 1)


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ simulation state (ranks, axis) precomputed
NF = int(round(TOTAL * FPS))


def precompute():
    order = sorted(RACE, key=lambda c: -float(INTERP_G[c](0.0)))
    pos, vel, last_swap = {}, {}, {c: -999 for c in RACE}
    held = {}  # frames a challenger has been ahead by the threshold
    axis = None
    states = []
    for f in range(NF):
        t = f / FPS
        m = month_at(t)
        g = {c: float(INTERP_G[c](m)) for c in codes}
        d = {c: float(INTERP_D[c](m)) for c in codes}
        rk = {c: float(INTERP_RANK[c](m)) for c in codes}
        # sticky sort with hysteresis + cooldown, so near-ties don't make rows flicker back and forth
        changed = True
        while changed:
            changed = False
            for i in range(len(order) - 1):
                a, b = order[i], order[i + 1]
                lead = rk[b] / rk[a]
                key = (a, b)
                held[key] = held.get(key, 0) + 1 if lead > 1.02 else 0
                cool = f - max(last_swap[a], last_swap[b]) > 30
                # swap only on a sustained lead: >2 % held for 1/3 s (cooldown 0.5 s), or immediately above 3 %
                if (held[key] >= 20 and cool) or lead > 1.03:
                    order[i], order[i + 1] = b, a
                    last_swap[a] = last_swap[b] = f
                    held[key] = 0
                    changed = True
        target = {c: i for i, c in enumerate(order)}
        for c in RACE:
            if c not in pos:
                pos[c], vel[c] = float(target[c]), 0.0
            # critically damped spring: eases in and out, settles in ~0.35 s, never overshoots
            k = 0.028
            acc = k * (target[c] - pos[c]) - 2 * math.sqrt(k) * vel[c]
            vel[c] += acc
            pos[c] += vel[c]
        visible = [c for c in RACE if pos[c] < TOP_N + 0.6] + PINNED
        vmax = max(max(g[c], d[c]) for c in visible)
        want = vmax * 1.06
        axis = want if axis is None else axis + (want - axis) * 0.06
        states.append((m, g, d, dict(pos), axis, dict(vel)))
    return states


# ------------------------------------------------------------------ drawing helpers
def paint(color=None, aa=True, style=None, **kw):
    p = skia.Paint(AntiAlias=aa)
    if color is not None:
        p.setColor(color)
    if style == "stroke":
        p.setStyle(skia.Paint.kStroke_Style)
    for k, v in kw.items():
        getattr(p, "set" + k)(v)
    return p


def text(canvas, s, x, y, fnt, color, align="left", alpha=1.0):
    blob = skia.TextBlob.MakeFromString(s, fnt)
    w = fnt.measureText(s)
    if align == "right":
        x -= w
    elif align == "center":
        x -= w / 2
    p = paint(color)
    p.setAlphaf(p.getAlphaf() * alpha)
    canvas.drawTextBlob(blob, x, y, p)
    return w


def draw_background(canvas, t):
    shader = skia.GradientShader.MakeLinear([(0, 0), (0, H)], [C_BG_TOP, C_BG_BOT])
    canvas.drawRect(skia.Rect(0, 0, W, H), paint(Shader=shader))
    # slow drifting colour glows (amber / teal) for life
    for cx, cy, r, col, ph in ((180, 520, 620, skia.Color(255, 150, 40, 30), 0.0),
                               (900, 1300, 700, skia.Color(30, 200, 190, 26), 1.7)):
        dx = math.sin(t * 0.25 + ph) * 60
        dy = math.cos(t * 0.21 + ph) * 50
        g = skia.GradientShader.MakeRadial((cx + dx, cy + dy), r, [col, skia.Color(0, 0, 0, 0)])
        canvas.drawRect(skia.Rect(0, 0, W, H), paint(Shader=g))
    # vignette
    v = skia.GradientShader.MakeRadial((W / 2, H * 0.45), H * 0.75,
                                       [skia.Color(0, 0, 0, 0), skia.Color(0, 0, 0, 120)], [0.55, 1.0])
    canvas.drawRect(skia.Rect(0, 0, W, H), paint(Shader=v))


def draw_flag(canvas, c, x, y, alpha):
    r = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, FLAG_W, FLAG_H), 9, 9)
    sh = paint(skia.Color(0, 0, 0, int(140 * alpha)))
    sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 6))
    canvas.drawRRect(r.makeOffset(0, 5), sh)
    canvas.save()
    canvas.clipRRect(r, True)
    p = paint()
    p.setAlphaf(alpha)
    canvas.drawImageRect(FLAGS[c], skia.Rect.MakeXYWH(x, y, FLAG_W, FLAG_H),
                         skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear), p)
    # glossy top highlight
    gl = skia.GradientShader.MakeLinear([(0, y), (0, y + FLAG_H)],
                                        [skia.Color(255, 255, 255, int(70 * alpha)), skia.Color(255, 255, 255, 0)],
                                        [0.0, 0.55])
    canvas.drawRect(skia.Rect.MakeXYWH(x, y, FLAG_W, FLAG_H), paint(Shader=gl))
    canvas.restore()
    canvas.drawRRect(r, paint(skia.Color(255, 255, 255, int(55 * alpha)), style="stroke", StrokeWidth=1.2))


def draw_bar(canvas, x, y, w, h, caps, alpha, t, value_txt):
    if w < 2:
        w = 2
    depth = 5  # tiny extrusion for the 3D feel
    # drop shadow
    sh = paint(skia.Color(0, 0, 0, int(150 * alpha)))
    sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 7))
    canvas.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x + 3, y + 8, w, h), 8, 8), sh)
    # extrusion (bottom face)
    canvas.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x + 1.5, y + depth, w, h), 8, 8),
                     paint(skia.Color(110, 116, 128, int(255 * alpha))))
    # main face: light-grey metal
    face = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), 8, 8)
    sh_face = skia.GradientShader.MakeLinear([(0, y), (0, y + h)], [C_BAR_HI, C_BAR_LO])
    fp = paint(Shader=sh_face)
    fp.setAlphaf(alpha)
    canvas.drawRRect(face, fp)
    canvas.save()
    canvas.clipRRect(face, True)
    # colour cap that fades into the grey bar
    cap_w = min(w, 120)
    cs = skia.GradientShader.MakeLinear([(x + w - cap_w, 0), (x + w, 0)],
                                        [skia.Color4f(0, 0, 0, 0).toColor(), caps[0]], [0.0, 1.0])
    cp = paint(Shader=cs)
    cp.setAlphaf(alpha * 0.95)
    canvas.drawRect(skia.Rect.MakeXYWH(x + w - cap_w, y, cap_w, h), cp)
    tip = paint(caps[1])
    tip.setAlphaf(alpha)
    canvas.drawRect(skia.Rect.MakeXYWH(x + w - 7, y, 7, h), tip)
    # moving sheen
    sx = x + ((t * 220) % (w + 300)) - 150
    sheen = skia.GradientShader.MakeLinear([(sx - 60, 0), (sx + 60, 0)],
                                           [skia.Color(255, 255, 255, 0), skia.Color(255, 255, 255, int(70 * alpha)),
                                            skia.Color(255, 255, 255, 0)])
    canvas.drawRect(skia.Rect.MakeXYWH(x, y, w, h), paint(Shader=sheen))
    # top highlight line
    canvas.drawRect(skia.Rect.MakeXYWH(x + 6, y + 2, max(w - 12, 0), 2),
                    paint(skia.Color(255, 255, 255, int(170 * alpha))))
    canvas.restore()
    # glow at tip
    gl = paint(caps[0])
    gl.setAlphaf(0.55 * alpha)
    gl.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 9))
    canvas.drawCircle(x + w - 3, y + h / 2, h * 0.42, gl)
    # value
    text(canvas, value_txt, x + w + 14, y + h - 7, font("bold", 25), C_TEXT, alpha=alpha)


def fit_font(s, weight, size, maxw):
    f = font(weight, size)
    while f.measureText(s) > maxw and size > 18:
        size -= 1
        f = font(weight, size)
    return f


def draw_row(canvas, c, y, g, d, axis, alpha, t, grow=1.0, emphasis=0.0):
    if alpha <= 0.01:
        return
    # glass row card (keeps overlapping rows clean during swaps)
    card = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(SAFE_L - 16, y - 2, W - 2 * SAFE_L + 32, ROW_H - 10), 18, 18)
    cs = skia.GradientShader.MakeLinear([(0, y), (0, y + ROW_H)],
                                        [skia.Color(40, 44, 54, int(235 * alpha)), skia.Color(27, 30, 37, int(235 * alpha))])
    canvas.drawRRect(card, paint(Shader=cs))
    canvas.drawRRect(card, paint(skia.Color(255, 255, 255, int(16 * alpha)), style="stroke", StrokeWidth=1.2))
    draw_flag(canvas, c, SAFE_L, y + (ROW_H - FLAG_H) / 2 - 8, alpha)
    name = NAMES[c]
    f = fit_font(name, "semi", 29, BAR_X0 - NAME_X - 14)
    text(canvas, name, NAME_X, y + ROW_H / 2 - 4, f, C_TEXT, alpha=alpha)
    text(canvas, c, NAME_X, y + ROW_H / 2 + 26, font("med", 19), C_MUTED, alpha=alpha * 0.8)
    scale = BAR_MAX_W / axis
    by = y + (ROW_H - (2 * BAR_H + BAR_GAP)) / 2 - 6
    draw_bar(canvas, BAR_X0, by, g * scale * grow, BAR_H, C_GAS, alpha, t + (sum(map(ord, c)) % 7), f"${g:.2f}")
    draw_bar(canvas, BAR_X0, by + BAR_H + BAR_GAP, d * scale * grow, BAR_H, C_DSL, alpha, t + 1.3 + (sum(map(ord, c)) % 5),
             f"${d:.2f}")


MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def draw_header(canvas, t, m, intro_k):
    a = ease_out(intro_k)
    dy = (1 - a) * -30
    text(canvas, "GASOLINE vs DIESEL", SAFE_L, 262 + dy, font("black", 58), C_TEXT, alpha=a)
    text(canvas, "Price per liter in US$ · Europe 1999–2026", SAFE_L, 306 + dy, font("med", 27), C_MUTED, alpha=a)
    # legend chips
    lx, ly = SAFE_L, 338
    for label, caps in (("Gasoline", C_GAS), ("Diesel", C_DSL)):
        sh = skia.GradientShader.MakeLinear([(lx, 0), (lx + 26, 0)], [caps[0], caps[1]])
        canvas.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(lx, ly + 4, 26, 16), 5, 5),
                         paint(Shader=sh, Alphaf=a))
        w = text(canvas, label, lx + 36, ly + 20, font("semi", 23), C_TEXT, alpha=a)
        lx += 36 + w + 34
    # year / month (right side)
    mi = int(round(m))
    y_lbl = months[min(mi, NM - 1)]
    year, mon = y_lbl[:4], MONTHS[int(y_lbl[5:]) - 1]
    yf = font("disp", 132)
    yw = yf.measureText(year)
    # subtle glow behind year
    gp = paint(skia.Color(255, 255, 255, 30))
    gp.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 22))
    canvas.drawTextBlob(skia.TextBlob.MakeFromString(year, yf), W - SAFE_L - yw, 392, gp)
    text(canvas, year, W - SAFE_L, 392, yf, skia.Color(235, 238, 244), align="right", alpha=a)
    text(canvas, mon, W - SAFE_L - 4, 262, font("bold", 30), C_MUTED, align="right", alpha=a)


def draw_axis(canvas, axis, alpha):
    step = 0.5 if axis < 3.2 else 1.0
    v = step
    f = font("med", 19)
    while v < axis * 0.999:
        x = BAR_X0 + v / axis * BAR_MAX_W
        canvas.drawRect(skia.Rect.MakeXYWH(x - 0.6, ROWS_TOP - 12, 1.2, 8), paint(skia.Color(255, 255, 255, int(60 * alpha))))
        lab = f"${v:.2f}" if step < 1 else f"${v:.0f}"
        text(canvas, lab, x, ROWS_TOP - 16, f, skia.Color(120, 128, 142), align="center", alpha=alpha)
        v += step


def draw_event(canvas, t):
    starts = [T_INTRO + months.index(lbl) / (NM - 1) * T_RACE for lbl, _ in EVENTS]
    for i, (lbl, msg) in enumerate(EVENTS):
        t0 = starts[i]
        dur = min(EVENT_DUR, (starts[i + 1] - t0 - 0.05) if i + 1 < len(EVENTS) else EVENT_DUR)
        k = (t - t0) / dur
        if 0 <= k <= 1:
            a = min(1.0, k / 0.12, (1 - k) / 0.15)
            a = ease_in_out(a)
            f = font("semi", 25)
            w = f.measureText(msg) + 44
            x, y = SAFE_L, 392
            r = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y - (1 - a) * 12, w, 46), 23, 23)
            canvas.drawRRect(r, paint(skia.Color(255, 255, 255, int(28 * a))))
            canvas.drawRRect(r, paint(skia.Color(255, 196, 66, int(170 * a)), style="stroke", StrokeWidth=1.6))
            canvas.drawCircle(x + 20, y + 23 - (1 - a) * 12, 5, paint(skia.Color(255, 176, 50, int(255 * a))))
            text(canvas, msg, x + 34, y + 32 - (1 - a) * 12, f, C_TEXT, alpha=a)


def draw_pinned_header(canvas, alpha):
    y = PIN_SEP_Y + 18
    f = font("bold", 19)
    lab = "FOR COMPARISON"
    w = f.measureText(lab)
    text(canvas, lab, SAFE_L, y, f, C_MUTED, alpha=alpha)
    canvas.drawRect(skia.Rect.MakeXYWH(SAFE_L + w + 16, y - 7, W - 2 * SAFE_L - w - 16, 1.5),
                    paint(skia.Color(255, 255, 255, int(40 * alpha))))


def draw_footer(canvas, alpha):
    f = font("med", 19)
    text(canvas, "Monthly averages, converted at monthly avg. exchange rates · Sources at the end",
         SAFE_L, PIN_TOP + 3 * ROW_H + 18, f, skia.Color(120, 128, 142), alpha=alpha)


def draw_outro(canvas, k, standings):
    if k <= 0:
        return
    a = ease_in_out(min(1.0, k / 0.18))
    # dim + card
    canvas.drawRect(skia.Rect(0, 0, W, H), paint(skia.Color(6, 7, 10, int(170 * a))))
    card = skia.Rect.MakeXYWH(SAFE_L - 8, 470 + (1 - a) * 60, W - 2 * SAFE_L + 16, 850)
    rr = skia.RRect.MakeRectXY(card, 28, 28)
    sh = paint(skia.Color(0, 0, 0, int(160 * a)))
    sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 24))
    canvas.drawRRect(rr.makeOffset(0, 16), sh)
    cs = skia.GradientShader.MakeLinear([(0, card.top()), (0, card.bottom())],
                                        [skia.Color(38, 42, 52, int(245 * a)), skia.Color(22, 25, 31, int(245 * a))])
    canvas.drawRRect(rr, paint(Shader=cs))
    canvas.drawRRect(rr, paint(skia.Color(255, 255, 255, int(40 * a)), style="stroke", StrokeWidth=1.5))
    x0, y = card.left() + 44, card.top() + 84
    text(canvas, "Most expensive gasoline, Oct 2026", x0, y, font("bold", 34), C_TEXT, alpha=a)
    y += 26
    for i, (c, g) in enumerate(standings[:3]):
        y += 62
        draw_flag(canvas, c, x0, y - 40, a)
        text(canvas, f"{i + 1}. {NAMES[c]}", x0 + FLAG_W + 18, y, font("semi", 30), C_TEXT, alpha=a)
        text(canvas, f"${g:.2f}/l", card.right() - 44, y, font("bold", 30), C_GAS[0], align="right", alpha=a)
    y += 70
    canvas.drawRect(skia.Rect.MakeXYWH(x0, y, card.width() - 88, 1.5), paint(skia.Color(255, 255, 255, int(40 * a))))
    y += 52
    text(canvas, "DATA SOURCES", x0, y, font("bold", 22), C_MUTED, alpha=a)
    for s in SOURCES:
        y += 40
        f = fit_font(s, "med", 23, card.width() - 88)
        text(canvas, s, x0, y, f, skia.Color(205, 210, 220), alpha=a)
    y += 62
    text(canvas, "Which number surprised you most?", x0, y, font("bold", 30), C_DSL[0], alpha=a)


# ------------------------------------------------------------------ frame
def render_frame(canvas, f, st):
    t = f / FPS
    m, g, d, pos, axis, vel = st
    canvas.clear(skia.ColorBLACK)
    draw_background(canvas, t)
    intro_k = t / 0.9
    grow = ease_out((t - 0.4) / 1.4)
    draw_header(canvas, t, m, intro_k)
    rows_a = ease_out((t - 0.25) / 0.8)
    draw_axis(canvas, axis, rows_a)
    draw_event(canvas, t)
    # race rows (clipped so leaving rows slide under the separator)
    canvas.save()
    canvas.clipRect(skia.Rect(0, ROWS_TOP - 30, W, PIN_SEP_Y - 2))
    # rows that are falling are drawn first (underneath) and slightly dimmed, rising rows pass over them
    for c in sorted(RACE, key=lambda c: (vel[c] <= 0.002, -pos[c])):
        p = pos[c]
        if p > TOP_N + 0.5:
            continue
        alpha = min(1.0, max(0.0, TOP_N + 0.15 - p)) * rows_a
        if vel[c] > 0.002:
            alpha *= 1.0 - min(0.4, vel[c] * 9)
        y = ROWS_TOP + p * ROW_H
        draw_row(canvas, c, y, g[c], d[c], axis, alpha, t, grow)
    canvas.restore()
    draw_pinned_header(canvas, rows_a)
    for i, c in enumerate(PINNED):
        draw_row(canvas, c, PIN_TOP + i * ROW_H, g[c], d[c], axis, rows_a, t, grow)
    draw_footer(canvas, rows_a)
    t_out = T_INTRO + T_RACE + T_HOLD
    if t >= t_out:
        standings = sorted(((c, g[c]) for c in RACE), key=lambda x: -x[1])
        draw_outro(canvas, (t - t_out) / T_OUTRO, standings)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=int, nargs="*", help="frame numbers to save as PNG")
    ap.add_argument("--out", default=str(BUILD / "race_silent.mp4"))
    ap.add_argument("--start", type=int, default=0, help="first frame (for parallel rendering)")
    ap.add_argument("--end", type=int, default=None, help="last frame, exclusive")
    args = ap.parse_args()
    print("precomputing", NF, "frames")
    states = precompute()
    surface = skia.Surface(W, H)
    if args.preview is not None:
        (BUILD / "frames").mkdir(exist_ok=True)
        frames = args.preview or [60, 600, 1700, 2600, 3000, 3300, NF - 30]
        for f in frames:
            with surface as canvas:
                render_frame(canvas, f, states[f])
            surface.makeImageSnapshot().save(str(BUILD / "frames" / f"f{f:05d}.png"), skia.kPNG)
        print("saved previews")
        return
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", args.out],
                          stdin=subprocess.PIPE)
    end = NF if args.end is None else min(args.end, NF)
    for f in range(args.start, end):
        with surface as canvas:
            render_frame(canvas, f, states[f])
        img = surface.makeImageSnapshot()
        ff.stdin.write(img.tobytes())
        if f % 300 == 0:
            print("frame", f, "/", NF, flush=True)
    ff.stdin.close()
    ff.wait()
    print("done", args.out)


if __name__ == "__main__":
    main()
