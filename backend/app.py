#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serveur de l'observatoire Kati Thanda - Lake Eyre.

Sert le frontend statique et expose l'API :
    GET  /api/health          etat du serveur et presence des donnees
    GET  /api/wse             payload complet (series + dernieres observations)
    GET  /api/wse/latest      derniere observation par site (condense)
    POST /api/refresh         lance le pipeline en arriere-plan
                              (?download=0 : extraction seule)
    GET  /api/refresh/status  suivi de la mise a jour en cours

Le JSON est produit par pipeline/update_swot.py ; il est relu a chaque
requete, ce qui permet de rafraichir les donnees sans redemarrer.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DATA_FILE = ROOT / "data" / "swot_wse.json"
WEATHER_FILE = ROOT / "data" / "weather.json"

sys.path.insert(0, str(ROOT / "pipeline"))
import fetch_weather  # noqa: E402
import scenario_field  # noqa: E402
import scenarios as scenarios_mod  # noqa: E402
import geo  # noqa: E402
import compact_store  # noqa: E402

COMPACT_FILE = ROOT / "data" / "compact.nc"
_COMPACT = None


def compact():
    """Magasin compact, ouvert une seule fois s'il existe."""
    global _COMPACT
    if _COMPACT is None and COMPACT_FILE.exists():
        try:
            _COMPACT = compact_store.CompactStore(COMPACT_FILE)
            app.logger.info("Compact store: %d scenarios",
                            len(_COMPACT.keys))
        except Exception as e:      # fichier absent ou illisible
            app.logger.warning("Compact store unavailable: %s", e)
            _COMPACT = False
    return _COMPACT or None

with open(ROOT / "config.yaml", "r", encoding="utf-8") as _f:
    CONFIG = yaml.safe_load(_f)

app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="")

# JSON strict. Python ecrit volontiers NaN et Infinity, que la norme
# JSON interdit : le navigateur rejette alors toute la reponse avec un
# message obscur (« Unexpected token 'N' »). Mieux vaut une erreur
# serveur explicite, tracee dans les journaux, qu'une charge utile
# silencieusement illisible.
try:
    from flask.json.provider import DefaultJSONProvider

    class StrictJSONProvider(DefaultJSONProvider):
        def dumps(self, obj, **kwargs):
            kwargs.setdefault("allow_nan", False)
            return super().dumps(obj, **kwargs)

    app.json = StrictJSONProvider(app)
except ImportError:             # Flask < 2.2
    pass

REFRESH_LOCK = threading.Lock()
REFRESH_STATE = {"running": False, "started_at": None, "last": None}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_data():
    if not DATA_FILE.exists():
        return None
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Frontend ─────────────────────────────────────────────────

@app.get("/")
def index():
    return send_from_directory(str(FRONTEND), "index.html")


# ── Donnees ──────────────────────────────────────────────────

@app.get("/api/health")
def health():
    data = load_data()
    return jsonify({
        "status": "ok",
        "data_available": data is not None,
        "generated_at": data.get("generated_at") if data else None,
        "demo": data.get("demo") if data else None,
    })


@app.get("/api/wse")
def wse_full():
    data = load_data()
    if data is None:
        return jsonify({
            "error": "no_data",
            "message": "No data yet: run pipeline/update_swot.py "
                       "(or --demo for a preview).",
        }), 404
    return jsonify(data)


@app.get("/api/wse/latest")
def wse_latest():
    data = load_data()
    if data is None:
        return jsonify({"error": "no_data"}), 404
    return jsonify({
        "generated_at": data["generated_at"],
        "demo": data["demo"],
        "sites": [
            {"name": s["name"], "lon": s["lon"], "lat": s["lat"],
             "latest": s["latest"]}
            for s in data["sites"]
        ],
    })


@app.get("/api/config")
def api_config():
    """Elements de config.yaml utiles au frontend (couches d'imagerie)."""
    return jsonify({"imagery": CONFIG.get("imagery") or {}})


# ── Meteo BOM ────────────────────────────────────────────────

def _read_weather_file():
    with open(WEATHER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/weather")
def api_weather():
    """Observations BOM, avec cache TTL cote serveur : le fichier
    data/weather.json est reutilise tant qu'il est recent, sinon les
    flux sont re-interroges. En cas d'echec reseau, on sert la
    derniere version connue (marquee stale)."""
    ttl = (CONFIG.get("weather") or {}).get("cache_minutes", 15) * 60
    try:
        if (WEATHER_FILE.exists()
                and time.time() - WEATHER_FILE.stat().st_mtime < ttl):
            return jsonify(_read_weather_file())
        return jsonify(fetch_weather.update(CONFIG))
    except Exception as e:
        if WEATHER_FILE.exists():
            stale = _read_weather_file()
            stale["stale"] = True
            stale["error"] = str(e)[:200]
            return jsonify(stale)
        return jsonify({"error": "weather_unavailable",
                        "message": str(e)[:200]}), 503


# ── Scenarios Delft3D ────────────────────────────────────────

SCENARIO_FILE = ROOT / "data" / "scenarios.json"
_FIELD_CACHE = {}


def load_scenario_index():
    if not SCENARIO_FILE.exists():
        return None
    with open(SCENARIO_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_instant(raw):
    """Horodatage ISO -> datetime UTC, ou None si illisible.

    Tolere le '+' du decalage horaire transforme en espace par le
    decodage d'URL ('...T09:00:00 00:00'), et un fuseau absent.
    """
    text = (raw or "").strip().replace("Z", "+00:00")
    text = re.sub(r"\s(\d{2}:?\d{2})$", r"+\1", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _bom_dt(utc):
    """Horodatage BOM 'YYYYMMDDHHMMSS' -> datetime UTC (ou None)."""
    if not utc or len(utc) < 14:
        return None
    try:
        return datetime.strptime(utc[:14], "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def pick_observation(station, at):
    """Releve le plus proche de l'instant demande (le plus recent si
    at vaut None)."""
    if at is None:
        return station.get("latest")
    history = [r for r in (station.get("history") or []) if r.get("utc")]
    if not history:
        return station.get("latest")
    best = min(history, key=lambda r: abs(
        ((_bom_dt(r["utc"]) or at) - at).total_seconds()))
    return best


def current_conditions(at=None):
    """Conditions deduites du BOM et de SWOT a l'instant demande,
    converties dans les conventions du modele.

    at=None -> derniere observation disponible.
    Retourne (cibles, provenance).
    """
    scfg = CONFIG.get("scenarios") or {}
    target, origin = {}, {}

    # Vent : station BOM de reference
    try:
        wx = _read_weather_file() if WEATHER_FILE.exists() else None
    except Exception:
        wx = None
    if wx:
        wanted = scfg.get("wind_station")
        stations = [s for s in wx.get("stations", []) if s.get("latest")]
        st = next((s for s in stations if s["name"] == wanted),
                  stations[0] if stations else None)
        if st:
            l = pick_observation(st, at) or st["latest"]
            if l.get("wind_spd_kmh") is not None:
                target["wind_speed"] = round(l["wind_spd_kmh"] / 3.6, 2)
            if l.get("wind_dir_deg") is not None:
                d = l["wind_dir_deg"]
                if scfg.get("wind_dir_convention", "from") == "to":
                    d = (d + 180.0) % 360.0
                target["wind_dir"] = d
            obs_dt = _bom_dt(l.get("utc"))
            origin["wind"] = {
                "station": st["name"], "utc": l.get("utc"),
                "offset_min": (int(round((at - obs_dt).total_seconds() / 60))
                               if at and obs_dt else 0),
                "stale": bool(st.get("stale")), "demo": bool(wx.get("demo")),
                "wind_spd_kmh": l.get("wind_spd_kmh"),
                "wind_dir": l.get("wind_dir"),
                "convention": scfg.get("wind_dir_convention", "from"),
            }

    # Niveau d'eau : derniere observation SWOT du premier site
    data = load_data()
    if data:
        wanted_site = scfg.get("wlvl_site")
        with_data = [s for s in data["sites"] if s.get("latest")]
        site = next((s for s in with_data if s["name"] == wanted_site),
                    with_data[0] if with_data else None)
        if site:
            obs = site["latest"]
            if at is not None:
                # Derniere observation SWOT anterieure a l'instant demande
                past = [r for r in site["series"]
                        if datetime.strptime(r["date"], "%Y-%m-%dT%H:%M:%S")
                        .replace(tzinfo=timezone.utc) <= at]
                if past:
                    obs = past[-1]
            wse = obs["wse"]
            target["wlvl"] = round(wse + scfg.get("wlvl_offset", 0.0), 3)
            origin["wlvl"] = {
                "site": site["name"], "date": obs["date"],
                "wse": wse, "offset": scfg.get("wlvl_offset", 0.0),
                "demo": bool(data.get("demo")),
            }

    if scfg.get("salinity") is not None:
        target["salinity"] = float(scfg["salinity"])
        origin["salinity"] = {"source": "config.yaml"}

    return target, origin


@app.get("/api/scenarios")
def api_scenarios():
    """Grille des scenarios disponibles (sans la liste complete)."""
    idx = load_scenario_index()
    if idx is None:
        return jsonify({
            "error": "no_index",
            "message": "No index yet: run pipeline/scenario_index.py "
                       "(or --demo for a preview).",
        }), 404
    summary = {k: v for k, v in idx.items() if k != "scenarios"}
    return jsonify(summary)


@app.get("/api/scenario/match")
def api_scenario_match():
    """Scenario le plus proche des conditions courantes.

    Les parametres d'URL (wind_speed, wind_dir, wlvl, salinity)
    remplacent les valeurs observees — pour explorer la base a la main.
    """
    idx = load_scenario_index()
    if idx is None:
        return jsonify({"error": "no_index"}), 404

    at = None
    raw_at = request.args.get("at")
    if raw_at:
        at = parse_instant(raw_at)
        if at is None:
            return jsonify({"error": "bad_parameter", "param": "at"}), 400

    target, origin = current_conditions(at)
    overrides = {}
    for key in ("wind_speed", "wind_dir", "wlvl", "salinity"):
        raw = request.args.get(key)
        if raw not in (None, ""):
            try:
                target[key] = float(raw)
                overrides[key] = target[key]
            except ValueError:
                return jsonify({"error": "bad_parameter", "param": key}), 400

    if not target:
        return jsonify({"error": "no_conditions",
                        "message": "No observed conditions available (BOM "
                                   "weather and SWOT level both missing)."}), 409

    scfg = CONFIG.get("scenarios") or {}
    result = scenarios_mod.match_scenario(
        idx["scenarios"], idx["grid"], target, scfg.get("weights"),
        mode=scfg.get("normalize", "range"))
    if result is None:
        return jsonify({"error": "empty_index"}), 404

    return jsonify({
        "target": target,
        "origin": origin,
        "at": raw_at or None,
        "overrides": overrides,
        "match": result,
        "demo": bool(idx.get("demo")),
        "units": idx.get("units", {}),
        "labels": idx.get("labels", {}),
        "sources": sorted(result["scenario"].get("files", {})),
        "default_source": scfg.get("default_source", "wave"),
        "coverage": idx.get("coverage"),
    })


@app.get("/api/scenario/field")
def api_scenario_field():
    """Champ 2D d'un scenario, pret a tracer."""
    idx = load_scenario_index()
    if idx is None:
        return jsonify({"error": "no_index"}), 404

    key = request.args.get("key")
    entry = next((s for s in idx["scenarios"] if s["key"] == key), None)
    if entry is None:
        return jsonify({"error": "unknown_scenario", "key": key}), 404

    scfg_src = (CONFIG.get("scenarios") or {}).get("default_source", "wave")
    source = request.args.get("source") or scfg_src
    files = entry.get("files") or {}
    if source not in files:
        available = sorted(files)
        if not available:
            return jsonify({"error": "no_file", "key": key}), 404
        source = available[0]
    path = files[source]
    if idx.get("demo"):
        return jsonify({
            "error": "demo_index",
            "message": "Demo index: no real NetCDF output to plot. Run "
                       "pipeline/scenario_index.py against the simulation "
                       "directory.",
        }), 409

    scfg = CONFIG.get("scenarios") or {}
    var = request.args.get("var") or None

    def _int_arg(name, default):
        raw = request.args.get(name)
        try:
            return int(raw) if raw not in (None, "") else default
        except ValueError:
            return default

    layer = _int_arg("layer", scfg.get("layer_index", 0))
    tstep = _int_arg("time", scfg.get("time_index", -1))
    const = _int_arg("constituent", 0)
    cache_key = (path, var, layer, tstep, const)
    if cache_key in _FIELD_CACHE:
        return jsonify(_FIELD_CACHE[cache_key])

    try:
        field = scenario_field.read_field(
            path, varname=var,
            max_points=scfg.get("max_points", 180),
            time_index=tstep, layer_index=layer,
            constituent_index=const,
            mask_zero=scfg.get("mask_zero", "auto"))
    except Exception as e:
        return jsonify({"error": "field_unavailable",
                        "message": f"{type(e).__name__}: {e}"[:300]}), 422

    # Champs disponibles, pour le selecteur du site
    try:
        ds = scenario_field.open_dataset(path)
        try:
            available = scenario_field.describe_dataset(ds)["fields"]
        finally:
            ds.close()
        allowed = scfg.get("variables")
        if allowed:
            available = [f for f in available if f["name"] in allowed]
        field["available"] = [{"name": f["name"], "label": f["label"],
                               "units": f["units"]} for f in available]
    except Exception:
        field["available"] = []

    field["key"] = entry["key"]
    field["params"] = entry["params"]
    field["source"] = source
    field["sources"] = sorted(files)
    if len(_FIELD_CACHE) > 12:
        _FIELD_CACHE.clear()
    _FIELD_CACHE[cache_key] = field
    return jsonify(field)


def scenario_zone():
    """Fuseau MGA du modele, deduit de la position du lac et verifie."""
    scfg = CONFIG.get("scenarios") or {}
    if scfg.get("utm_zone"):
        return int(scfg["utm_zone"]), None
    centre = (CONFIG.get("lake") or {}).get("center") or {}
    sites = CONFIG.get("sites") or []
    lon = centre.get("lon") or (sites[0]["lon"] if sites else 137.5)
    lat = centre.get("lat") or (sites[0]["lat"] if sites else -28.9)
    return geo.infer_zone(lon), (lon, lat)


@app.get("/api/scenario/maplayer")
def api_scenario_maplayer():
    """Couche cartographique (courants ou vagues) sur grille lon/lat."""
    idx = load_scenario_index()
    if idx is None:
        return jsonify({"error": "no_index"}), 404

    layer = request.args.get("layer", "currents")
    spec = scenario_field.MAP_LAYERS.get(layer)
    if spec is None:
        return jsonify({"error": "unknown_layer", "layer": layer}), 400

    key = request.args.get("key")
    entry = next((s for s in idx["scenarios"] if s["key"] == key), None)
    if entry is None:
        return jsonify({"error": "unknown_scenario", "key": key}), 404
    if idx.get("demo"):
        return jsonify({"error": "demo_index",
                        "message": "Demo index: no real NetCDF output to "
                                   "plot."}), 409

    files = entry.get("files") or {}
    path = files.get(spec["source"])
    if not path:
        return jsonify({
            "error": "missing_output",
            "message": f"This layer needs the {spec['source'].upper()} "
                       f"output, which is missing for this run."}), 404

    scfg = CONFIG.get("scenarios") or {}

    def _int_arg(name, default):
        raw = request.args.get(name)
        try:
            return int(raw) if raw not in (None, "") else default
        except ValueError:
            return default

    lvl = _int_arg("layer_index", scfg.get("layer_index", 0))
    tstep = _int_arg("time", scfg.get("time_index", -1))
    cache_key = (path, "__map__", layer, lvl, tstep)
    if cache_key in _FIELD_CACHE:
        return jsonify(_FIELD_CACHE[cache_key])

    zone, hint = scenario_zone()
    scales = (scfg.get("layer_scales") or {}).get(layer) or [None, None]
    common = dict(grid_res=scfg.get("map_grid_res", 260),
                  n_arrows=scfg.get("arrow_density", 26),
                  smooth=scfg.get("current_smooth", 2.0),
                  vmin=scales[0], vmax=scales[1],
                  wave_dir_convention=scfg.get("wave_dir_convention", "from"))

    # Le fichier compact, s'il existe, evite d'ouvrir un NetCDF de
    # plusieurs centaines de Mo a chaque requete.
    store = compact()
    if store is not None and store.has(key):
        try:
            out = store.map_layer(key, layer=layer, layer_index=lvl, **common)
            out["key"] = entry["key"]
            out["layers"] = [{"id": k, "label": v["label"],
                              "units": v["units"], "source": v["source"]}
                             for k, v in scenario_field.MAP_LAYERS.items()]
            _FIELD_CACHE[cache_key] = out
            return jsonify(out)
        except Exception as e:
            app.logger.info("Compact read failed (%s), falling back", e)

    try:
        out = scenario_field.read_map_layer(
            path, layer=layer, zone=zone,
            south=scfg.get("southern_hemisphere", True),
            time_index=tstep, layer_index=lvl,
            rotate=scfg.get("rotate_vectors", True), **common)
    except Exception as e:
        return jsonify({"error": "layer_unavailable",
                        "message": f"{type(e).__name__}: {e}"[:300]}), 422

    # Un fuseau errone deplacerait le lac de plusieurs degres sans
    # message d'erreur : on le signale explicitement.
    if hint:
        centre_lon = (out["bounds"][0][1] + out["bounds"][1][1]) / 2
        centre_lat = (out["bounds"][0][0] + out["bounds"][1][0]) / 2
        if abs(centre_lon - hint[0]) > 2 or abs(centre_lat - hint[1]) > 2:
            out["warning"] = (
                f"Reprojected domain centre ({centre_lon:.2f}, "
                f"{centre_lat:.2f}) is far from the configured lake centre "
                f"({hint[0]:.2f}, {hint[1]:.2f}) — check scenarios.utm_zone.")

    out["key"] = entry["key"]
    out["layers"] = [{"id": k, "label": v["label"], "units": v["units"],
                      "source": v["source"]}
                     for k, v in scenario_field.MAP_LAYERS.items()]
    if len(_FIELD_CACHE) > 8:
        _FIELD_CACHE.clear()
    _FIELD_CACHE[cache_key] = out
    return jsonify(out)


@app.get("/api/scenario/currents")
def api_scenario_currents():
    """Carte de courants : intensite + fleches, prete a tracer."""
    idx = load_scenario_index()
    if idx is None:
        return jsonify({"error": "no_index"}), 404

    key = request.args.get("key")
    entry = next((s for s in idx["scenarios"] if s["key"] == key), None)
    if entry is None:
        return jsonify({"error": "unknown_scenario", "key": key}), 404
    if idx.get("demo"):
        return jsonify({"error": "demo_index",
                        "message": "Demo index: no real NetCDF output to "
                                   "plot."}), 409

    files = entry.get("files") or {}
    path = files.get("flow")
    if not path:
        return jsonify({"error": "no_flow_output",
                        "message": "Currents require the FLOW output, which "
                                   "is missing for this run."}), 404

    scfg = CONFIG.get("scenarios") or {}

    def _int_arg(name, default):
        raw = request.args.get(name)
        try:
            return int(raw) if raw not in (None, "") else default
        except ValueError:
            return default

    layer = _int_arg("layer", scfg.get("layer_index", 0))
    tstep = _int_arg("time", scfg.get("time_index", -1))
    density = _int_arg("density", scfg.get("arrow_density", 30))
    cache_key = (path, "__currents__", layer, tstep, density)
    if cache_key in _FIELD_CACHE:
        return jsonify(_FIELD_CACHE[cache_key])

    try:
        vecs = scenario_field.read_currents(
            path, n_arrows=density, time_index=tstep, layer_index=layer,
            grid_res=scfg.get("current_grid_res", 250),
            smooth=scfg.get("current_smooth", 2.0),
            vmin=scfg.get("current_vmin"), vmax=scfg.get("current_vmax"),
            bounds=scfg.get("current_bounds"),
            rotate=scfg.get("rotate_vectors", True))
    except Exception as e:
        return jsonify({"error": "currents_unavailable",
                        "message": f"{type(e).__name__}: {e}"[:300]}), 422

    vecs["key"] = entry["key"]
    if len(_FIELD_CACHE) > 12:
        _FIELD_CACHE.clear()
    _FIELD_CACHE[cache_key] = vecs
    return jsonify(vecs)


# ── Mise a jour a la demande ─────────────────────────────────

def _run_refresh(download):
    cmd = [sys.executable, str(ROOT / "pipeline" / "update_swot.py")]
    if download:
        cmd.append("--download")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=str(ROOT), timeout=3600)
        ok = proc.returncode == 0
        if ok:
            data = load_data() or {}
            src = data.get("source") or {}
            n = src.get("new_this_run", 0)
            if n:
                msg = f"{n} new granule{'s' if n > 1 else ''} processed"
            elif download and src.get("found_in_window") == 0:
                msg = ("No granules found in the search window — check "
                       "short_names and granule_patterns in config.yaml")
            elif src.get("last_remote_granule_date"):
                msg = ("Up to date — latest remote granule: "
                       f"{src['last_remote_granule_date'][:10]}")
            else:
                msg = "No new granules"
        else:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            msg = tail[-1][:300] if tail else "Pipeline failed"
    except subprocess.TimeoutExpired:
        ok, msg = False, "Timed out after 60 minutes"
    except Exception as e:  # message toujours renvoye au client
        ok, msg = False, str(e)[:300]

    with REFRESH_LOCK:
        REFRESH_STATE["running"] = False
        REFRESH_STATE["last"] = {"ok": ok, "message": msg,
                                 "finished_at": now_iso()}


def refresh_allowed():
    """Le rafraichissement lance un sous-processus et declenche des
    telechargements : a desactiver sur un site accessible publiquement
    (LKE_ALLOW_REFRESH=0 ou server.allow_refresh: false)."""
    env = os.environ.get("LKE_ALLOW_REFRESH")
    if env is not None:
        return env not in ("0", "false", "no")
    return bool((CONFIG.get("server") or {}).get("allow_refresh", True))


@app.post("/api/refresh")
def refresh():
    if not refresh_allowed():
        return jsonify({
            "error": "refresh_disabled",
            "message": "Data refresh is disabled on this deployment; run "
                       "the pipeline on the machine holding the data.",
        }), 403
    download = request.args.get("download", "1") != "0"
    with REFRESH_LOCK:
        if REFRESH_STATE["running"]:
            return jsonify({"error": "busy",
                            "started_at": REFRESH_STATE["started_at"]}), 409
        REFRESH_STATE["running"] = True
        REFRESH_STATE["started_at"] = now_iso()
        REFRESH_STATE["last"] = None
    threading.Thread(target=_run_refresh, args=(download,),
                     daemon=True).start()
    return jsonify({"started": True, "download": download})


@app.get("/api/refresh/status")
def refresh_status():
    with REFRESH_LOCK:
        state = dict(REFRESH_STATE)
    state["allowed"] = refresh_allowed()
    return jsonify(state)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
