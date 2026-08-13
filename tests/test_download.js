/* Test de l'export CSV (frontend/download.js).
 *
 *   node tests/test_download.js
 *
 * Un fichier telecharge quitte le site : il doit rester interpretable
 * seul, d'ou les controles sur l'entete de metadonnees, les unites et
 * l'echappement.
 */

"use strict";

const assert = require("assert");
const path = require("path");
const D = require(path.join(__dirname, "..", "frontend", "download.js"));

// ── Échappement CSV ──────────────────────────────────────────

assert.strictEqual(D.escapeCell("Marree Airport"), "Marree Airport");
assert.strictEqual(D.escapeCell("a,b"), '"a,b"');
assert.strictEqual(D.escapeCell('say "hi"'), '"say ""hi"""');
assert.strictEqual(D.escapeCell("line\nbreak"), '"line\nbreak"');
assert.strictEqual(D.escapeCell(null), "");
assert.strictEqual(D.escapeCell(undefined), "");
assert.strictEqual(D.escapeCell(0), "0");        // zéro n'est pas vide

const csv = D.toCSV(["a", "b"], [[1, 2], ["x,y", null]], ["note"]);
assert.strictEqual(csv, '# note\na,b\n1,2\n"x,y",\n');

// ── Niveaux d'eau ────────────────────────────────────────────

const wse = {
  datum_label: "WSE (m, EGM2008 geoid)",
  demo: false,
  sites: [
    { name: "Belt Bay", lon: 137.028098, lat: -28.893022,
      series: [{ date: "2026-07-25T17:02:00", wse: -12.93 },
               { date: "2026-08-05T03:11:00", wse: -12.88 }] },
    { name: "Madigan Gulf", lon: 137.56, lat: -28.893,
      series: [{ date: "2026-07-25T17:02:00", wse: -12.71 }] },
  ],
};

const wf = D.wseCSV(wse);
assert(/^ktle_water_levels_\d{4}-\d{2}-\d{2}\.csv$/.test(wf.name), wf.name);

const wl = wf.text.split("\n");
const wHeader = wl.filter((l) => l.startsWith("#"));
assert(wHeader.some((l) => l.includes("SWOT L2 HR Raster")), "source absente");
assert(wHeader.some((l) => l.includes("EGM2008")), "datum absent");
assert(wHeader.some((l) => l.includes("13x13")), "méthode absente");
assert(!wHeader.some((l) => l.includes("WARNING")), "aucune donnée synthétique");

const wCols = wl[wHeader.length];
assert.strictEqual(wCols, "site,longitude,latitude,date_utc,wse_m");
// Une ligne par observation, tous sites confondus
const wData = wl.slice(wHeader.length + 1).filter((l) => l);
assert.strictEqual(wData.length, 3);
assert(wData[0].startsWith("Belt Bay,137.028098,-28.893022,"));
assert(wData[2].startsWith("Madigan Gulf,"));
// L'unité figure dans le nom de colonne, pas dans les cellules
assert(!wData.some((l) => l.includes(" m")), "pas d'unité dans les cellules");

// Les données de démonstration doivent être signalées
const demoFile = D.wseCSV(Object.assign({}, wse, { demo: true }));
assert(demoFile.text.includes("WARNING: synthetic"), "démo non signalée");

// Une série vide reste un fichier valide, avec son en-tête
const empty = D.wseCSV({ sites: [] });
assert(empty.text.includes("site,longitude"), empty.text);

// ── Météo ────────────────────────────────────────────────────

const wx = {
  demo: false, stale: true,
  stations: [
    { name: "Marree Airport", lat: -29.66, lon: 138.065, ok: true,
      history: [
        { utc: "20260812060000", wind_dir: "SE", wind_dir_deg: 135,
          wind_spd_kmh: 20, gust_kmh: 28, air_temp: 16.1, rel_hum: 52,
          press_hpa: 1016, rain_since_9am: 0 },
        { utc: "20260812063000", wind_dir: null, wind_dir_deg: null,
          wind_spd_kmh: 0, gust_kmh: null, air_temp: 15.8, rel_hum: null,
          press_hpa: 1016.2, rain_since_9am: 0 },
      ] },
  ],
};

const wxf = D.weatherCSV(wx);
const wxl = wxf.text.split("\n");
const wxHeader = wxl.filter((l) => l.startsWith("#"));
assert(wxHeader.some((l) => l.includes("Bureau of Meteorology")));
assert(wxHeader.some((l) => l.includes("ten-minute mean")), "convention absente");
assert(wxHeader.some((l) => l.includes("unreachable")), "stale non signalé");
assert.strictEqual(wxl[wxHeader.length], D.WEATHER_COLUMNS.join(","));

const wxData = wxl.slice(wxHeader.length + 1).filter((l) => l);
assert.strictEqual(wxData.length, 2);
// Les valeurs manquantes deviennent des cellules vides, pas "null"
assert(!wxData[1].includes("null"), wxData[1]);
assert(wxData[1].includes(",0,"), "un calme à 0 km/h doit rester présent");
assert.strictEqual(wxData[0].split(",").length, D.WEATHER_COLUMNS.length);
assert.strictEqual(wxData[1].split(",").length, D.WEATHER_COLUMNS.length);

// ── Couche du modèle ─────────────────────────────────────────

const scenario = { key: "wind-sp6.0_wind-dir135.0_wlvl-13.0_sal150.0",
                   params: { wind_speed: 6, wind_dir: 135, wlvl: -13,
                             salinity: 150 } };

// Champ complet disponible (site servi par Flask) -> grille
const withGrid = {
  layer: "hsign", label: "Wave height", units: "m",
  lat: [-29.0, -28.9], lon: [137.0, 137.1],
  z: [[0.11, null], [0.14, 0.15]],
  arrows: { lat: [-28.95], lon: [137.05], bearing: [135], value: [0.13] },
};
const gf = D.layerCSV(withGrid, scenario);
assert(gf.name.endsWith("_grid.csv"), gf.name);
assert(gf.name.includes("hsign"), gf.name);
const gRows = gf.text.split("\n").filter((l) => l && !l.startsWith("#"));
assert.strictEqual(gRows[0], "longitude,latitude,value");
// Les cellules sèches (null) sont omises : 3 points sur 4
assert.strictEqual(gRows.length - 1, 3, gRows);
assert(gf.text.includes("Scenario: " + scenario.key));
assert(gf.text.includes("wind 6 m/s from 135 deg"));

// Champ absent (site statique) -> flèches, avec la direction
const arrowsOnly = {
  layer: "currents", label: "Current speed", units: "m/s",
  arrows: { lat: [-28.95, -28.9], lon: [137.05, 137.1],
            bearing: [90, 120], value: [0.21, 0.18] },
};
const af = D.layerCSV(arrowsOnly, scenario);
assert(af.name.endsWith("_arrows.csv"), af.name);
const aRows = af.text.split("\n").filter((l) => l && !l.startsWith("#"));
assert.strictEqual(aRows[0], "longitude,latitude,bearing_deg,value");
assert.strictEqual(aRows.length - 1, 2);
assert(af.text.includes("Current speed (m/s)"));
assert(af.text.includes("true direction"), "convention d'azimut absente");

// Sans scénario, le fichier reste exploitable
const noScen = D.layerCSV(arrowsOnly, null);
assert(!noScen.text.includes("Scenario:"));
assert(noScen.name.startsWith("ktle_currents"));

// ── Noms de fichiers ─────────────────────────────────────────

assert.strictEqual(D.slug("wind-sp6.0_wind-dir135.0"), "wind-sp6-0-wind-dir135-0");
assert.strictEqual(D.slug("Wave height"), "wave-height");
assert(!/[^a-z0-9._-]/.test(af.name), `nom de fichier douteux : ${af.name}`);
assert(!/[^a-z0-9._-]/.test(wf.name), wf.name);

console.log("OK — échappement, en-têtes de métadonnées, niveaux d'eau, météo, "
  + "grille et flèches, noms de fichiers validés.");

// ── Surface en eau : la citation doit accompagner les données ─

const area = {
  note: "Spatial constraint from the Delft3D domain",
  series: [
    { date: "2026-07-25", area_km2: 910.4, uncert_km2: 12.1,
      coverage: 0.82, partial: false, n_scenes: 3 },
    { date: "2026-08-05", area_km2: 120.0, uncert_km2: null,
      coverage: 0.09, partial: true, n_scenes: 1 },
  ],
};

const af2 = D.areaCSV(area);
assert(/^ktle_water_area_\d{4}-\d{2}-\d{2}\.csv$/.test(af2.name), af2.name);

const aHead = af2.text.split("\n").filter((l) => l.startsWith("#"));
// La méthode n'est pas de nous : la référence voyage avec le fichier
assert(aHead.some((l) => l.includes("Rai")), "auteur absent");
assert(aHead.some((l) => l.includes("Journal of Hydrology 676, 135652")),
  "référence incomplète");
assert(aHead.some((l) => l.includes("10.1016/j.jhydrol.2026.135652")),
  "DOI absent");
assert(aHead.some((l) => l.includes("partial")), "réserve sur la couverture");

const aBody = af2.text.split("\n").filter((l) => l && !l.startsWith("#"));
assert.strictEqual(aBody[0],
  "date,area_km2,uncertainty_km2,coverage_fraction,pass_coverage,n_scenes");
assert.strictEqual(aBody.length - 1, 2);
assert(aBody[1].includes(",full,"), aBody[1]);
// Un passage partiel doit être identifiable dans le fichier lui-même
assert(aBody[2].includes(",partial,"), aBody[2]);
// Une incertitude absente reste une cellule vide, pas "null"
assert(!aBody[2].includes("null"), aBody[2]);

assert(D.AREA_CITATION.includes("doi.org/10.1016/j.jhydrol.2026.135652"));

// Une série vide donne un fichier valide, citation comprise
const emptyArea = D.areaCSV({ series: [] });
assert(emptyArea.text.includes("Rai"));
assert(emptyArea.text.includes("date,area_km2"));

console.log("OK — export de la surface en eau : citation, DOI, réserve sur "
  + "les passages partiels et valeurs manquantes validés.");
