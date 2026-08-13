/* Test de la logique des roses des vents (frontend/windrose.js).
 *
 * Exécuté sous Node : node tests/test_windrose.js
 *
 * Le point délicat est la position solaire — une erreur y décalerait
 * silencieusement le partage jour/nuit, et donc l'interprétation des
 * régimes de vent.
 */

"use strict";

const assert = require("assert");
const path = require("path");
const W = require(path.join(__dirname, "..", "frontend", "windrose.js"));

const LAT = -28.9, LON = 137.35;          // Kati Thanda – Lake Eyre
const ok = [];

// ── Position solaire ─────────────────────────────────────────

// Midi solaire local (137.35 °E -> ~02:50 UTC), le 12 août.
// Valeur attendue par la géométrie : 90 - |lat - déclinaison|, soit
// 90 - |-28.9 - 14.9| = 46.2°.
const noon = new Date(Date.UTC(2026, 7, 12, 2, 50));
const elevNoon = W.solarElevation(noon, LAT, LON);
assert(elevNoon > 44 && elevNoon < 48,
  `élévation à midi solaire : ${elevNoon.toFixed(1)}° (46.2 attendu)`);
ok.push(`midi solaire ${elevNoon.toFixed(1)}°`);

// Minuit solaire : soleil bien sous l'horizon
const midnight = new Date(Date.UTC(2026, 7, 12, 14, 50));
assert(W.solarElevation(midnight, LAT, LON) < -30);
assert(!W.isDaytime(midnight, LAT, LON));

// Durée du jour : mi-août à 28.9 °S, environ 11 h
function dayLengthHours(y, m, d) {
  let count = 0;
  for (let k = 0; k < 24 * 6; k++) {
    const t = new Date(Date.UTC(y, m, d, 0, 0) + k * 10 * 60000);
    if (W.isDaytime(t, LAT, LON)) count += 1;
  }
  return count / 6;
}
const augLength = dayLengthHours(2026, 7, 12);
assert(augLength > 10.5 && augLength < 11.6,
  `durée du jour en août : ${augLength.toFixed(2)} h (≈11 attendu)`);
ok.push(`jour d'août ${augLength.toFixed(2)} h`);

// Solstices : jour long en décembre, court en juin (hémisphère sud)
const dec = dayLengthHours(2026, 11, 21);
const jun = dayLengthHours(2026, 5, 21);
assert(dec > 13.5 && dec < 14.5, `solstice de décembre : ${dec.toFixed(2)} h`);
assert(jun > 9.5 && jun < 10.5, `solstice de juin : ${jun.toFixed(2)} h`);
assert(dec > jun, "hémisphère sud : décembre plus long que juin");
ok.push(`solstices ${jun.toFixed(1)} h / ${dec.toFixed(1)} h`);

// Hémisphère nord : la saisonnalité doit s'inverser
function dayLengthAt(lat, lon, y, m, d) {
  let c = 0;
  for (let k = 0; k < 24 * 6; k++) {
    const t = new Date(Date.UTC(y, m, d, 0, 0) + k * 10 * 60000);
    if (W.isDaytime(t, lat, lon)) c += 1;
  }
  return c / 6;
}
assert(dayLengthAt(48.85, 2.35, 2026, 5, 21)
       > dayLengthAt(48.85, 2.35, 2026, 11, 21),
  "hémisphère nord : juin plus long que décembre");
ok.push("saisonnalité inversée au nord");

// ── Sélection des périodes ───────────────────────────────────

function stamp(date) {
  const p = (v, n = 2) => String(v).padStart(n, "0");
  return `${date.getUTCFullYear()}${p(date.getUTCMonth() + 1)}`
    + `${p(date.getUTCDate())}${p(date.getUTCHours())}`
    + `${p(date.getUTCMinutes())}00`;
}

// Huit jours de relevés toutes les 30 min
const end = new Date(Date.UTC(2026, 7, 12, 6, 0));
const history = [];
for (let k = 8 * 48 - 1; k >= 0; k--) {
  const at = new Date(end.getTime() - k * 30 * 60000);
  const day = W.isDaytime(at, LAT, LON);
  history.push({
    utc: stamp(at),
    // Régime contrasté : vent fort de sud-est le jour, faible de nord
    // la nuit — le partage doit le faire ressortir.
    wind_spd_kmh: day ? 28 : 8,
    wind_dir_deg: day ? 135 : 0,
    wind_dir: day ? "SE" : "N",
  });
}

const all = W.selectPeriod(history, "all", LAT, LON, end);
assert.strictEqual(all.length, history.length);

const h24 = W.selectPeriod(history, "h24", LAT, LON, end);
assert(h24.length >= 47 && h24.length <= 49, `24 h : ${h24.length} relevés`);

const d7 = W.selectPeriod(history, "d7", LAT, LON, end);
const n7 = W.selectPeriod(history, "n7", LAT, LON, end);
assert(d7.every((r) => r.wind_dir_deg === 135), "7 jours : que du diurne");
assert(n7.every((r) => r.wind_dir_deg === 0), "7 nuits : que du nocturne");
// Sur 7 jours à cette saison, la nuit est plus longue que le jour
assert(n7.length > d7.length, `${d7.length} diurnes / ${n7.length} nocturnes`);
ok.push(`7 jours : ${d7.length} diurnes, ${n7.length} nocturnes`);

// Période contiguë : une seule journée, pas sept
const lastday = W.selectPeriod(history, "lastday", LAT, LON, end);
assert(lastday.length > 0 && lastday.length < d7.length / 5,
  `dernière journée : ${lastday.length} relevés`);
assert(lastday.every((r) => r.wind_dir_deg === 135));
// Les relevés doivent être consécutifs
const times = lastday.map((r) => W.obsDate(r).getTime());
for (let i = 1; i < times.length; i++) {
  assert.strictEqual(times[i] - times[i - 1], 30 * 60000,
    "la dernière journée doit être d'un seul tenant");
}
ok.push(`dernière journée : ${lastday.length} relevés consécutifs`);

const lastnight = W.selectPeriod(history, "lastnight", LAT, LON, end);
assert(lastnight.length > 0);
assert(lastnight.every((r) => r.wind_dir_deg === 0));

// Historique vide ou sans horodatage
assert.deepStrictEqual(W.selectPeriod([], "all", LAT, LON), []);
assert.deepStrictEqual(W.selectPeriod([{ wind_spd_kmh: 5 }], "all", LAT, LON),
  []);

// ── Répartition directionnelle ───────────────────────────────

const rose = W.binRose(d7);
assert.strictEqual(rose.sectors.length, 16);
assert.strictEqual(rose.series.length, W.SPEED_BINS.length);
rose.series.forEach((row) => assert.strictEqual(row.length, 16));

// Tout le vent diurne vient du sud-est, à 28 km/h -> secteur SE, bin 20–30
const seIndex = rose.sectors.indexOf("SE");
const bin2030 = W.SPEED_LABELS.indexOf("20–30");
assert(Math.abs(rose.series[bin2030][seIndex] - 100) < 1e-6,
  "100 % attendu en SE, bin 20–30");
const others = rose.series.reduce((sum, row, b) =>
  sum + row.reduce((s, v, i) => s + ((b === bin2030 && i === seIndex) ? 0 : v),
    0), 0);
assert(Math.abs(others) < 1e-6, "aucun autre secteur ne doit être rempli");
assert.strictEqual(rose.total, d7.length);
assert.strictEqual(rose.calm, 0);

// Les secteurs doivent être centrés : 349° comme 11° tombent en N
assert.strictEqual(W.binRose([{ wind_spd_kmh: 15, wind_dir_deg: 349 }])
  .series[1][0] > 0, true);
assert.strictEqual(W.binRose([{ wind_spd_kmh: 15, wind_dir_deg: 11 }])
  .series[1][0] > 0, true);
// 100° doit tomber en E (90°), pas en ESE
assert(W.binRose([{ wind_spd_kmh: 15, wind_dir_deg: 100 }])
  .series[1][W.SECTORS.indexOf("E")] > 0);

// Calme et valeurs manquantes
const mixed = W.binRose([
  { wind_spd_kmh: 0, wind_dir_deg: null },
  { wind_spd_kmh: 12, wind_dir_deg: 180 },
  { wind_spd_kmh: null, wind_dir_deg: 90 },     // ignoré
]);
assert.strictEqual(mixed.total, 2);
assert.strictEqual(mixed.calm, 1);
assert(Math.abs(mixed.calmPercent - 50) < 1e-6);

// Les pourcentages somment à 100 moins les calmes
const sum = rose.series.reduce((s, row) =>
  s + row.reduce((a, b) => a + b, 0), 0);
assert(Math.abs(sum - (100 - rose.calmPercent)) < 1e-6, sum);

assert.strictEqual(W.binRose([]).total, 0);

console.log("OK — position solaire (" + ok.join(" · ") + "), sélection des "
  + "périodes et répartition directionnelle validées.");
