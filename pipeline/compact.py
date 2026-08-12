#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compacte l'archive Delft3D en un fichier unique contenant uniquement
ce que le site affiche.

Sur les sorties completes (~208 Go pour 790 runs), le site ne lit que
six champs a un pas de temps : U1 et V1 cote FLOW, hsign, wlength,
period et dir cote WAVE. Tout le reste — S1, R1, RHO, les contraintes
de fond, 23 des 24 pas de temps, les couches non affichees — n'est
jamais servi.

Le fichier produit :
  - ne garde que les mailles dont les coordonnees sont valides, les
    mailles seches conservant une valeur nulle (c'est elle qui dessine
    le trait de cote a l'affichage) ;
  - stocke les coordonnees en degres, une seule fois, partagees par
    tous les scenarios ;
  - stocke les vitesses deja projetees en composantes est/nord, donc
    sans rotation ni convergence a appliquer au moment de l'affichage ;
  - encode les champs en entiers 16 bits avec facteur d'echelle
    (precision tres superieure a celle du modele) et compresse en zlib.

Usage :
    python pipeline/compact.py                 # -> data/compact.nc
    python pipeline/compact.py --layers 0,4,9  # plusieurs couches
    python pipeline/compact.py --dry-run       # estime la taille
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import geo  # noqa: E402
import scenario_field as sfield  # noqa: E402
from scenarios import PARAM_SPECS  # noqa: E402

OUT_FILE = ROOT / "data" / "compact.nc"
INDEX_FILE = ROOT / "data" / "scenarios.json"

# Champ -> (source, variable, pas d'encodage entier 16 bits)
# Le pas est choisi tres en dessous de l'incertitude du modele :
# 0,1 mm/s sur une vitesse, 0,1 mm sur une hauteur de vague.
# Le pas est choisi tres en dessous de l'incertitude du modele, mais le
# plafond (32767 x pas) doit rester au-dessus de toute valeur physique
# plausible : un depassement serait ecrete silencieusement.
#   pas 2e-4 -> plafond 6.55   pas 2e-2 -> plafond 655
FIELDS = {
    "flow_ue": ("flow", None, 2e-4),        # +/- 6.55 m/s
    "flow_vn": ("flow", None, 2e-4),
    "wave_hsign": ("wave", "hsign", 2e-4),  # 6.55 m
    "wave_wlength": ("wave", "wlength", 2e-2),  # 655 m
    "wave_period": ("wave", "period", 1e-3),    # 32.8 s
    "wave_dir": ("wave", "dir", 2e-2),          # 655 deg
}
FILL = -32768


def load_index():
    """Index des scenarios, avec les gardes qui evitent de travailler
    sur des chemins qui n'existent pas."""
    import json

    path = INDEX_FILE
    if not path.exists():
        raise RuntimeError(
            "Index absent : lancez d'abord\n"
            "    python pipeline/scenario_index.py")
    with open(path, "r", encoding="utf-8") as f:
        idx = json.load(f)

    if idx.get("demo"):
        raise RuntimeError(
            "L'index chargé est celui de démonstration (chemins <demo>/…), "
            "livré pour que le site affiche quelque chose au premier "
            "lancement.\nReconstruisez-le sur vos simulations :\n"
            "    python pipeline/scenario_index.py")
    return idx


def existing_scenarios(scen):
    """Ecarte les runs dont les fichiers ne sont plus la (archive
    deplacee, disque externe absent) plutot que d'echouer en cours de
    route."""
    kept, missing = [], []
    for entry in scen:
        files = {k: v for k, v in (entry.get("files") or {}).items()
                 if Path(v).exists()}
        if files:
            kept.append({**entry, "files": files})
        else:
            missing.append(entry["key"])
    return kept, missing


def cell_coords(path, zone, south):
    """Coordonnees geographiques des mailles valides + masque."""
    ds = sfield.open_dataset(path)
    try:
        names = list(ds.variables)
        xname, yname, xv, yv, _, _ = sfield.read_coords(ds, names)
        if xname is None:
            raise ValueError(f"No usable coordinates in {Path(path).name}")
        good = np.isfinite(xv) & np.isfinite(yv)
        lon = np.full(xv.shape, np.nan)
        lat = np.full(xv.shape, np.nan)
        idx = np.argwhere(good)
        for iy, ix in idx:
            lon[iy, ix], lat[iy, ix] = geo.utm_to_lonlat(
                float(xv[iy, ix]), float(yv[iy, ix]), zone, south)
        return good, lon[good], lat[good], xv, yv
    finally:
        ds.close()


def rotation_terms(xv, yv, lon, lat, zone, good, rotate=True):
    """Cosinus et sinus de la rotation totale ksi/eta -> est/nord.

    L'angle de la grille et la convergence des meridiens ne dependent
    que de la geometrie : ils sont identiques pour les 790 runs et se
    calculent donc une seule fois. Les recalculer par scenario et par
    couche representerait des dizaines de millions d'appels.
    """
    total = np.radians(grid_convergence_array(lon, lat, zone))
    if rotate:
        ang = sfield.grid_rotation(xv, yv)
        if ang is not None and np.isfinite(ang).any():
            total = total + np.where(np.isfinite(ang), ang, 0.0)[good]
    return np.cos(total), np.sin(total)


def grid_convergence_array(lon, lat, zone):
    """Convergence des meridiens, vectorisee (degres)."""
    dlon = np.radians(lon - geo.zone_central_meridian(zone))
    return np.degrees(np.arctan(np.tan(dlon) * np.sin(np.radians(lat))))


def read_flow(path, good, layers, time_index, cos_a, sin_a):
    """Vitesses est/nord des mailles valides, pour chaque couche.

    Les mailles SECHES sont renvoyees a NaN (et stockees en FILL), ce
    qui les distingue d'une eau calme ou la vitesse vaut zero. Le
    critere est le niveau d'eau S1, nul hors de l'eau.
    """
    ds = sfield.open_dataset(path)
    try:
        wet = sfield.wet_mask(ds, "S1", time_index)
        wet = None if wet is None else wet[good]
        out = []
        for lay in layers:
            u, _, _, _ = sfield._read_2d(ds, "U1", time_index, lay)
            v, _, _, _ = sfield._read_2d(ds, "V1", time_index, lay)
            u = np.where(np.isfinite(u), u, 0.0)[good]
            v = np.where(np.isfinite(v), v, 0.0)[good]
            ue = u * cos_a - v * sin_a
            vn = u * sin_a + v * cos_a
            if wet is not None:
                ue = np.where(wet, ue, np.nan)
                vn = np.where(wet, vn, np.nan)
            out.append((ue, vn))
        return out
    finally:
        ds.close()


def read_wave(path, good, varname, time_index):
    """Champ de vagues des mailles valides, NaN hors de l'eau.

    Le critere est la profondeur `depth`, nulle hors de l'eau ; a
    defaut, la valeur manquante du champ lui-meme.
    """
    ds = sfield.open_dataset(path)
    try:
        a, _, _, _ = sfield._read_2d(ds, varname, time_index, 0)
        wet = sfield.wet_mask(ds, "depth", time_index)
        if wet is None:
            wet = np.isfinite(a) & (np.abs(a) > 0)
        return np.where(wet, a, np.nan)[good]
    finally:
        ds.close()


def pack(values, scale, counter=None, name=""):
    """Reels -> entiers 16 bits.

    Les valeurs non finies deviennent FILL. Un ecretage (valeur au-dela
    du plafond 32767 x scale) est comptabilise : il fausserait le champ
    sans aucun autre symptome.
    """
    a = np.asarray(values, dtype="float64")
    finite = np.isfinite(a)
    q = np.zeros(a.shape, dtype="float64")
    q[finite] = np.round(a[finite] / scale)

    over = finite & ((q > 32767) | (q < FILL + 1))
    if counter is not None and over.any():
        counter[name] = counter.get(name, 0) + int(over.sum())

    q = np.clip(q, FILL + 1, 32767)
    out = q.astype("int16")
    out[~finite] = FILL
    return out


def verify_roundtrip(variables, n, expected, tol_factor=3.0):
    """Relit ce qui vient d'etre ecrit et le compare a la source.

    Effectuee des le premier scenario : une erreur d'encodage est ainsi
    detectee en quelques secondes, au lieu d'aboutir a un fichier
    complet mais faux apres des heures de traitement.
    """
    problems = []
    for name, (source, scale) in expected.items():
        var = variables.get(name)
        if var is None or source is None or not len(source):
            continue
        raw = np.asarray(var[n] if var.ndim == 2 else var[n, 0])
        back = raw.astype("float64") * scale
        ok = np.isfinite(source) & (raw != FILL)
        if not ok.any():
            continue
        err = np.abs(back[ok] - source[ok]).max()
        if err > tol_factor * scale:
            problems.append(
                f"{name} : écart max {err:.4g} pour un pas de {scale:g} "
                f"(attendu ≤ {tol_factor * scale:g})")
    return problems


class SystematicFailure(RuntimeError):
    """Toutes les lectures echouent : c'est un defaut de code ou de
    configuration, pas des donnees abimees."""


def check_systematic(failures, n, exc, probe=12):
    """Interrompt le traitement si les premiers scenarios echouent tous.

    Tolerer les echecs protege d'un run abime isole, mais ne doit pas
    transformer un bug en fichier vide produit apres des heures : au
    dela de quelques echecs consecutifs des le depart, on s'arrete.
    """
    if n + 1 <= probe and len(failures) >= probe:
        raise SystematicFailure(
            f"Les {probe} premiers scénarios ont tous échoué "
            f"({type(exc).__name__}: {exc}).\n"
            "Ce n'est pas un problème de données : vérifiez la "
            "configuration, ou signalez cette erreur.") from exc


def resumable(out_path, keys, layers):
    """Scenarios deja compactes dans un fichier existant.

    Retourne (cles_faites, utilisable). Le fichier n'est reutilisable
    que si sa liste de scenarios et ses couches correspondent
    exactement a la demande courante : completer un fichier construit
    avec d'autres parametres produirait un melange silencieux.
    """
    if not out_path.exists():
        return set(), False
    try:
        from netCDF4 import Dataset
        ds = Dataset(str(out_path), "r")
    except Exception:
        return set(), False
    try:
        if "key" not in ds.variables:
            return set(), False
        existing = [str(k) for k in ds.variables["key"][:]]
        if len(existing) != len(keys):
            return set(), False
        prev_layers = [int(t) for t in np.atleast_1d(getattr(ds, "layers", []))]
        if prev_layers != [int(t) for t in layers]:
            return set(), False
        # Les cles ecrites doivent occuper les memes positions
        for n, k in enumerate(existing):
            if k and k != keys[n]:
                return set(), False

        done = set()
        var = ds.variables.get("flow_ue")
        if var is None:
            return set(), False
        var.set_auto_maskandscale(False)
        for n, k in enumerate(existing):
            if not k:
                continue
            row = np.asarray(var[n, 0, :])
            # Un scenario en echec a ete laisse vide : il sera retraite
            if np.any((row != FILL) & (row != 0)):
                done.add(k)
        return done, True
    except Exception:
        return set(), False
    finally:
        ds.close()


def build(cfg, layers, time_index, out_path=OUT_FILE, dry_run=False,
          limit=None, resume=False):
    idx = load_index()
    scen, missing = existing_scenarios(idx["scenarios"])
    if missing:
        print(f"Attention : {len(missing)} run(s) introuvable(s) sur le "
              f"disque, ignoré(s) — ex. {missing[0]}")
    if limit:
        scen = scen[:limit]
    if not scen:
        raise RuntimeError(
            f"Aucun fichier lisible dans {idx.get('directory')} — le disque "
            "des simulations est-il monté ?\n"
            "Relancez pipeline/scenario_index.py si l'archive a bougé.")

    scfg = cfg.get("scenarios") or {}
    south = scfg.get("southern_hemisphere", True)
    centre = (cfg.get("lake") or {}).get("center") or {}
    zone = scfg.get("utm_zone") or geo.infer_zone(centre.get("lon", 137.5))

    # Grilles : identiques d'un run a l'autre, lues une seule fois
    ref_flow = next((s["files"]["flow"] for s in scen if "flow" in s["files"]),
                    None)
    ref_wave = next((s["files"]["wave"] for s in scen if "wave" in s["files"]),
                    None)
    if not ref_flow and not ref_wave:
        raise RuntimeError("Aucune sortie FLOW ni WAVE lisible dans l'index.")
    grids = {}
    if ref_flow:
        g, lon, lat, xv, yv = cell_coords(ref_flow, zone, south)
        cos_a, sin_a = rotation_terms(xv, yv, lon, lat, zone, g,
                                      rotate=scfg.get("rotate_vectors", True))
        grids["flow"] = {"mask": g, "lon": lon, "lat": lat,
                         "cos_a": cos_a, "sin_a": sin_a}
        print(f"Grille FLOW : {g.size} mailles, {g.sum()} valides")
    if ref_wave:
        g, lon, lat, xv, yv = cell_coords(ref_wave, zone, south)
        grids["wave"] = {"mask": g, "lon": lon, "lat": lat}
        print(f"Grille WAVE : {g.size} mailles, {g.sum()} valides")

    n_s = len(scen)
    n_lay = len(layers)
    est = 0
    for name, (src, _, _) in FIELDS.items():
        if src not in grids:
            continue
        n_cell = int(grids[src]["mask"].sum())
        est += n_s * n_cell * 2 * (n_lay if src == "flow" else 1)
    human = ", ".join(f"{k + 1}" for k in layers)
    print(f"\n{n_s} scénarios")
    print(f"  couches conservées : indices {layers} "
          f"= couche(s) {human} sur 10 dans l'interface")
    print(f"  pas de temps       : {time_index} "
          f"({'dernier' if time_index == -1 else time_index})")
    unit, div = ("Mo", 1e6) if est >= 1e6 else ("Ko", 1e3)
    print(f"Taille brute estimée : {est / div:.1f} {unit} "
          f"(avant compression zlib, typiquement ÷2)")
    if dry_run:
        return None

    try:
        from netCDF4 import Dataset
    except ImportError:
        raise RuntimeError("netCDF4 est requis pour écrire le fichier "
                           "compact (pip install netCDF4).")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Reprise : le fichier existant est complete en place, ce qui evite
    # de relire les scenarios deja traites. On n'y touche que si sa
    # structure correspond exactement a la demande courante.
    done = set()
    append = False
    if resume:
        done, ok = resumable(out_path, [e["key"] for e in scen], layers)
        if ok:
            append = True
            print(f"Reprise : {len(done)} scénario(s) déjà compacté(s), "
                  f"{len(scen) - len(done)} restant(s)")
            if len(done) == len(scen):
                print("Rien à faire — le fichier est complet.")
                return out_path
        elif out_path.exists():
            print("Le fichier existant ne correspond pas à cette demande "
                  "(scénarios ou couches différents) : reconstruction "
                  "complète.")

    nc = Dataset(out_path, "a" if append else "w", format="NETCDF4")
    try:
        if append:
            keys = nc.variables["key"]
            variables = {n: nc.variables[n] for n in FIELDS
                         if n in nc.variables}
            for v in variables.values():
                v.set_auto_maskandscale(False)
            _create_structure = False
        else:
            _create_structure = True

        # Attributs volontairement en ASCII : le format NetCDF3 les
        # exige et certains lecteurs anciens butent sur l'UTF-8.
        nc.title = "Kati Thanda - Lake Eyre: compacted Delft3D output"
        nc.created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        nc.source_directory = str(idx.get("directory", ""))
        nc.utm_zone = zone
        nc.time_index = time_index
        nc.layers = np.array(layers, dtype="i4")
        if ref_flow:
            try:
                ds0 = sfield.open_dataset(ref_flow)
                try:
                    lay_dim = next((d for d in ds0.dimensions
                                    if sfield.is_layer_dim(d)), None)
                    if lay_dim:
                        nc.n_layers_source = int(len(ds0.dimensions[lay_dim]))
                finally:
                    ds0.close()
            except Exception:
                pass
        nc.note = ("Velocity components already expressed as geographic "
                   "east/north; dry cells set to zero.")

        if _create_structure:
          nc.createDimension("scenario", n_s)
          nc.createDimension("layer", n_lay)
          for src, g in grids.items():
              nc.createDimension(f"{src}_cell", int(g["mask"].sum()))
              for axis in ("lon", "lat"):
                  v = nc.createVariable(f"{src}_{axis}", "f8",
                                        (f"{src}_cell",),
                                        zlib=True, complevel=4)
                  v[:] = g[axis]
                  v.units = ("degrees_east" if axis == "lon"
                             else "degrees_north")

          keys = nc.createVariable("key", str, ("scenario",))
          for k in PARAM_SPECS:
              nc.createVariable(k, "f4", ("scenario",))

          variables = {}
          for name, (src, _, scale) in FIELDS.items():
              if src not in grids:
                  continue
              dims = (("scenario", "layer", "flow_cell") if src == "flow"
                      else ("scenario", "wave_cell"))
              chunk = ((1, 1, int(grids[src]["mask"].sum())) if src == "flow"
                       else (1, int(grids[src]["mask"].sum())))
              v = nc.createVariable(name, "i2", dims, zlib=True, complevel=4,
                                    chunksizes=chunk, fill_value=FILL)
              # netCDF4 divise AUTOMATIQUEMENT par scale_factor a
              # l'ecriture. Comme pack() a deja converti en entiers, il
              # faut couper cet automatisme : sans cela la division a
              # lieu deux fois, l'entier 16 bits deborde et les champs
              # relus sont absurdes (courants satures, vagues bruitees).
              v.set_auto_maskandscale(False)
              v.scale_factor = scale
              variables[name] = v

        failures = []
        clipped = {}
        verified = False
        for n, entry in enumerate(scen):
            if entry["key"] in done:
                continue
            keys[n] = entry["key"]
            for k in PARAM_SPECS:
                nc.variables[k][n] = entry["params"].get(k, np.nan)

            # Un run defectueux (sortie tronquee, dimension vide, fichier
            # corrompu) ne doit pas annuler le travail deja fait : il est
            # signale, laisse vide, et le compactage continue.
            check = {}
            flow = entry["files"].get("flow")
            if flow and "flow" in grids:
                g = grids["flow"]
                try:
                    # read_flow applique deja la rotation complete
                    # (grille + convergence) via cos_a / sin_a.
                    for li, (ue, vn) in enumerate(read_flow(
                            flow, g["mask"], layers, time_index,
                            g["cos_a"], g["sin_a"])):
                        variables["flow_ue"][n, li, :] = pack(
                            ue, FIELDS["flow_ue"][2], clipped, "flow_ue")
                        variables["flow_vn"][n, li, :] = pack(
                            vn, FIELDS["flow_vn"][2], clipped, "flow_vn")
                        if li == 0:
                            check["flow_ue"] = (ue, FIELDS["flow_ue"][2])
                            check["flow_vn"] = (vn, FIELDS["flow_vn"][2])
                except Exception as e:
                    failures.append((entry["key"], "FLOW",
                                     f"{type(e).__name__}: {e}"[:120]))
                    check_systematic(failures, n, e)

            wave = entry["files"].get("wave")
            if wave and "wave" in grids:
                g = grids["wave"]
                for name, (src, var, scale) in FIELDS.items():
                    if src != "wave":
                        continue
                    try:
                        vals = read_wave(wave, g["mask"], var, time_index)
                        variables[name][n, :] = pack(vals, scale, clipped,
                                                     name)
                        check[name] = (vals, scale)
                    except Exception as e:
                        failures.append((entry["key"], var,
                                         f"{type(e).__name__}: {e}"[:120]))
                        check_systematic(failures, n, e)

            # Verification par relecture, une seule fois
            if not verified and check:
                verified = True
                problems = verify_roundtrip(variables, n, check)
                if problems:
                    raise SystematicFailure(
                        "Le premier scénario relu ne correspond pas à la "
                        "source :\n  " + "\n  ".join(problems) +
                        "\nLe fichier serait faux : compactage interrompu.")
                print("  vérification par relecture : conforme")

            if (n + 1) % 25 == 0 or n + 1 == n_s:
                extra = f", {len(failures)} échec(s)" if failures else ""
                print(f"  {n + 1}/{n_s} scénarios{extra}")

        if clipped:
            print("\nAttention : valeurs écrêtées (au-delà du plafond de "
                  "l'encodage 16 bits) :")
            for name, count in sorted(clipped.items()):
                scale = FIELDS[name][2]
                print(f"    {name} : {count} valeur(s) > {32767 * scale:g}")
            print("  Augmentez le pas correspondant dans FIELDS "
                  "(pipeline/compact.py).")

        if failures and len({k for k, _, _ in failures}) >= len(scen):
            raise SystematicFailure(
                "Aucun scénario n'a pu être lu — fichier compact "
                "inutilisable. Consultez la première erreur ci-dessus.")
        if failures:
            nc.n_failures = len(failures)
            print(f"\n{len(failures)} lecture(s) en échec, laissée(s) vide(s) :")
            seen = set()
            for key, what, msg in failures:
                if key in seen:
                    continue
                seen.add(key)
                print(f"    {key} [{what}] {msg}")
                if len(seen) >= 8:
                    print(f"    … et {len(failures) - len(seen)} autre(s)")
                    break
            print("  Ces scénarios retomberont sur la lecture des NetCDF "
                  "d'origine côté site.")
    finally:
        nc.close()

    if out_path.exists():
        print(f"\nFichier écrit : {out_path} "
              f"({out_path.stat().st_size / 1e6:.0f} Mo)")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Compactage des sorties Delft3D")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--layers", default="0",
                        help="Couches conservées, indices à partir de 0 : "
                             "0 = première couche, 9 = dixième. "
                             "Ex. --layers 0,9 pour la première et la dernière")
    parser.add_argument("--time", type=int, default=-1,
                        help="Pas de temps conservé (-1 = dernier)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Ne traiter que les N premiers scénarios")
    parser.add_argument("--dry-run", action="store_true",
                        help="Estime la taille sans écrire")
    parser.add_argument("--resume", action="store_true",
                        help="Reprend un compactage interrompu, en "
                             "réutilisant data/compact.nc s'il existe")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    layers = [int(t) for t in args.layers.split(",") if t.strip() != ""]
    try:
        build(cfg, layers, args.time, dry_run=args.dry_run, limit=args.limit,
          resume=args.resume)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"\n{e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
