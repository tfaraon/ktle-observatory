#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Profils topographiques transversaux de Kati Thanda - Lake Eyre.

Montre ce qu'un chiffre seul ne fait pas sentir : sur un lit aussi plat,
quelques centimetres de variation verticale deplacent le rivage de
plusieurs kilometres. Chaque profil porte donc, en plus du trace, la
migration horizontale du rivage pour la variation demandee.

Le fond vient par defaut de data/bathymetry.npz, la bathymetrie
reconstituee depuis une sortie Delft3D, en metres AHD sur une grille
reguliere de 500 m en UTM 53S. Un MNT GeoTIFF quelconque peut le
remplacer avec --dem.

ATTENTION AU REFERENTIEL. La bathymetrie du modele est en AHD, tandis
que la WSE mesuree par SWOT est en EGM2008. Un niveau releve sur le site
ou dans swot_wse.json doit donc etre converti avant d'etre passe ici :
--datum-offset est AJOUTE au niveau fourni, et vaut ce que
config.yaml appelle scenarios.wlvl_offset. Sans cette precaution le
rivage se deplace d'un biais systematique, et c'est exactement l'ordre
de grandeur que la figure cherche a mettre en evidence.

Le setup est le basculement du plan d'eau sous l'effet du vent : l'eau
s'accumule sur la rive sous le vent et se retire de la rive au vent.
--setup donne l'amplitude a CHAQUE extremite, en metres : la surface va
de niveau - setup a l'ouest a niveau + setup a l'est. Une valeur
negative inverse le sens.

Depuis un interpreteur, Spyder ou un carnet, il n'y a rien a taper dans
un terminal : les constantes LEVEL, SETUP, AT, DEM et OUT sont en tete
de la seconde moitie du fichier, et lancer le module les utilise.

    run()                                   # les constantes font foi
    panels = run(level=-12.4, setup=0.15)   # ou des valeurs ponctuelles
    panels[1]["per_cm"]                     # km de largeur par cm

    grid = open_grid()
    levels, widths, sens = sweep(grid, transects(grid))
    preview(panels)                         # apercu, si matplotlib est la

run() rend la liste des profils, chacun un dictionnaire portant ses
tableaux s et bed, la surface wl, et les mesures. write=False trace sans
ecrire de fichier, quiet=True sans rien afficher.

La ligne de commande reste disponible et ses options l'emportent :

    python tools/lake_profile.py
    python tools/lake_profile.py --level -13.5 --setup 0.15
    python tools/lake_profile.py --at 6803.9 --at 6863.9 --level -14.0
    python tools/lake_profile.py --sweep
    python tools/lake_profile.py --dem mnt.tif --from 678465,6800871 \\
                                 --to 781465,6800871
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BATHY = ROOT / "data" / "bathymetry.npz"

# Deux transects ouest-est, choisis sur les donnees et non a vue :
# le premier passe par le point le plus bas du lit, le second traverse
# la partie nord, retenue pour sa platitude.
DEFAULT_NORTHINGS = (6803871.0, 6863871.0)

INK, DUNE, RULE = "#1A2B30", "#64757A", "#C7D0D0"
BED, BED_LINE = "#E7DCC4", "#9A8759"
WATER, WATER_LINE = "#BBD6DC", "#2E6B78"
PAPER = "#FFFFFF"
ACCENT = "#B9833F"


# ── Lecture du relief ───────────────────────────────────────

class Grid:
    """Un relief echantillonnable, quelle qu'en soit l'origine."""

    def __init__(self, z, x0, y0, dx, dy, label):
        self.z, self.x0, self.y0 = z, x0, y0
        self.dx, self.dy, self.label = dx, dy, label

    @property
    def bounds(self):
        ny, nx = self.z.shape
        return (self.x0, self.y0,
                self.x0 + (nx - 1) * self.dx, self.y0 + (ny - 1) * self.dy)

    def sample(self, x, y):
        """Interpolation bilineaire ; hors emprise ou sans donnee -> nan."""
        fx = (np.asarray(x, dtype=float) - self.x0) / self.dx
        fy = (np.asarray(y, dtype=float) - self.y0) / self.dy
        ny, nx = self.z.shape
        out = np.full(fx.shape, np.nan)
        ok = (fx >= 0) & (fx <= nx - 1) & (fy >= 0) & (fy <= ny - 1)
        if not ok.any():
            return out
        i0 = np.floor(fy[ok]).astype(int).clip(0, ny - 2)
        j0 = np.floor(fx[ok]).astype(int).clip(0, nx - 2)
        ty, tx = fy[ok] - i0, fx[ok] - j0
        q = np.stack([self.z[i0, j0], self.z[i0, j0 + 1],
                      self.z[i0 + 1, j0], self.z[i0 + 1, j0 + 1]])
        w = np.stack([(1 - ty) * (1 - tx), (1 - ty) * tx,
                      ty * (1 - tx), ty * tx])
        # Une maille sans donnee contamine ses voisines : on l'ecarte et
        # on renormalise, plutot que de propager un nan sur 500 m.
        good = np.isfinite(q)
        w = np.where(good, w, 0.0)
        tot = w.sum(axis=0)
        vals = np.where(tot > 0, np.nansum(np.where(good, q, 0.0) * w, axis=0)
                        / np.where(tot > 0, tot, 1.0), np.nan)
        out[ok] = np.where(tot > 0.35, vals, np.nan)
        return out


def load_bathymetry(path=BATHY):
    d = np.load(path)
    bed = d["bed"]
    xv, yv = d["xv"], d["yv"]
    x0 = float(np.nanmin(xv))
    y0 = float(np.nanmin(yv))
    dx = float(np.nanmean(np.diff(xv, axis=1)))
    dy = float(np.nanmean(np.diff(yv, axis=0)))
    return Grid(bed, x0, y0, dx, dy,
                f"{path.name} ({str(d['source'])})")


def load_dem(path):
    try:
        import rasterio
    except ImportError:
        sys.exit("rasterio est necessaire pour --dem : pip install rasterio")
    with rasterio.open(path) as src:
        z = src.read(1, masked=True).filled(np.nan).astype(float)
        t = src.transform
        if t.b or t.d:
            sys.exit("MNT non aligne sur les axes : reprojetez-le d'abord.")
        # Un GeoTIFF se lit du nord au sud ; on remet le sud en premier
        # pour que l'ordonnee croisse avec l'indice, comme la grille npz.
        if t.e < 0:
            z = z[::-1]
            y0 = t.f + t.e * z.shape[0]
        else:
            y0 = t.f
        return Grid(z, t.c, y0, abs(t.a), abs(t.e), Path(path).name)


# ── Profil le long d'un transect ────────────────────────────

def profile(grid, p0, p1, step=None):
    step = step or min(abs(grid.dx), abs(grid.dy)) / 2.0
    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    n = max(2, int(length / step) + 1)
    t = np.linspace(0.0, 1.0, n)
    x = p0[0] + (p1[0] - p0[0]) * t
    y = p0[1] + (p1[1] - p0[1]) * t
    return t * length, grid.sample(x, y)


def surface(s, level, setup):
    """Plan d'eau bascule : -setup a l'origine, +setup a l'autre bout."""
    if s[-1] <= 0:
        return np.full_like(s, level)
    return level + setup * (2.0 * s / s[-1] - 1.0)


def crossings(s, bed, wl):
    """Abscisses ou la surface coupe le fond, par interpolation lineaire.

    Sans cette interpolation le rivage ne pourrait bouger que par pas de
    maille, soit 250 m ici : l'effet que la figure veut montrer serait
    quantifie par la resolution de la grille plutot que par le relief.
    """
    d = wl - bed
    ok = np.isfinite(d)
    out = []
    idx = np.where(ok)[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if b != a + 1:
            continue
        if (d[a] > 0) != (d[b] > 0):
            f = d[a] / (d[a] - d[b])
            out.append(s[a] + f * (s[b] - s[a]))
    return out


def wetted(s, bed, wl):
    d = wl - bed
    wet = np.isfinite(d) & (d > 0)
    return wet, float(np.trapezoid(wet.astype(float), s)) if wet.any() else 0.0


# ── Dessin ──────────────────────────────────────────────────

def draw(panels, level, setup, exag, source):
    PW, PH = 1700, 300          # largeur utile, hauteur d'un panneau
    L, R = 112, 1660
    TOP = 96
    GAP = 118
    H = TOP + len(panels) * (PH + GAP) + 92

    for p in panels:
        p["zmin"] = float(np.nanmin(p["bed"])) - 0.35
        p["zmax"] = max(level + abs(setup) + 0.55,
                        float(np.nanmax(p["bed"])) + 0.25)
    smax = max(p["s"][-1] for p in panels)

    def X(s):
        return L + (R - L) * s / smax

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {PW} {H}" '
           f'role="img" aria-labelledby="lp-t">',
           '<title id="lp-t">Transverse topographic profiles of Kati Thanda '
           'Lake Eyre, with the shoreline migration produced by a small '
           'change in water level</title>',
           f'<rect width="{PW}" height="{H}" fill="{PAPER}"/>',
           '<style>'
           'text{font-family:Helvetica,Arial,sans-serif;fill:#1A2B30}'
           '.ti{font-size:27px;font-weight:600}'
           '.lb{font-size:21px}'
           '.ax{font-size:19px;fill:#64757A;font-variant-numeric:tabular-nums}'
           '.nt{font-size:19px;fill:#64757A;font-style:italic}'
           '.hl{font-size:23px;font-weight:600;fill:#B9833F}'
           '</style>']

    for k, p in enumerate(panels):
        top = TOP + k * (PH + GAP)

        zmin, zmax = p["zmin"], p["zmax"]

        def Y(z, top=top, zmin=zmin, zmax=zmax):
            return top + PH * (zmax - z) / (zmax - zmin)

        s, bed, wl = p["s"], p["bed"], p["wl"]
        out.append(f'<text class="ti" x="{L}" y="{top-34}">{p["title"]}</text>')
        out.append(f'<text class="nt" x="{R}" y="{top-34}" '
                   f'text-anchor="end">{p["sub"]}</text>')
        out.append(f'<text class="hl" x="{L}" y="{top-8}">'
                   f'1 cm of water level = {p["per_cm"]:.2f} km of wetted '
                   f'width</text>')
        if p["within"] > 0:
            out.append(f'<text class="nt" x="{R}" y="{top-8}" '
                       f'text-anchor="end">bed within &#177;'
                       f'{abs(setup)*100:.0f} cm of the surface over '
                       f'{p["within"]/1000:.0f} km</text>')

        # Graduations verticales
        lo, hi = math.floor(zmin), math.ceil(zmax)
        for z in range(lo, hi + 1):
            if not (zmin <= z <= zmax):
                continue
            out.append(f'<line x1="{L-6}" y1="{Y(z):.1f}" x2="{R}" '
                       f'y2="{Y(z):.1f}" stroke="{RULE}" stroke-width="1" '
                       f'stroke-dasharray="2 6"/>')
            out.append(f'<text class="ax" x="{L-14}" y="{Y(z)+6:.1f}" '
                       f'text-anchor="end">{z}</text>')

        # Corps d'eau, entre fond et surface
        ok = np.isfinite(bed)
        wet = ok & (wl > bed)
        runs, cur = [], []
        for i, w in enumerate(wet):
            if w:
                cur.append(i)
            elif cur:
                runs.append(cur); cur = []
        if cur:
            runs.append(cur)
        for run in runs:
            pts = " ".join(f"{X(s[i]):.1f},{Y(wl[i]):.1f}" for i in run)
            pts += " " + " ".join(f"{X(s[i]):.1f},{Y(bed[i]):.1f}"
                                  for i in reversed(run))
            out.append(f'<polygon points="{pts}" fill="{WATER}"/>')

        # Fond
        seg, cur = [], []
        for i in range(len(s)):
            if ok[i]:
                cur.append(i)
            elif cur:
                seg.append(cur); cur = []
        if cur:
            seg.append(cur)
        for run in seg:
            d = " ".join(("M" if j == 0 else "L")
                         + f"{X(s[i]):.1f} {Y(bed[i]):.1f}"
                         for j, i in enumerate(run))
            out.append(f'<path d="{d} L{X(s[run[-1]]):.1f} {Y(zmin):.1f} '
                       f'L{X(s[run[0]]):.1f} {Y(zmin):.1f}Z" fill="{BED}"/>')
            out.append(f'<path d="{d}" fill="none" stroke="{BED_LINE}" '
                       f'stroke-width="2"/>')

        # La bande balayee par le basculement du vent. C'est elle qui
        # porte le propos : sur un lit aussi plat, une grande longueur
        # de fond tient dans quelques centimetres de hauteur.
        if setup:
            y1, y2 = Y(level + abs(setup)), Y(level - abs(setup))
            out.append(f'<rect x="{L}" y="{y1:.1f}" width="{R-L}" '
                       f'height="{max(2.0, y2-y1):.1f}" fill="{ACCENT}" '
                       f'fill-opacity="0.16"/>')

        # Plan d'eau : niveau au repos, puis bascule
        out.append(f'<line x1="{L}" y1="{Y(level):.1f}" x2="{R}" '
                   f'y2="{Y(level):.1f}" stroke="{WATER_LINE}" '
                   f'stroke-width="1.8" stroke-dasharray="9 7"/>')
        if setup:
            out.append(f'<line x1="{L}" y1="{Y(wl[0]):.1f}" x2="{R}" '
                       f'y2="{Y(wl[-1]):.1f}" stroke="{WATER_LINE}" '
                       f'stroke-width="2.6"/>')

        # Migration du rivage, aux deux bords
        for side, (a, b) in p["shift"].items():
            if a is None or b is None or abs(b - a) < 300.0:
                continue
            xa, xb = X(a), X(b)
            ym = Y(level) + 46
            out.append(f'<line x1="{xa:.1f}" y1="{Y(level):.1f}" x2="{xa:.1f}" '
                       f'y2="{ym+10:.1f}" stroke="{ACCENT}" stroke-width="1.6" '
                       f'stroke-dasharray="4 4"/>')
            out.append(f'<line x1="{xb:.1f}" y1="{Y(level):.1f}" x2="{xb:.1f}" '
                       f'y2="{ym+10:.1f}" stroke="{ACCENT}" stroke-width="1.6" '
                       f'stroke-dasharray="4 4"/>')
            out.append(f'<line x1="{min(xa,xb):.1f}" y1="{ym:.1f}" '
                       f'x2="{max(xa,xb):.1f}" y2="{ym:.1f}" '
                       f'stroke="{ACCENT}" stroke-width="2.4"/>')
            km = abs(b - a) / 1000.0
            anchor = "start" if side == "west" else "end"
            tx = max(xa, xb) + 12 if side == "west" else min(xa, xb) - 12
            out.append(f'<text class="hl" x="{tx:.1f}" y="{ym+30:.1f}" '
                       f'text-anchor="{anchor}">{km:.1f} km</text>')

        # Axe des abscisses
        out.append(f'<line x1="{L}" y1="{top+PH+14}" x2="{R}" '
                   f'y2="{top+PH+14}" stroke="{DUNE}" stroke-width="1.4"/>')
        for km in range(0, int(smax / 1000) + 1, 10):
            x = X(km * 1000.0)
            out.append(f'<line x1="{x:.1f}" y1="{top+PH+14}" x2="{x:.1f}" '
                       f'y2="{top+PH+21}" stroke="{DUNE}" stroke-width="1.4"/>')
            out.append(f'<text class="ax" x="{x:.1f}" y="{top+PH+42}" '
                       f'text-anchor="middle">{km}</text>')
        out.append(f'<text class="ax" x="{R}" y="{top+PH+66}" '
                   f'text-anchor="end">distance along the transect (km)</text>')
        out.append(f'<text class="ax" x="{L-72}" y="{top+PH/2:.0f}" '
                   f'text-anchor="middle" '
                   f'transform="rotate(-90 {L-72} {top+PH/2:.0f})">'
                   f'elevation (m AHD)</text>')
        out.append(f'<text class="ax" x="{L}" y="{top+PH+42}">west</text>')
        out.append(f'<text class="ax" x="{R}" y="{top+PH+42}" '
                   f'text-anchor="end">east</text>')

    foot = (f"water level {level:+.2f} m AHD"
            + (f", wind setup {setup:+.2f} m at the east shore and "
               f"{-setup:+.2f} m at the west" if setup else "")
            + f". Vertical exaggeration about {exag:,.0f}&#215;.")
    out.append(f'<text class="lb" x="{L}" y="{H-46}">{foot}</text>')
    out.append(f'<text class="nt" x="{L}" y="{H-20}">bed from {source}</text>')
    out.append("</svg>")
    return "\n".join(out)


# ── Reglages, pour une execution depuis l'interpreteur ──────
#
# Ouvrir ce fichier dans Spyder, PyCharm ou un carnet et lancer le
# module execute run() avec les valeurs ci-dessous. Les modifier ici
# suffit : rien a taper dans un terminal. La ligne de commande reste
# disponible et ses options l'emportent quand il y en a.

LEVEL = -12.6           # niveau d'eau au repos, en m AHD
SETUP = 0.10            # amplitude du setup a chaque rive, en m
DATUM_OFFSET = 0.0      # ajoute au niveau : EGM2008 vers AHD
AT = list(DEFAULT_NORTHINGS)   # ordonnees UTM des transects ouest-est
DEM = None              # chemin d'un GeoTIFF, ou None pour la npz
OUT = "lake-profiles.svg"


# ── Interface ───────────────────────────────────────────────

def open_grid(dem=None):
    """Le relief, depuis un GeoTIFF ou depuis la bathymetrie du modele."""
    return load_dem(dem) if dem else load_bathymetry()


def transects(grid, at=None, p0=None, p1=None):
    """Les traces a echantillonner, sous forme (debut, fin, titre)."""
    x0, y0, x1, y1 = grid.bounds
    if p0 and p1:
        return [(tuple(p0), tuple(p1), "Transect")]
    ys = list(at) if at else list(DEFAULT_NORTHINGS)
    ys = [v * 1000.0 if v < 100000 else v for v in ys]
    return [((x0, y), (x1, y), f"Transect at {y/1000:.1f} km N") for y in ys]


def analyse(grid, line, level, setup):
    """Un profil et ses mesures, sans rien afficher ni ecrire.

    Rend un dictionnaire : s et bed sont les tableaux du trace, wl la
    surface basculee, per_cm les kilometres de largeur mouillee gagnes
    par centimetre de montee uniforme, within la longueur de fond
    comprise dans la bande balayee par le vent.
    """
    p0, p1, title = line
    s, bed = profile(grid, p0, p1)
    if not np.isfinite(bed).any():
        return None
    wl = surface(s, level, setup)
    flat = np.full_like(s, level)

    c_flat, c_tilt = crossings(s, bed, flat), crossings(s, bed, wl)
    shift = {}
    if c_flat and c_tilt:
        shift["west"] = (c_flat[0], c_tilt[0])
        shift["east"] = (c_flat[-1], c_tilt[-1])

    _, w_flat = wetted(s, bed, flat)
    _, w_tilt = wetted(s, bed, wl)
    _, w_up = wetted(s, bed, flat + 0.05)
    _, w_dn = wetted(s, bed, flat - 0.05)
    near = np.isfinite(bed) & (np.abs(bed - level) <= abs(setup))
    within = float(np.trapezoid(near.astype(float), s)) if near.any() else 0.0

    return {"s": s, "bed": bed, "wl": wl, "title": title, "shift": shift,
            "wet_rest": w_flat, "wet_setup": w_tilt,
            "per_cm": (w_up - w_dn) / 1000.0 / 10.0, "within": within,
            "sub": f"wetted {w_flat/1000:.0f} km at rest"}


def report(panel, setup):
    """Les mesures d'un profil, en clair."""
    s, bed = panel["s"], panel["bed"]
    out = [panel["title"],
           f"  longueur du trace        {s[-1]/1000:7.1f} km",
           f"  fond                     {np.nanmin(bed):7.2f} a "
           f"{np.nanmax(bed):.2f} m AHD",
           f"  largeur mouillee, repos  {panel['wet_rest']/1000:7.1f} km",
           f"  largeur mouillee, setup  {panel['wet_setup']/1000:7.1f} km"]
    for side in ("west", "east"):
        if side in panel["shift"]:
            a, b = panel["shift"][side]
            out.append(f"  rivage {side:5}            {abs(b-a)/1000:7.2f} km "
                       f"deplaces par {abs(setup)*100:.0f} cm")
    out.append(f"  une montee uniforme de 1 cm ajoute "
               f"{panel['per_cm']:.2f} km de largeur mouillee")
    out.append(f"  fond compris a +/- {abs(setup)*100:.0f} cm de la surface "
               f"sur {panel['within']/1000:.1f} km")
    return "\n".join(out)


def sweep(grid, lines, lo=-15.0, hi=-10.0, step=0.2):
    """Largeur mouillee et sensibilite, niveau par niveau.

    Rend (niveaux, largeurs, sensibilites), chacun un tableau dont la
    seconde dimension suit l'ordre des traces. Sert a choisir le niveau
    qui illustre le propos : elle n'est pas uniforme, et son maximum
    n'est pas au meme endroit d'un transect a l'autre.
    """
    levels = np.arange(lo, hi, step)
    widths = np.zeros((len(levels), len(lines)))
    sens = np.zeros_like(widths)
    for j, (p0, p1, _) in enumerate(lines):
        s, bed = profile(grid, p0, p1)
        for i, lv in enumerate(levels):
            _, w = wetted(s, bed, np.full_like(s, lv))
            _, up = wetted(s, bed, np.full_like(s, lv + 0.05))
            _, dn = wetted(s, bed, np.full_like(s, lv - 0.05))
            widths[i, j] = w / 1000.0
            sens[i, j] = (up - dn) / 1e4
    return levels, widths, sens


def run(level=None, setup=None, at=None, dem=None, out=None,
        datum_offset=None, p0=None, p1=None, write=True, quiet=False):
    """Trace les profils et rend leurs mesures.

    Appelee sans argument, elle utilise les constantes en tete de
    fichier. Rend la liste des dictionnaires produits par analyse().

        import lake_profile as lp
        panels = lp.run(level=-12.4, setup=0.15)
        panels[1]["per_cm"]
    """
    level = LEVEL if level is None else level
    setup = SETUP if setup is None else setup
    out = OUT if out is None else out
    dem = DEM if dem is None else dem
    level = level + (DATUM_OFFSET if datum_offset is None else datum_offset)

    grid = open_grid(dem)
    lines = transects(grid, at if at is not None else AT, p0, p1)

    panels = []
    for line in lines:
        panel = analyse(grid, line, level, setup)
        if panel is None:
            if not quiet:
                print(f"  {line[2]} : aucune donnee sur ce trace, ignore")
            continue
        panels.append(panel)
        if not quiet:
            print()
            print(report(panel, setup))
    if not panels:
        raise ValueError("aucun transect exploitable")

    if write:
        smax = max(p["s"][-1] for p in panels)
        zspan = max(np.ptp(p["bed"][np.isfinite(p["bed"])])
                    for p in panels) + 1.5
        exag = (smax / 1548.0) / (zspan / 300.0)
        Path(out).write_text(draw(panels, level, setup, exag, grid.label),
                             encoding="utf-8")
        if not quiet:
            print(f"\n{out} ecrit ({len(panels)} profil(s))")
    return panels


def preview(panels, level=None, setup=None):
    """Apercu a l'ecran, si matplotlib est installe.

    Facultatif a dessein : le livrable est le SVG, et la chaine ne doit
    pas dependre d'une bibliotheque de trace pour tourner.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib absent : l'apercu est saute, le SVG reste ecrit.")
        return None
    level = LEVEL if level is None else level
    setup = SETUP if setup is None else setup
    fig, axes = plt.subplots(len(panels), 1, figsize=(11, 3.2 * len(panels)),
                             squeeze=False)
    for ax, p in zip(axes[:, 0], panels):
        km = p["s"] / 1000.0
        ax.fill_between(km, p["bed"], np.nanmin(p["bed"]) - 0.4,
                        color="#E7DCC4")
        ax.fill_between(km, p["bed"], p["wl"], where=p["wl"] > p["bed"],
                        color="#BBD6DC")
        ax.plot(km, p["bed"], color="#9A8759", lw=1.2)
        ax.axhline(level, color="#2E6B78", ls="--", lw=1.0)
        ax.plot(km, p["wl"], color="#2E6B78", lw=1.4)
        ax.set_title(f"{p['title']}  |  1 cm = {p['per_cm']:.2f} km",
                     fontsize=10, loc="left")
        ax.set_ylabel("m AHD")
    axes[-1, 0].set_xlabel("distance along the transect (km)")
    fig.tight_layout()
    return fig


# ── Ligne de commande ───────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", type=float, default=LEVEL)
    ap.add_argument("--setup", type=float, default=SETUP)
    ap.add_argument("--datum-offset", type=float, default=DATUM_OFFSET)
    ap.add_argument("--at", type=float, action="append")
    ap.add_argument("--from", dest="p0")
    ap.add_argument("--to", dest="p1")
    ap.add_argument("--dem")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)

    pt = [tuple(float(v) for v in x.split(",")) if x else None
          for x in (a.p0, a.p1)]

    if a.sweep:
        grid = open_grid(a.dem)
        lines = transects(grid, a.at, *pt)
        levels, widths, sens = sweep(grid, lines)
        print(f"{'niveau':>8}" + "".join(f"{t[:22]:>26}" for _, _, t in lines))
        print(f"{'m AHD':>8}" + "".join(f"{'largeur (km)   km/cm':>26}"
                                        for _ in lines))
        for i, lv in enumerate(levels):
            print(f"{lv:8.1f}" + "".join(
                f"{widths[i, j]:17.1f}{sens[i, j]:9.2f}"
                for j in range(len(lines))))
        return

    run(level=a.level, setup=a.setup, at=a.at, dem=a.dem, out=a.out,
        datum_offset=a.datum_offset, p0=pt[0], p1=pt[1])


if __name__ == "__main__":
    # Lance depuis un interpreteur, sans arguments : les constantes
    # ci-dessus font foi. Lance depuis un terminal avec des options,
    # elles l'emportent.
    main() if len(sys.argv) > 1 else run()
