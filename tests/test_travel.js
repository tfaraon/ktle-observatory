/* Test de frontend/travel.js :  node tests/test_travel.js */
"use strict";
const assert = require("assert");
const path = require("path");
const T = require(path.join(__dirname, "..", "frontend", "travel.js"));

const day = (i) => new Date(Date.UTC(2025, 0, 1 + i)).toISOString().slice(0, 10);

// Série de pluie, et un débit qui la reproduit 21 jours plus tard
const rain = [], flow = [];
for (let i = 0; i < 400; i += 1) {
  const v = Math.max(0, Math.sin(i / 9) * 10 + Math.cos(i / 31) * 6);
  rain.push([day(i), Math.round(v * 100) / 100]);
  flow.push([day(i + 21), Math.round(v * 3 * 100) / 100]);
}

const best = T.bestLag(rain, flow, 60);
assert.strictEqual(best.lag, 21, `décalage trouvé : ${best.lag}`);
assert(best.r > 0.99, best.r);
assert(best.n >= T.MIN_OVERLAP);
assert(best.curve.length === 61);

// Alignement et corrélation
const al = T.align(rain, flow, 21);
assert.strictEqual(al.x.length, al.y.length);
assert.strictEqual(al.dates[0], day(0));
assert(Math.abs(T.pearson([1, 2, 3, 4], [2, 4, 6, 8]) - 1) < 1e-9);
assert.strictEqual(T.pearson([1, 1, 1], [1, 2, 3]), null, "série constante : pas de corrélation");
assert.strictEqual(T.pearson([1], [1]), null);

// Trop peu de données communes, ou aucun lien : aucune conclusion
assert.strictEqual(T.bestLag(rain.slice(0, 40), flow, 60), null, "moins de 90 jours communs");
const noise = rain.map(([d], i) => [d, ((i * 7919) % 97) / 10]);
assert.strictEqual(T.bestLag(noise, flow, 60, 0.9), null, "aucun lien net");

// Somme glissante et variation quotidienne
const rows = [["2025-01-01", 1], ["2025-01-02", 2], ["2025-01-03", 3]];
assert.deepStrictEqual(T.rolling(rows, 2, true), [["2025-01-02", 3], ["2025-01-03", 5]]);
assert.deepStrictEqual(T.rolling(rows, 3), [["2025-01-02", 6]], "fenêtre centrée");
// Fenêtre centrée : le décalage mesuré reste celui de la série, sans biais
assert.strictEqual(T.bestLag(T.rolling(rain, 7), flow, 60).lag, 21, "cumul centré : pas de biais");
assert.strictEqual(T.bestLag(T.rolling(rain, 7, true), flow, 60).lag, 18, "cumul arrière : biaisé");
const chg = T.dailyChange([["2025-01-01", 10], ["2025-01-03", 14], ["2025-03-01", 20]]);
assert.deepStrictEqual(chg, [["2025-01-03", 2]], "saut de deux mois ignoré, pente par jour");

// Phrase
assert(T.sentence("the rain and the flow", best).includes("about 3 weeks"));
assert(T.sentence("the rain and the flow", null).startsWith("Not enough"));

console.log("OK — décalage retrouvé à 21 jours, corrélation, garde-fous (peu de données, "
  + "série constante, aucun lien), somme glissante, variation quotidienne, phrase.");
