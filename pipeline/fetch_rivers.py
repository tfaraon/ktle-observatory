#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debits et hauteurs des rivieres du bassin, d'apres Water Data Online
(Bureau of Meteorology).

    python pipeline/fetch_rivers.py              # met a jour data/rivers.json
    python pipeline/fetch_rivers.py --discover   # liste les stations retenues
    python pipeline/fetch_rivers.py --demo

Water Data Online reunit les series des agences d'Etat (Queensland,
Australie-Meridionale, Territoire du Nord) ; il est mis a jour une fois
par jour, pas en temps reel. On l'interroge par son service KiWIS, avec
les moyennes journalieres controlees (DMQaQc.Merged.DailyMean.24HR).

Choix des stations : par defaut (rivers.stations: auto), toutes celles
dont la position tombe dans le contour du bassin et qui ont transmis un
debit ou une hauteur dans les `active_days` derniers jours. Beaucoup de
stations du bassin ont ferme : c'est pourquoi on ne fige pas de liste.
`--discover` affiche le resultat pour le verifier ; une liste explicite
de numeros de stations peut ensuite remplacer « auto » dans config.yaml.

Licence : Creative Commons Attribution, sauf mention contraire du
fournisseur, que le site cite.
"""

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

import basin_outline as bo

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "rivers.json"
USER_AGENT = "ktle-observatory/1.0 (research outreach; github.com/tfaraon/ktle-observatory)"
TS_NAME = "DMQaQc.Merged.DailyMean.24HR"
PARAMS = {"discharge": "Water Course Discharge", "level": "Water Course Level"}
FIELDS = "station_no,station_name,station_latitude,station_longitude,ts_id,ts_unitsymbol,coverage"

DEFAULTS = {
    "service": "https://www.bom.gov.au/waterdata/services",
    "stations": "auto",
    "active_days": 60,
    "history_days": 365,
    "pause_s": 0.5,
}


def settings(cfg):
    s = dict(DEFAULTS, **((cfg or {}).get("rivers") or {}))
    s["history_days"] = max(30, min(int(s["history_days"]), 3650))
    return s


def kiwis(s, request, extra, timeout=60):
    q = {"service": "kisters", "type": "queryServices", "request": request,
         "datasource": 0, "format": "json"}
    q.update(extra)
    url = f"{s['service']}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def table(rows):
    """Reponse KiWIS en tableau : premiere ligne = noms de colonnes."""
    if not rows:
        return []
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:]]


def _day(ts):
    return str(ts)[:10] if ts else None


def discover(cfg, call=kiwis, today=None):
    """Series journalieres de debit et de hauteur des stations du bassin."""
    s = settings(cfg)
    outline, _ = bo.load_outline(cfg)
    today = today or datetime.now(timezone.utc).date()
    horizon = str(today - timedelta(days=int(s["active_days"])))
    wanted = s["stations"] if isinstance(s["stations"], list) else None
    found = {}
    for kind, pname in PARAMS.items():
        rows = table(call(s, "getTimeseriesList",
                          {"parametertype_name": pname, "ts_name": TS_NAME, "returnfields": FIELDS}))
        for r in rows:
            try:
                lat, lon = float(r["station_latitude"]), float(r["station_longitude"])
            except (TypeError, ValueError, KeyError):
                continue
            no = str(r.get("station_no", "")).strip()
            if wanted is not None:
                if no not in wanted:
                    continue
            elif not bo.contains(outline, lon, lat):
                continue
            st = found.setdefault(no, {"station_no": no, "name": r.get("station_name"),
                                       "lat": round(lat, 5), "lon": round(lon, 5), "series": {}})
            st["series"][kind] = {"ts_id": r.get("ts_id"), "unit": r.get("ts_unitsymbol"),
                                  "to": _day(r.get("to"))}
    out = []
    for st in found.values():
        last = max((v["to"] or "") for v in st["series"].values())
        st["active"] = bool(last) and last >= horizon
        if wanted is not None or st["active"]:
            out.append(st)
    return sorted(out, key=lambda x: (-x["lat"], x["lon"]))


def values(s, ts_id, start, end, call=kiwis):
    res = call(s, "getTimeseriesValues", {
        "ts_id": ts_id, "from": str(start), "to": str(end),
        "returnfields": "Timestamp,Value,Quality Code"})
    block = res[0] if isinstance(res, list) and res else {}
    out = []
    for row in block.get("data") or []:
        ts, v = row[0], row[1]
        if v is None:
            continue
        try:
            out.append([_day(ts), round(float(v), 3)])
        except (TypeError, ValueError):
            continue
    return out


def status(st):
    """Etat d'une station : ecoulement, absence d'ecoulement, ou pas de donnee recente."""
    q = st.get("discharge") or {}
    last = q.get("last")
    if not st.get("active"):
        return "no recent data"
    if last is None:
        return "level only"
    return "flowing" if last["value"] > 0.001 else "no flow"


def update(cfg, demo=False, call=kiwis, today=None, write=True, sleep=time.sleep):
    s = settings(cfg)
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=int(s["history_days"]))
    errors = []
    if demo:
        stations = demo_stations(today, start)
    else:
        try:
            stations = discover(cfg, call=call, today=today)
        except Exception as e:
            prev = load_previous()
            if prev is None:
                raise SystemExit(f"Water Data Online injoignable et aucun fichier précédent : {e}")
            prev["stale"], prev["errors"] = True, [f"{type(e).__name__}: {e}"[:160]]
            if write:
                OUT_FILE.write_text(json.dumps(prev, indent=1), encoding="utf-8")
            return prev
        for st in stations:
            for kind, meta in st.pop("series").items():
                try:
                    vals = values(s, meta["ts_id"], start, today, call=call)
                    sleep(s["pause_s"])
                except Exception as e:
                    errors.append(f"{st['station_no']} {kind}: {type(e).__name__}")
                    continue
                st[kind] = {"unit": meta["unit"], "values": vals,
                            "last": {"date": vals[-1][0], "value": vals[-1][1]} if vals else None}
    for st in stations:
        st["status"] = status(st)
    payload = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "demo": bool(demo), "stale": False, "errors": errors[:20],
        "source": "Water Data Online, Bureau of Meteorology",
        "source_url": "https://www.bom.gov.au/waterdata/",
        "licence": "Creative Commons Attribution unless the data supplier states otherwise",
        "selection": "auto" if s["stations"] == "auto" else "list",
        "history_from": str(start),
        "stations": stations,
    }
    if write:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUT_FILE.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload


def load_previous():
    if not OUT_FILE.exists():
        return None
    try:
        return json.loads(OUT_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return None


def demo_stations(today, start):
    """Trois stations fictives, marquees demonstration, avec une onde de crue."""
    import math
    specs = [("DEMO01", "Demonstration upstream gauge", -23.4, 144.2, 0),
             ("DEMO02", "Demonstration middle gauge", -25.4, 142.7, 18),
             ("DEMO03", "Demonstration downstream gauge", -27.6, 141.1, 40)]
    out = []
    n = (today - start).days
    for no, name, lat, lon, lag in specs:
        vals = []
        for k in range(n + 1):
            d = start + timedelta(days=k)
            peak = n - 60 + lag
            q = max(0.0, 400 * math.exp(-((k - peak) / 12.0) ** 2))
            vals.append([str(d), round(q, 2)])
        out.append({"station_no": no, "name": name, "lat": lat, "lon": lon, "active": True,
                    "discharge": {"unit": "cumec", "values": vals,
                                  "last": {"date": vals[-1][0], "value": vals[-1][1]}}})
    return out


def main():
    ap = argparse.ArgumentParser(description="Débits des rivières du bassin du lac Eyre")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--discover", action="store_true", help="Lister les stations retenues")
    ap.add_argument("--demo", action="store_true", help="Données synthétiques, sans réseau")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.discover:
        for st in discover(cfg):
            kinds = ", ".join(f"{k} ({v['unit']}, jusqu'au {v['to']})" for k, v in st["series"].items())
            print(f"{st['station_no']:>10}  {st['name']:<45} {st['lat']:>9} {st['lon']:>9}  {kinds}")
        return
    p = update(cfg, demo=args.demo)
    print(f"JSON écrit : {OUT_FILE}{' (démonstration)' if p.get('demo') else ''}")
    for st in p["stations"]:
        q = (st.get("discharge") or {}).get("last")
        extra = f"{q['value']} {st['discharge']['unit']} le {q['date']}" if q else "pas de débit"
        print(f"  {st['station_no']:>10}  {st['name']:<45} {st['status']:<15} {extra}")
    for e in p.get("errors", []):
        print("  échec :", e)


if __name__ == "__main__":
    main()
